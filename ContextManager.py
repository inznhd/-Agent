from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


class ContextManager:
    """
    对话轮次管理与压缩。

    一轮 = 一条 user 消息及其后直至下一条 user 消息之前的所有消息。
    超出 max_rounds 时触发压缩：将旧轮次用 LLM 摘要替代，
    保留最新一轮完整消息（工具结果截断至 30 字）。
    """

    def __init__(self, max_rounds: int = 10):
        self.max_rounds = max_rounds

    # ──────────────────────────────────────────────
    # 轮次检查
    # ──────────────────────────────────────────────

    def needs_compression(self, messages: list[dict]) -> bool:
        """
        检查当前消息列表是否需要压缩。

        判断依据：跳过 system prompt（index 0），
        统计 user 消息的数量 = 轮次数。
        """
        user_rounds = sum(1 for msg in messages[1:] if msg["role"] == "user")
        need = user_rounds > self.max_rounds
        if need:
            logger.debug(
                f"压缩触发, user_rounds={user_rounds}, max_rounds={self.max_rounds}"
            )
        return need

    # ──────────────────────────────────────────────
    # 摘要提示词消息
    # ──────────────────────────────────────────────

    def get_summary_prompt_message(self) -> dict:
        """
        返回摘要提示词模板（作为 user 消息）。

        该消息会被追加到原 messages 数组末尾后发给 LLM，
        LLM 基于完整对话历史生成摘要。
        """
        return {
            "role": "user",
            "content": (
                "请对以上对话进行摘要，提取以下关键信息：\n"
                "1. 用户的目标和需求\n"
                "2. 已执行的操作和结果\n"
                "3. 重要发现和结论\n"
                "4. 当前任务状态\n\n"
                "请用简洁的中文概括（200 字以内）："
            ),
        }

    # ──────────────────────────────────────────────
    # 压缩执行
    # ──────────────────────────────────────────────

    def compress(self, messages: list[dict], summary_text: str) -> list[dict]:
        """
        执行压缩，构建新的消息列表。

        结构::
            [system,
             {"role": "user", "content": "（之前对话的摘要）...summary_text..."},
             ...最新一轮（工具结果截断至 30 字）]

        Args:
            messages:     原始消息列表（含 system）
            summary_text: LLM 返回的摘要文本

        Returns:
            压缩后的新消息列表
        """
        orig_count = len(messages)

        # 1. 找到最新一轮的起始位置（最后一条 user 消息的索引）
        last_user_idx = self._find_last_user_index(messages)

        # 2. 提取最新一轮消息
        latest_round = messages[last_user_idx:]

        # 3. 截断最新一轮中的工具结果
        truncated_latest = self._truncate_tool_results(latest_round, max_len=30)

        # 4. 构建压缩结果
        compressed = [
            messages[0],  # system prompt
            {
                "role": "user",
                "content": f"（以下是之前对话的关键信息摘要）\n{summary_text}",
            },
        ] + truncated_latest

        logger.info(
            f"压缩完成, 原始消息数={orig_count}, 压缩后消息数={len(compressed)}"
        )
        return compressed

    # ──────────────────────────────────────────────
    # 内部工具
    # ──────────────────────────────────────────────

    @staticmethod
    def _find_last_user_index(messages: list[dict]) -> int:
        """从后向前找到最后一条 user 消息的索引（跳过 system prompt）"""
        for i in range(len(messages) - 1, 0, -1):
            if messages[i]["role"] == "user":
                return i
        logger.warning("未找到 user 消息, 使用 index=1 兜底")
        return 1  # 兜底

    @staticmethod
    def _truncate_tool_results(
        round_msgs: list[dict], max_len: int = 30
    ) -> list[dict]:
        """将一条消息列表中 role=tool 的 content 截断到 max_len 字"""
        result = []
        for msg in round_msgs:
            if msg["role"] == "tool" and len(msg.get("content", "")) > max_len:
                m = dict(msg)
                m["content"] = m["content"][:max_len] + "..."
                result.append(m)
            else:
                result.append(msg)
        return result
