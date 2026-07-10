# AI Prompt

我的风格偏向前期描述好所有的需求，提示让llm补充细节（包括用例需求、逻辑实现方案、代码修改方案），让llm出一个小任务的修改方案后，让他自己修改，最后检查验收

部分prompt：

- 现在我需要更多的工具： calculator  ，search（可 mock）。请先参考项目里的工具注册方式（包括每个工具包含名称、描述、参数 Schema），以及解析后的工具调用方法。给我一份具体的修改方案，包括各个工具的功能，如何并入现有的项目，需要修改哪些代码。请先给出一份方案我们讨论后再执行。

- 现在我们需要新增功能：session管理。比如用户 A 开了窗口 1：让 Agent 查天气记待办。用户 A 开了窗口 2：让 Agent 写周报记待办，这两个窗口应该是独立的session，用户A可以随时接着窗口1/2和继续聊，彼此不会影响。请给出session的设计方案、与用户的交互逻辑、以及代码上的实现方案。请先给出方案，不执行修改。

- 现在我们需要处理日志信息，需要为关键信息输出日志并保存在本地，请给出日志事件和等级，每一次程序打开就一份日志，时间戳作为文件名。现在给我一份修改计划，请不要开始修改。

---

# 问题解决记录

整个开发只在搭建Message中的`assistant`消息的时候出现过反复报错，传入内容不符合规范。

- 我先查看deepseek文档，文档只告知reasoning模式下调用工具后，assistant message要返回reasoning_context、tool_calls，但是没有说明具体返回格式。

- 开始自己尝试。刚开始尝试用纯字典构建，把所有需要的字段拼接放入。接口报错AIMessage里的`tool_calls`格式错误，后来手动多次尝试之后选择在`tool_calls`字段中返回整个接收到的函数调用对象。

- 这两天我重新尝试解析，成功把函数调用对象替换为字典（当初报错的原因是tool_calls的`type`字段没有提供）

---

# 项目开发历程

### 1、源于旧项目

这个项目其实是源自于我自己实现过的一个最简cli agent上开发的。初始项目是由**Claude code辅助完成cli工具函数的编写**，**自己实现流式输出的接口解析、工具调用、上下文消息封装、按规范格式请求llm**

解决问题的顺序如下：

1. 从deepseek接口文档直接复制快速开始的代码（只有硬编码的单轮非流式输出消息，具体在文件底部）

2. 搭建ReAct框架（while循环），构建函数框架（流式输出解析、上下文消息包装、工具执行和消息返回）

3. 使用测试代码获取完整的流式输出返回结果，然后编写流式输出解析函数

4. 实现正确的拼接上下文格式。

### 2、按要求补充开发功能

这两天按照飞书文档的要求补充更多的功能。这些功能都是使用自己搭建的coding agent开发完成的。

1. 补充更多的工具和工具注册

2. 开发session管理功能（包括文件存储、session全量召回）

3. 开发上下文压缩功能（包括轮次限制、基础的压缩）

4. 补充日志保存功能

5. 测试所有的功能。（最后是用例编写和综合整体测试，在上面开发的过程中有局部测试的习惯）

---

---

```python
# Please install OpenAI SDK first: `pip3 install openai`
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get('DEEPSEEK_API_KEY'),
    base_url="https://api.deepseek.com")

response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello"},
    ],
    stream=False,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}}
)

print(response.choices[0].message.content)
```
