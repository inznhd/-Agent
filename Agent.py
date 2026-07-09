from doctest import debug
from typing import Any

from openai import OpenAI
import os
import json
import logging

from dataclasses import is_dataclass, asdict
from datetime import datetime
from decimal import Decimal

from Tools.CLI_Tool import run_cli
from Tools.Calculator_Tool import calculate
from Tools.Search_Tool import search
from SessionManager import SessionManager
from ContextManager import ContextManager
from logger_config import setup_logger

import config

# 本模块 logger
logger = logging.getLogger(__name__)

# 获取工具的描述
def get_tools_info() -> list[dict]:
    tools = [
        # ── CLI 命令工具 ──
        {
            "type": "function",
            "function": {
                "name": "run_cli_tool",
                "description": "执行外部命令行命令，返回结构化结果。所有非 command 参数均为可选，不传则使用合理的默认值。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "anyOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}}
                            ],
                            "description": "要执行的命令，可以是字符串（如 'ls -l'）或字符串数组（如 ['ls', '-l']），推荐数组形式以防止注入。"
                        },
                        "timeout": {"type": "number", "description": "最大等待秒数，超时后终止进程"},
                        "cwd": {"type": "string", "description": "工作目录，默认为当前目录"},
                        "env": {"type": "object", "additionalProperties": {"type": "string"},
                                "description": "环境变量键值对"},
                        "shell": {"type": "boolean", "description": "是否通过 shell 执行，默认自动判断"},
                        "text": {"type": "boolean", "description": "是否以文本形式返回输出，默认 true"},
                        "encoding": {"type": "string",
                                     "description": "文本解码编码，默认使用gbk"},
                        "errors": {"type": "string", "description": "解码错误处理策略，默认 replace"}
                    },
                    "required": ["command"]
                }
            }
        },
        # ── 计算器工具 ──
        {
            "type": "function",
            "function": {
                "name": "calculator_tool",
                "description": "安全执行数学计算（支持 + - * / // % ** 及 sqrt、sin、cos、log 等函数），返回数值结果。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "数学表达式，如 '2 + 2'、'sqrt(16)'、'(3.14 * 5 ** 2)'、'sin(pi/2)'"
                        },
                        "precision": {
                            "type": "integer",
                            "description": "小数精度（保留几位小数），不传则不截断"
                        }
                    },
                    "required": ["expression"]
                }
            }
        },
        # ── 搜索工具（Mock） ──
        {
            "type": "function",
            "function": {
                "name": "search_tool",
                "description": "执行搜索查询（当前为 Mock 实现，无需联网），返回结构化搜索结果列表，包含标题、摘要和链接。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词，如 'python pip install'、'docker 入门'"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "最大返回结果数（1-20），默认 5"
                        },
                        "source": {
                            "type": "string",
                            "description": "搜索源，当前仅支持 'mock'（默认值）"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
    ]
    return tools

Function_Name_Mapping = {
    "run_cli_tool"   : run_cli,
    "calculator_tool": calculate,
    "search_tool"    : search,
}

# 主模型调用-流式输出 -> 返回迭代器
def stream_query(history_messages: list[dict]):
    """
    输入历史消息，返回迭代器
    :param history_messages:
    :return:
    """
    client = OpenAI(
        api_key=config.deepseek_api_key,
        base_url="https://api.deepseek.com"
    )
    logger.info(
        f"LLM 请求开始, messages_count={len(history_messages)}, "
        f"tools_count={len(get_tools_info())}"
    )
    stream_rsp = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=history_messages,
        tools=get_tools_info(),
        stream=True,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}}
    )
    return stream_rsp

