from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 数据结构定义
# ──────────────────────────────────────────────
@dataclass
class SearchResult:
    """单条搜索结果"""
    title: str
    snippet: str
    url: str = ""
    relevance: float = 1.0  # 0.0 ~ 1.0


@dataclass
class SearchResponse:
    """搜索工具的完整返回"""
    query: str                # 原始查询
    results: list[SearchResult]  # 搜索结果列表
    total_results: int        # 结果总数（mock 下等于 len(results)）
    error: str | None         # 错误信息
    duration_ms: int          # 执行耗时


# ──────────────────────────────────────────────
# Mock 知识库 —— 命中关键词返回预设结果
# ──────────────────────────────────────────────
_MOCK_KNOWLEDGE_BASE: dict[str, list[dict]] = {
    # Python / 编程
    "python": [
        {"title": "Python 官方文档", "snippet": "Python 是一种高级、解释型、通用的编程语言，以其简洁易读的语法而闻名。", "url": "https://docs.python.org/3/"},
        {"title": "Python 包索引 (PyPI)", "snippet": "PyPI 是 Python 第三方软件包的官方仓库，包含超过 50 万个包。", "url": "https://pypi.org/"},
    ],
    "pip install": [
        {"title": "pip 安装指南", "snippet": "使用 pip install <package> 安装 Python 包，或使用 -r requirements.txt 批量安装。", "url": "https://pip.pypa.io/"},
    ],
    # Git
    "git": [
        {"title": "Git 官方文档", "snippet": "Git 是一个分布式版本控制系统，用于跟踪文件的变更历史。", "url": "https://git-scm.com/doc"},
        {"title": "Git 常用命令速查", "snippet": "git clone, git commit, git push, git pull, git branch, git merge 等。", "url": "https://git-scm.com/docs"},
    ],
    # Docker
    "docker": [
        {"title": "Docker 文档", "snippet": "Docker 是一个容器化平台，允许开发者将应用及其依赖打包成轻量级容器。", "url": "https://docs.docker.com/"},
        {"title": "Docker Compose", "snippet": "Docker Compose 用于定义和运行多容器 Docker 应用。", "url": "https://docs.docker.com/compose/"},
    ],
}


def _search_mock(query: str, max_results: int = 5) -> list[dict]:
    """在 Mock 知识库中匹配查询，返回最多 max_results 条结果"""
    query_lower = query.lower().strip()

    # 精确匹配
    for keyword, results in _MOCK_KNOWLEDGE_BASE.items():
        if keyword in query_lower:
            return results[:max_results]

    # 模糊匹配：检查查询中是否包含任意关键词
    matched: list[dict] = []
    for keyword, results in _MOCK_KNOWLEDGE_BASE.items():
        if keyword == "default":
            continue
        if any(word in query_lower for word in keyword.split()):
            matched.extend(results)
    if matched:
        return matched[:max_results]

    # 兜底：返回默认结果，并将 query 动态填入
    return [
        {"title": f"关于「{query}」的搜索结果",
         "snippet": f"这是关于「{query}」的模拟搜索结果摘要，仅供参考。",
         "url": f"https://example.com/search?q={query}"},
    ][:max_results]


def search(
    query: str,
    *,
    max_results: int = 5,
    source: str = "mock",
) -> SearchResponse:
    """
    执行搜索查询，返回结构化结果（当前为 Mock 实现，无需联网）。

    Args:
        query:       搜索关键词
        max_results: 最大返回结果数（1-20，默认 5）
        source:      搜索源（当前仅支持 "mock"）

    Returns:
        SearchResponse: 结构化搜索结果
    """
    start = time.perf_counter()

    logger.debug(f"搜索开始: query={query!r}, source={source!r}, max_results={max_results}")

    # 参数校验
    if not query or not query.strip():
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.warning(f"搜索参数错误: 搜索查询不能为空")
        return SearchResponse(
            query=query,
            results=[],
            total_results=0,
            error="搜索查询不能为空",
            duration_ms=duration_ms,
        )

    max_results = max(1, min(20, max_results))

    try:
        if source == "mock":
            raw_results = _search_mock(query, max_results)
        else:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(f"搜索参数错误: 不支持的搜索源 {source!r}")
            return SearchResponse(
                query=query,
                results=[],
                total_results=0,
                error=f"不支持的搜索源: {source!r}（当前仅支持 'mock'）",
                duration_ms=duration_ms,
            )

        results = [
            SearchResult(
                title=r.get("title", "无标题"),
                snippet=r.get("snippet", ""),
                url=r.get("url", ""),
                relevance=1.0 - (i * 0.05),
            )
            for i, r in enumerate(raw_results)
        ]

        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.debug(f"搜索完成: query={query!r}, results={len(results)}, duration_ms={duration_ms}")
        return SearchResponse(
            query=query,
            results=results,
            total_results=len(results),
            error=None,
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error(f"搜索异常: query={query!r}, 错误={type(e).__name__}: {e}")
        return SearchResponse(
            query=query,
            results=[],
            total_results=0,
            error=f"搜索执行出错: {type(e).__name__}: {e}",
            duration_ms=duration_ms,
        )
