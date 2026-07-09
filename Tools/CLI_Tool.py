from __future__ import annotations

import logging
from dataclasses import dataclass
import os
import subprocess
import time
from typing import Mapping, Sequence

logger = logging.getLogger(__name__)

# Define a data class to store the results of a CLI command execution
@dataclass
class RunResult:
    args: str | list[str]  # The command arguments used for execution
    returncode: int | None  # The return code of the command, or None if not applicable
    stdout: str  # The standard output of the command
    stderr: str  # The standard error output of the command
    duration_ms: int  # The duration of the command execution in milliseconds
    timed_out: bool  # Whether the command timed out
    error: str | None  # Any error message or exception name if an error occurred

# Normalize the command input to ensure it is in the correct format for subprocess
# Accepts a string, PathLike object, or a sequence of these and returns a normalized format
# 把所有各种各样的传入路径格式全部转换为str或者[str]
def _normalize_command(command: str | os.PathLike | Sequence[str | os.PathLike]) -> str | list[str]:
    if isinstance(command, (list, tuple)):
        return [os.fspath(part) for part in command]
    return os.fspath(command)

# Convert the output of subprocess to a string, handling encoding and errors
# Ensures compatibility with both text and binary outputs
def _coerce_text(value: object | None, *, text: bool, encoding: str, errors: str) -> str:
    if value is None:
        return ""
    if text:
        return value if isinstance(value, str) else str(value)
    if isinstance(value, bytes):
        return value.decode(encoding, errors)
    return str(value)

# Execute a CLI command and return structured results
# Supports various options like timeout, working directory, environment variables, and shell execution
def run_cli(
    command: str | os.PathLike | Sequence[str | os.PathLike],
    *,
    timeout: float | None = None,  # Maximum time to wait for the command to complete
    cwd: str | os.PathLike | None = None,  # Working directory for the command
    env: Mapping[str, str] | None = None,  # Environment variables for the command
    shell: bool | None = None,  # Whether to execute the command in a shell
    text: bool = True,  # Whether to treat output as text
    encoding: str = "gbk",  # Encoding for text output
    errors: str = "replace",  # Error handling strategy for decoding
) -> RunResult:
    """Run a CLI command and return structured results for agent consumption."""
    normalized = _normalize_command(command)
    if shell is None:
        shell = isinstance(normalized, str)

    cmd_preview = normalized if isinstance(normalized, str) else " ".join(normalized)
    logger.debug(f"CLI 执行开始: command={cmd_preview!r}, cwd={cwd}, timeout={timeout}")

    start = time.perf_counter()
    try:
        # Run the command and capture its output
        completed = subprocess.run(
            normalized,
            capture_output=True,
            text=text,
            encoding=encoding if text else None,
            errors=errors if text else None,
            timeout=timeout,
            cwd=os.fspath(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            shell=shell,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        error = None
        if completed.returncode != 0:
            error = f"Command exited with code {completed.returncode}"
        logger.debug(f"CLI 执行完成: returncode={completed.returncode}, duration_ms={duration_ms}")
        return RunResult(
            args=completed.args if isinstance(completed.args, str) else list(completed.args),
            returncode=completed.returncode,
            stdout=_coerce_text(completed.stdout, text=text, encoding=encoding, errors=errors),
            stderr=_coerce_text(completed.stderr, text=text, encoding=encoding, errors=errors),
            duration_ms=duration_ms,
            timed_out=False,
            error=error,
        )
    except subprocess.TimeoutExpired as exc:
        # Handle timeout exceptions
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.warning(f"CLI 执行超时: command={cmd_preview!r}, timeout={timeout}s")
        return RunResult(
            args=normalized if isinstance(normalized, str) else list(normalized),
            returncode=None,
            stdout=_coerce_text(exc.stdout, text=text, encoding=encoding, errors=errors),
            stderr=_coerce_text(exc.stderr, text=text, encoding=encoding, errors=errors),
            duration_ms=duration_ms,
            timed_out=True,
            error="Command timed out",
        )
    except FileNotFoundError as exc:
        # Handle file not found exceptions
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error(f"CLI 执行失败 (文件未找到): command={cmd_preview!r}, 错误={exc}")
        return RunResult(
            args=normalized if isinstance(normalized, str) else list(normalized),
            returncode=None,
            stdout="",
            stderr=str(exc),
            duration_ms=duration_ms,
            timed_out=False,
            error="File not found",
        )
    except Exception as exc:  # Catch-all for unexpected exceptions
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error(f"CLI 执行异常: command={cmd_preview!r}, 错误={exc.__class__.__name__}: {exc}")
        return RunResult(
            args=normalized if isinstance(normalized, str) else list(normalized),
            returncode=None,
            stdout="",
            stderr=str(exc),
            duration_ms=duration_ms,
            timed_out=False,
            error=exc.__class__.__name__,
        )
