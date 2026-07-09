from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any


logger = logging.getLogger(__name__)


class SessionManager:
    """管理 Agent 会话的保存、加载、列举和删除"""

    def __init__(self, sessions_dir: str = "sessions"):
        self.sessions_dir = sessions_dir
        os.makedirs(sessions_dir, exist_ok=True)

    # ────────────────────────────────────────
    # 内部工具
    # ────────────────────────────────────────

    def _session_path(self, session_id: str) -> str:
        return os.path.join(self.sessions_dir, f"{session_id}.json")

    @staticmethod
    def generate_session_id() -> str:
        """以时间戳生成会话 ID，同时作为文件名"""
        sid = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.debug(f"生成会话 ID: {sid}")
        return sid

    @staticmethod
    def _auto_name(messages: list[dict]) -> str:
        """从第一条 user 消息截取前 20 个字符作为会话名"""
        for msg in messages:
            if msg.get("role") == "user":
                text = msg.get("content", "")
                display = text[:20].replace("\n", " ")
                return display + ("..." if len(text) > 20 else "")
        return "空会话"

    # ────────────────────────────────────────
    # 外部接口
    # ────────────────────────────────────────

    def list_sessions(self) -> list[dict]:
        """
        返回所有会话的元信息列表，按创建时间降序。

        每个元素::
            {
                "session_id": str,
                "session_name": str,
                "message_count": int,
                "created_at": str,
            }
        """
        sessions: list[dict] = []
        if not os.path.isdir(self.sessions_dir):
            return sessions

        for fname in os.listdir(self.sessions_dir):
            if not fname.endswith(".json"):
                continue
            sid = fname[:-5]  # 去掉 .json
            fpath = os.path.join(self.sessions_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append({
                    "session_id": data.get("session_id", sid),
                    "session_name": data.get("session_name", "未命名"),
                    "message_count": len(data.get("messages", [])),
                    "created_at": data.get("session_id", sid),
                })
            except (json.JSONDecodeError, OSError):
                # 文件损坏 —— 仍列出但标记
                sessions.append({
                    "session_id": sid,
                    "session_name": "[文件已损坏]",
                    "message_count": 0,
                    "created_at": sid,
                })

        sessions.sort(key=lambda s: s["created_at"], reverse=True)
        logger.debug(f"列举会话, 找到 {len(sessions)} 个会话文件")
        return sessions

    def save_session(
        self,
        session_id: str,
        messages: list[dict],
        session_name: str | None = None,
    ) -> str:
        """
        保存会话到 JSON 文件。

        Args:
            session_id:   会话 ID（也是文件名）
            messages:     完整的 messages 数组（纯 dict 结构）
            session_name: 会话名称，为 None 时自动从首条 user 消息生成

        Returns:
            str: 实际使用的 session_name
        """
        if session_name is None:
            session_name = self._auto_name(messages)

        data = {
            "session_id": session_id,
            "session_name": session_name,
            "messages": messages,
        }
        with open(self._session_path(session_id), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(
            f"会话已保存, session_id={session_id}, "
            f"session_name={session_name}, messages_count={len(messages)}"
        )
        return session_name

    def load_session(self, session_id: str) -> dict | None:
        """
        加载会话文件。

        Returns:
            成功时返回完整 dict（含 session_id, session_name, messages）；
            文件损坏/不存在时返回 None。
        """
        try:
            with open(self._session_path(session_id), "r", encoding="utf-8") as f:
                data = json.load(f)
            msg_count = len(data.get("messages", []))
            logger.info(f"会话已加载, session_id={session_id}, messages_count={msg_count}")
            return data
        except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
            logger.error(f"会话加载失败, session_id={session_id}, 错误: {type(e).__name__}")
            return None

    def delete_session(self, session_id: str) -> bool:
        """删除会话文件，成功返回 True。"""
        try:
            os.remove(self._session_path(session_id))
            logger.info(f"会话已删除, session_id={session_id}")
            return True
        except OSError as e:
            logger.warning(f"会话删除失败, session_id={session_id}, 错误: {type(e).__name__}")
            return False