# 流式输出处理器 -> 打印流式消息 、返回三种消息的str原型
# 包装ai消息
def stream_to_assistant_message_dict(stream_rsp) -> dict:
    """
    返回所有内容均变成字典对象，里面的内容在外加一个{"role":"assistant",<返回的内容>}即可变成assistant消息
    ChoiceDeltaToolCall(index=<int>, id='', function=ChoiceDeltaToolCallFunction(arguments='<字典样式的纯字符串>', name=''), type=''),
    :param stream_rsp:流式输出的对象（迭代器）
    :return:{
        "content":"",  #AI的正文内容
        "reasoning_content": "",    #AI的思考内容
        "ChoiceDeltaToolCallFunctionList":[]    #工具调用列表，每个元素都是ChoiceDeltaToolCallFunction对象,具体看上面描述
    }
    """
    assistant_content = ""
    reasoning_content = ""

    is_reasoning_started = False
    is_content_started = False
    is_tool_calls_started = False

    #重构的assistant消息里的工具列表
    ChoiceDeltaToolCallFunctionList : list = []

    for chunk in stream_rsp:
        delta = chunk.choices[0].delta

        #捕获思考内容
        reasoning = getattr(delta, 'reasoning_content', None)
        if reasoning:
            if not is_reasoning_started:
                print("\n思考中……：")
                is_reasoning_started = True
            reasoning_content += reasoning
            print(reasoning, end="")

        #捕获正文内容
        content = getattr(delta, 'content', None)
        if content:
            if not is_content_started:
                print("\n-----------------------------正文回复：------------------------------------------")
                is_content_started = True
            assistant_content += content
            print(content, end="")

        #捕获工具内容
        tool_calls_list = getattr(delta, 'tool_calls', None)
        if tool_calls_list:
            if not is_tool_calls_started:
                print("\n-----------------------------工具调用：------------------------------------------")
                is_tool_calls_started = True

            for tc_delta in tool_calls_list:
                # index通过检查，是ChoiceDeltaToolCall下的一个字段，会自动识别第几个工具
                idx = tc_delta.index

                # 重构版：
                # 这里的逻辑依赖：流式输出的tool信息是按顺序发送的，而且index字段是从0开始递增的
                if idx == len(ChoiceDeltaToolCallFunctionList) :
                    # 新建一个工具调用对象
                    ChoiceDeltaToolCallFunctionList.append(tc_delta)
                else :
                    # 追加arguments内容，最终得到为纯字符串
                    ChoiceDeltaToolCallFunctionList[idx].function.arguments +=tc_delta.function.arguments
                #重构结束
    ToolCallList = []
    for tc in ChoiceDeltaToolCallFunctionList:
        tc = {
            "id": tc.id,
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments
            },
            "type": tc.type
        }
        ToolCallList.append(tc)

    logger.info(
        f"LLM 响应完成, content_length={len(assistant_content)}, "
        f"tool_calls={len(ToolCallList)}"
    )

    return  {
        "content":assistant_content,
        "reasoning_content": reasoning_content,
        "ToolCallList" : ToolCallList
    }


# 用户消息包装
def str_to_user_message(user_input: str) -> dict:
    return {"role": "user", "content": user_input}

