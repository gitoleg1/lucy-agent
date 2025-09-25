import asyncio
import os
from typing import Dict

from .redaction import redact


def _env_merge(env: Dict[str, str] | None) -> Dict[str, str]:
    base = dict(os.environ)
    if env:
        base.update(env)
    return base


def normalize_command(cmd: str | list[str]) -> list[str]:
    if isinstance(cmd, str):
        return ["bash", "-lc", cmd]
    return cmd


async def run_shell(
    cmd: str | list[str],
    workdir: str | None = None,
    env: Dict[str, str] | None = None,
    timeout: int = 600,
):
    argv = normalize_command(cmd)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=workdir or None,
        env=_env_merge(env),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        raise
    stdout = stdout_b.decode(errors="ignore")
    stderr = stderr_b.decode(errors="ignore")
    return proc.returncode, redact(stdout), redact(stderr)
