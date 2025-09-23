import subprocess
from pathlib import Path
from typing import Tuple


def ensure_run_dir(run_id: str) -> Path:
    base = Path.home() / ".local" / "share" / "lucy-agent" / "runs" / run_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def run_shell_command(run_id: str, cmd: str) -> Tuple[int, str, str]:
    rd = ensure_run_dir(run_id)
    stdout_file = rd / "stdout.log"
    stderr_file = rd / "stderr.log"
    with stdout_file.open("wb") as out, stderr_file.open("wb") as err:
        p = subprocess.Popen(["/bin/bash", "-lc", cmd], stdout=out, stderr=err)
        ret = p.wait()
    return ret, str(stdout_file), str(stderr_file)