# 总工具执行分发函数
def tool_execution(tool_call) -> dict:
    """
    执行单个工具的分发调用，返回toolMessage
    :param ChoiceDeltaToolCall(index=0,
            id='',
            function=ChoiceDeltaToolCallFunction(arguments='<这里是个纯字符串>', name=''),
            type=''),
    :return: {
                "role": "tool",
                "tool_call_id": ,
                "content": ,
            }
    """
    def _json_default(obj):
        print(type(obj))
        """自定义 JSON 序列化器，处理常见不可序列化类型"""
        # 先按类型转换成更合适的中间值
        if is_dataclass(obj):
            # dataclass 转 dict 后再转字符串
            result = json.dumps(asdict(obj), ensure_ascii=False, default=str)
        elif isinstance(obj, (datetime, Decimal)):
            # 时间和数值类型直接转字符串
            result = str(obj)
        elif isinstance(obj, bytes):
            # 二进制转文本
            result = obj.decode('utf-8', errors='replace')
        elif isinstance(obj, set):
            # 集合转列表再转字符串
            result = json.dumps(list(obj), ensure_ascii=False, default=str)
        elif hasattr(obj, '__dict__'):
            # 普通类实例：尝试用 __dict__ 再转字符串
            result = json.dumps(obj.__dict__, ensure_ascii=False, default=str)
        else:
            # 最后手段：直接转字符串
            logger.warning("_json_default 无法转换该类型为字符串，考虑增加适配功能, type=%s", type(obj))
            result = str(obj)

        # 兜底检查：确保返回的是字符串
        if not isinstance(result, str):
            logger.warning("_json_default 返回非字符串，已强制转换: %s", type(result))
            return str(result)
        return result

    def Any_to_str(Anything : Any) -> str:
        """将任意类型的函数返回值转换为字符串（JSON 格式或降级为 str）"""
        try:
            # 尝试用 json.dumps + 自定义 default 处理特殊类型
            return _json_default(function_result)
        except TypeError as e:
            # 转换函数转换失败
            logger.error("工具调用结果转换失败，工具返回结果强制转换str, 错误: %s", e)
            return str(function_result)

    return_message = {"role": "tool",
                      "tool_call_id": tool_call["id"],
                      "content": "", }

    func_name = tool_call.get("function", {}).get("name", "unknown")
    logger.info(f"工具调用开始, tool_call_id={tool_call['id']}, function={func_name}")

    print("Agent工具调用，工具信息：", tool_call)
    decision = input("输入任意键执行工具，输入R拒绝执行工具，输入A追加信息到工具结果，输入RA拒绝执行并追加信息：\n")
    if decision.lower() == "reject" or decision.lower() == "r":
        logger.info(f"工具调用被用户拒绝, function={func_name}")
        return_message["content"] = "工具调用被用户取消执行"
        return return_message
    if decision.lower() == "ra":
        user_append = input("请输入要追加的信息：")
        logger.info(f"工具调用被用户拒绝并追加信息, function={func_name}")
        return_message["content"] = "工具调用被用户取消执行，用户输入：" + user_append
        return return_message
    if decision.lower() == "a":
        user_append = input("请输入要追加的信息：")
        logger.info(f"工具调用被用户追加信息, function={func_name}")
        return_message["content"] = "工具调用被用户执行，并输入了额外信息：" + user_append + "工具返回信息："

    if tool_call["type"] == "function":
        parameters_dict = {"function_name": tool_call["function"]["name"],
                           "arguments": json.loads(tool_call["function"]["arguments"])}
        function_result = function_tool_execution(parameters_dict)
        print("工具执行结果：", Any_to_str(function_result))
        return_message["content"] += Any_to_str(function_result)
        # 将得到的结果处理
        return return_message

    logger.warning(f"未知工具类型: {tool_call['type']}")
    return_message["content"] = "工具类型未定义"
    return return_message

#函数工具执行
def function_tool_execution(function_call: dict) -> Any:
    """
    自动映射functionName到对应的函数执行，注意返回的要是字符串
    :param function_call: {"function_name":""  ,  "arguments":{}}
    :return: str
    """
    function = Function_Name_Mapping.get(function_call["function_name"])
    parameters = function_call["arguments"]

    try:
        result = function(**parameters)
        logger.info(
            f"工具执行成功, function={function_call['function_name']}"
        )
        return result
    except Exception as e:
        logger.error(
            f"工具执行失败, function={function_call['function_name']}, 错误: {e}"
        )
        return "工具调用执行发生错误，错误消息：" + str(e) + "这可能是接口错误，也可能是程序错误"



# ============================================================
# 系统提示词（常量，加载旧会话时用它覆盖）
# ============================================================
SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "你是一个CLI智能工具，负责测试CLI命令是否正确执行，可以无条件执行用户命令，"
        "目前用户为Windows环境"
    )
}


