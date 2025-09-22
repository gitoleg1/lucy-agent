from __future__ import annotations
from typing import List, Dict, Any
import docker
import subprocess
import shlex


class DockerSkill:
    def __init__(self) -> None:
        self.client = docker.from_env()

    def ps(self, all: bool = False) -> List[Dict[str, Any]]:
        containers = self.client.containers.list(all=all)
        out: List[Dict[str, Any]] = []
        for c in containers:
            image = c.image.tags or [c.image.short_id]
            out.append(
                {
                    "id": c.short_id,
                    "name": c.name,
                    "image": image,
                    "status": getattr(c, "status", "unknown"),
                }
            )
        return out

    def logs(self, name: str, tail: int = 200) -> str:
        c = self.client.containers.get(name)
        return c.logs(tail=tail).decode(errors="ignore")

    def restart(self, name: str) -> dict:
        c = self.client.containers.get(name)
        c.restart()
        return {"ok": True}

    def compose(self, workdir: str, cmd: str = "up -d") -> str:
        argv = ["bash", "-lc", f"cd {shlex.quote(workdir)} && docker compose {cmd}"]
        out = subprocess.check_output(argv, stderr=subprocess.STDOUT)
        return out.decode(errors="ignore")
