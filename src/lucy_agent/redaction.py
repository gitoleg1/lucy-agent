import re

SECRET_PATTERNS = [
    re.compile(
        r"(?i)(x-api-key|authorization|password|passphrase|token)\s*[:=]\s*([^\s]+)"
    ),
    re.compile(r"(?i)(AGENT_API_KEY)=([^\s]+)"),
]


def redact(text: str | None) -> str | None:
    if text is None:
        return None
    redacted = text
    for pat in SECRET_PATTERNS:
        redacted = pat.sub(lambda m: f"{m.group(1)}=<REDACTED>", redacted)
    return redacted