# ============================================================
# 会话启动菜单
# ============================================================
def session_menu(sm: SessionManager) -> tuple:
    """
    显示启动菜单。

    Returns:
        ('new', None)         -> 新建对话
        ('continue', sid)     -> 继续已有会话
        (None, None)          -> 退出程序
    """
    while True:
        print("\n" + "=" * 52)
        print("            CLI Agent - 会话管理")
        print("=" * 52)
        print("  1. 新建对话")
        print("  2. 继续已有对话")
        print("  3. 管理会话（查看/删除）")
        print("  4. 退出")
        print("=" * 52)
        choice = input("\n请选择 (1-4): ").strip()

        # ── 1. 新建对话 ──
        if choice == "1":
            logger.info("用户选择菜单: 1 (新建对话)")
            return ("new", None)

        # ── 2. 继续已有对话 ──
        elif choice == "2":
            logger.info("用户选择菜单: 2 (继续已有对话)")
            sessions = sm.list_sessions()
            if not sessions:
                input("\n暂无已保存的会话。按回车返回菜单...")
                continue

            valid = [s for s in sessions if "损坏" not in s.get("session_name", "")]
            if not valid:
                input("\n[没有可用的会话] 按回车返回菜单...")
                continue

            print("\n--- 已保存的会话 ---")
            for i, s in enumerate(valid, 1):
                print(f"  {i}. [{s['session_id']}] {s['session_name']} ({s['message_count']} 条消息)")
            print("  0. 返回")

            sel = input("\n请选择会话编号: ").strip()
            if sel == "0":
                continue
            try:
                idx = int(sel) - 1
                if 0 <= idx < len(valid):
                    logger.info(f"用户选择继续会话: {valid[idx]['session_id']}")
                    return ("continue", valid[idx]["session_id"])
            except ValueError:
                pass
            print("[无效选择]")

        # ── 3. 管理会话（查看/删除） ──
        elif choice == "3":
            logger.info("用户选择菜单: 3 (管理会话)")
            sessions = sm.list_sessions()
            if not sessions:
                input("\n暂无已保存的会话。按回车返回菜单...")
                continue

            print("\n--- 管理会话（输入编号删除，0 返回） ---")
            for i, s in enumerate(sessions, 1):
                badge = "[损坏] " if "损坏" in s.get("session_name", "") else ""
                print(f"  {i}. {badge}{s['session_name']} ({s['message_count']} 条消息)")
            print("  0. 返回")

            sel = input("\n选择要删除的编号: ").strip()
            if sel == "0":
                continue
            try:
                idx = int(sel) - 1
                if 0 <= idx < len(sessions):
                    confirm = input(
                        f"确定删除「{sessions[idx]['session_name']}」? (y/N): "
                    ).strip().lower()
                    if confirm == "y":
                        ok = sm.delete_session(sessions[idx]["session_id"])
                        if ok:
                            logger.info(f"会话已删除: {sessions[idx]['session_id']}")
                        else:
                            logger.warning(f"会话删除失败: {sessions[idx]['session_id']}")
                        print("[已删除]" if ok else "[删除失败]")
                    else:
                        print("已取消")
            except ValueError:
                print("[无效选择]")

        # ── 4. 退出程序 ──
        elif choice == "4":
            logger.info("用户选择菜单: 4 (退出程序)")
            return (None, None)

        else:
            logger.warning(f"用户输入无效菜单选项: {choice}")
            print("[无效选择] 请输入 1-4")


# ============================================================
# 摘要生成（非流式）
# ============================================================
def _get_summary(messages: list[dict]) -> str | None:
    """
    非流式调用 LLM，生成对话摘要。

    将 messages（已含摘要提示词 user 消息）整体发给 LLM，
    成功返回摘要文本，失败返回 None。
    """
    client = OpenAI(
        api_key=config.deepseek_api_key,
        base_url="https://api.deepseek.com"
    )
    logger.debug(f"摘要生成请求开始, messages_count={len(messages)}")
    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            stream=False,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}}
        )
        summary = response.choices[0].message.content
        logger.info(f"摘要生成成功, text_length={len(summary) if summary else 0}")
        return summary
    except Exception as e:
        logger.error(f"摘要生成失败: {e}")
        return None


