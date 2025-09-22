
from fastapi import APIRouter
from typing import Any, Dict, List, Optional, Union
import asyncio, asyncssh, time, traceback, json
from ..models import ActionRequest, ActionResult
from ..db import log_action

router = APIRouter()

def sh_quote(s: str) -> str:
    return "''" if not s else "'" + s.replace("'", "'\"'\"'") + "'"

def _normalize_command(cmd: Union[str, List[str], None], commands: Optional[List[str]] = None,
                       workdir: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> str:
    seq: List[str] = []
    if env: seq.append("export " + " ".join(f"{k}={sh_quote(v)}" for k, v in env.items()))
    if workdir: seq.append(f"cd {sh_quote(workdir)}")
    base: List[str] = []
    if isinstance(cmd, list): base += [str(x) for x in cmd if x]
    elif isinstance(cmd, str) and cmd.strip(): base.append(cmd.strip())
    if commands: base += [str(x) for x in commands if x]
    seq += base
    return " && ".join(seq) if seq else "true"

def _redact(p: Dict[str, Any]) -> Dict[str, Any]:
    q = dict(p or {})
    for k in ("password", "passphrase"):
        if q.get(k): q[k] = "***"
    if q.get("private_key"): q["private_key"] = f"***PEM({len(str(q['private_key']))} chars)***"
    if q.get("private_key_path"): q["private_key_path"] = "***PATH***"
    return q

async def _try_log(action: str, request: Any, params: Dict[str, Any],
                   success: bool, output: Optional[str], error: Optional[str],
                   meta: Optional[Dict[str, Any]] = None):
    try:
        rq = request.model_dump() if hasattr(request, "model_dump") else (
            request.dict() if hasattr(request, "dict") else {}
        )
        payload = {
            "params": params or {},
            "request": rq,
            "meta": meta or {},
            "success": bool(success)
        }
        if error:
            payload["error"] = error
        input_str = json.dumps(payload, ensure_ascii=False)
        status_str = "ok" if success else "error"
        await log_action(action, input_str, (output or ""), status_str)
    except Exception:
        # לא מפיל את הפעולה במקרה של כשל בלוגים
        pass

@router.post("/ssh", response_model=ActionResult)
async def run_ssh(req: ActionRequest):
    t0 = time.time()
    p: Dict[str, Any] = dict(getattr(req, "params", {}) or {})
    host, username = p.get("host"), p.get("username")
    if not host or not username:
        return ActionResult(status=False, output="", error="missing 'host' or 'username'")
    port = int(p.get("port") or 22)
    timeout = int(p.get("timeout") or 30)
    full_cmd = _normalize_command(p.get("command"), p.get("commands"), p.get("workdir"), p.get("env") or {})
    dry = bool(p.get("dry_run") or getattr(req, "dry_run", False))
    do_exec = (p.get("exec") is True)

    if dry or not do_exec:
        msg = f"[DRY-RUN] {username}@{host}:{port} → {full_cmd}"
        await _try_log("ssh", req, p, True, msg, None, {"dry_run": True, "duration": time.time()-t0})
        return ActionResult(status=True, output=msg, error=None)

    try:
        conn_params: Dict[str, Any] = {
            "host": host, "port": port, "username": username,
            "known_hosts": p.get("known_hosts", None), "login_timeout": timeout, "connect_timeout": timeout
        }
        if p.get("password"): conn_params["password"] = p["password"]
        if p.get("private_key_path"): conn_params["client_keys"] = [p["private_key_path"]]
        async with asyncssh.connect(**conn_params) as conn:
            res = await asyncio.wait_for(conn.run(full_cmd, check=False), timeout=timeout)
        out = (res.stdout or "") + (("\n"+res.stderr) if res.stderr else "")
        ok = (res.exit_status == 0)
        await _try_log("ssh", req, p, ok, out.strip(), None if ok else f"exit_status={res.exit_status}",
                       {"exit_status": res.exit_status, "duration": time.time()-t0})
        return ActionResult(status=ok, output=out, error=None if ok else "Command failed")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        await _try_log("ssh", req, p, False, "", err, {"trace": traceback.format_exc(), "duration": time.time()-t0})
        return ActionResult(status=False, output="", error=err)
