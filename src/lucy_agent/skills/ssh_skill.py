from __future__ import annotations

import io
from typing import Optional, Tuple

import paramiko


def _load_pkey(private_key: str, passphrase: Optional[str] = None) -> paramiko.PKey:
    """
    מנסה לטעון מפתח פרטי מכל הסוגים הנפוצים לפי סדר:
    Ed25519 -> RSA -> ECDSA -> DSS
    """
    buf = io.StringIO(private_key)
    try:
        buf.seek(0)
        return paramiko.Ed25519Key.from_private_key(buf, password=passphrase)
    except Exception:
        pass
    try:
        buf.seek(0)
        return paramiko.RSAKey.from_private_key(buf, password=passphrase)
    except Exception:
        pass
    try:
        buf.seek(0)
        return paramiko.ECDSAKey.from_private_key(buf, password=passphrase)
    except Exception:
        pass
    buf.seek(0)
    return paramiko.DSSKey.from_private_key(buf, password=passphrase)


class SSHSkill:
    def run(
        self,
        host: str,
        user: str,
        cmd: str,
        port: int = 22,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
        passphrase: Optional[str] = None,
        timeout: int = 600,
    ) -> Tuple[int, str, str]:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = _load_pkey(private_key, passphrase) if private_key else None

        client.connect(
            hostname=host,
            port=port,
            username=user,
            password=password,
            pkey=pkey,
            timeout=timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        try:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
            rc = stdout.channel.recv_exit_status()
            out = stdout.read().decode(errors="ignore")
            err = stderr.read().decode(errors="ignore")
            return rc, out, err
        finally:
            client.close()