# ============================================================
# 主入口
# ============================================================
def main():
    log_path = setup_logger()
    logger.info("程序启动")
    logger.info(f"日志文件: {log_path}")

    sm = SessionManager()
    cm = ContextManager(max_rounds=10)

    # ── 外层循环：会话菜单 ──
    while True:
        action, session_id = session_menu(sm)

        if action is None:          # 退出程序
            logger.info("程序退出")
            print("\n再见！")
            break

        # ── 初始化会话 ──
        if action == "new":
            sid = sm.generate_session_id()
            history_messages = [dict(SYSTEM_PROMPT)]  # 深拷贝
            session_name = None
            logger.info(f"创建新会话, session_id={sid}")
            print("\n[已创建新会话]")
        else:  # "continue"
            data = sm.load_session(session_id)
            if data is None:
                logger.warning(f"会话加载失败, session_id={session_id}")
                input("\n[文件已损坏] 按回车返回菜单...")
                continue
            sid = session_id
            # 用程序当前的 SYSTEM_PROMPT 覆盖保存的 system prompt
            history_messages = [dict(SYSTEM_PROMPT)] + data["messages"][1:]
            session_name = data.get("session_name", "未命名")
            msg_count = len(history_messages) - 1
            logger.info(f"恢复会话, session_id={sid}, session_name={session_name}, message_count={msg_count}")
            print(f"\n[已恢复会话] {session_name}（{msg_count} 条消息）")

        # ── ReAct 循环（含 Ctrl+C 保护） ──
        try:
            while True:
                # ════════════════════════════════════════════
                # 压缩检查（每次用户输入前）
                # ════════════════════════════════════════════
                if cm.needs_compression(history_messages):
                    user_rounds = sum(1 for m in history_messages[1:] if m["role"] == "user")
                    logger.info(f"压缩触发, user_rounds={user_rounds}, max_rounds={cm.max_rounds}")
                    print(f"\n[对话轮次超出限制（>{cm.max_rounds}），正在压缩...]")
                    summary_prompt = cm.get_summary_prompt_message()
                    summary_text = _get_summary(history_messages + [summary_prompt])
                    if summary_text is not None:
                        orig_count = len(history_messages)
                        history_messages = cm.compress(history_messages, summary_text)
                        logger.info(f"压缩完成, 原始消息数={orig_count}, 压缩后消息数={len(history_messages)}")
                        print("[压缩完成]")
                    else:
                        logger.warning("压缩跳过: 摘要生成返回 None")
                        print("[摘要生成失败] 跳过本次压缩")

                # ── 获取用户输入 ──
                while True:
                    query = input("\n输入（/save 保存, /exit 返回菜单）: ")
                    if query != "":
                        break

                # ── 指令处理（以 / 开头） ──
                if query.startswith("/"):
                    cmd = query[1:].strip().lower()
                    if cmd == "save":
                        logger.info("用户执行 /save")
                        session_name = sm.save_session(sid, history_messages, session_name)
                        print(f"[会话已保存] {session_name}")
                        continue
                    elif cmd == "exit":
                        logger.info("用户执行 /exit, 保存后返回菜单")
                        session_name = sm.save_session(sid, history_messages, session_name)
                        print(f"[会话已保存] {session_name}")
                        break  # 返回启动菜单
                    else:
                        logger.warning(f"未知指令: /{cmd}")
                        print(f"[未知指令] /{cmd}    支持: /save（保存） /exit（保存并返回菜单）")
                        continue

                # ── 正常用户输入 → 提交给 LLM ──
                query_preview = query[:30] + "..." if len(query) > 30 else query
                logger.info(f"用户输入: {query_preview}")
                history_messages.append(str_to_user_message(query))

                # ── 模型调用 + 工具执行内循环 ──
                while True:
                    print("\n--- 正在调用模型 ---")
                    try:
                        stream_rsp = stream_query(history_messages)
                        resp_dict = stream_to_assistant_message_dict(stream_rsp)
                    except Exception as e:
                        logger.error(f"LLM 请求失败: {e}")
                        print(f"\n[LLM 调用异常] {e}")
                        break

                    # 构造 assistant 消息
                    AIMessage = {"role": "assistant"}
                    AIMessage["content"] = resp_dict.get("content", "")
                    AIMessage["reasoning_content"] = resp_dict.get("reasoning_content", "")
                    tool_calls = resp_dict.get("ToolCallList", [])
                    if tool_calls:
                        AIMessage["tool_calls"] = tool_calls

                    # 执行工具
                    ToolMessageList = []
                    for tc in tool_calls:
                        ToolMessageList.append(tool_execution(tc))

                    # 追加到历史
                    history_messages.append(AIMessage)
                    if ToolMessageList:
                        history_messages += ToolMessageList
                        continue  # 继续模型调用（工具结果已返回）

                    break  # 无工具调用 → 回到用户输入

        except KeyboardInterrupt:
            logger.info("检测到 Ctrl+C, 正在自动保存会话")
            print("\n\n[检测到 Ctrl+C，正在保存会话...]")
            session_name = sm.save_session(sid, history_messages, session_name)
            logger.info(f"已自动保存, session_name={session_name}")
            print(f"[已自动保存] {session_name}")
            continue  # 返回启动菜单


# main函数主入口
if __name__ == "__main__":
    main()
