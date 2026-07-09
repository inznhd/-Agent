from __future__ import annotations

import logging
import math
import re
import traceback
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 数据结构定义
# ──────────────────────────────────────────────
@dataclass
class CalculateResult:
    """计算器执行结果"""
    expression: str            # 原始表达式
    result: float | int | None  # 计算结果
    error: str | None          # 错误信息（成功时为 None）
    duration_ms: int           # 执行耗时（毫秒）


# 白名单：允许的 math 模块函数
_MATH_FUNCS = {
    "abs": abs,
    "round": round,
    "int": int,
    "float": float,
    "sqrt": math.sqrt,
    "pow": pow,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "ceil": math.ceil,
    "floor": math.floor,
    "pi": math.pi,
    "e": math.e,
    "degrees": math.degrees,
    "radians": math.radians,
}

# 安全全局命名空间
_SAFE_GLOBALS = {
    "__builtins__": {},
    **_MATH_FUNCS,
}


def _is_safe_expression(expr: str) -> bool:
    """检查表达式是否只包含安全字符，防止注入"""
    # 允许：数字、运算符、括号、空格、小数点、数学函数名
    allowed = re.compile(r'^[\d\s+\-*/().,%_a-zA-Z]+$')
    return bool(allowed.match(expr))


def calculate(
    expression: str,
    *,
    precision: int | None = None,
) -> CalculateResult:
    """
    安全执行数学计算，返回结构化结果。

    支持的运算符: +, -, *, /, //, %, **
    支持的函数: sqrt, pow, sin, cos, tan, log, log10, exp, ceil, floor, abs, round 等

    Args:
        expression: 数学表达式字符串，如 "2 + 2", "sqrt(16)", "(3.14 * 5 ** 2)"
        precision:    小数精度（保留几位小数），None 表示不截断

    Returns:
        CalculateResult: 结构化计算结果
    """
    import time
    start = time.perf_counter()

    logger.debug(f"计算开始: expression={expression!r}, precision={precision}")

    # 1. 安全检查
    if not _is_safe_expression(expression):
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.warning(f"计算错误 (不安全表达式): expression={expression!r}")
        return CalculateResult(
            expression=expression,
            result=None,
            error=f"表达式包含不安全的字符: {expression!r}",
            duration_ms=duration_ms,
        )

    try:
        # 2. 执行计算（在受限命名空间中）
        raw_result = eval(expression, _SAFE_GLOBALS, {})

        # 3. 处理精度
        if precision is not None and isinstance(raw_result, float):
            result = round(raw_result, precision)
        else:
            result = raw_result

        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.debug(f"计算成功: expression={expression!r}, result={result}, duration_ms={duration_ms}")
        return CalculateResult(
            expression=expression,
            result=result,
            error=None,
            duration_ms=duration_ms,
        )

    except ZeroDivisionError:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.warning(f"计算错误 (除零): expression={expression!r}")
        return CalculateResult(
            expression=expression,
            result=None,
            error="除零错误: 除数不能为 0",
            duration_ms=duration_ms,
        )
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error(f"计算异常: expression={expression!r}, 错误={type(e).__name__}: {e}")
        return CalculateResult(
            expression=expression,
            result=None,
            error=f"计算错误: {type(e).__name__}: {e}",
            duration_ms=duration_ms,
        )
