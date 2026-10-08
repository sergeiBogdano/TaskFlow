"""Defense in depth for text. Authorization and explicit field selection remain mandatory."""
import os
import re

REDACTED = '[секрет_скрыт]'
_LABEL = r'(?:password|passwd|pwd|пароль|пароля|паролем|token|токен|secret|секрет|api[_ -]?key|ключ[_ -]?api|authorization|cookie|session[_ -]?(?:id|token)|(?:client|access|refresh|bot|auth|private|ssh)[_ -]?(?:token|key|secret)|jwt)'
_ASSIGNMENT = re.compile(r'(?i)([\"\']?'+_LABEL+r'[\"\']?(?:\s|<[^>]+>)*(?::|=|—|-)(?:\s|<[^>]+>)*)([\"\'])(.*?)(\2)|([\"\']?'+_LABEL+r'[\"\']?(?:\s|<[^>]+>)*(?::|=|—|-)(?:\s|<[^>]+>)*)([^\s<>,;\"\']+)', re.S)
_PATTERNS = [
    re.compile(r'(?im)\b(?:Cookie|Set-Cookie|Authorization)\s*[:=]\s*[^\r\n]+'),
    re.compile(r'-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----.*?-----END (?:[A-Z ]*PRIVATE KEY)-----', re.S),
    re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+'),
    re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'),
    re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{16,})\b'),
    re.compile(r'\b\d{6,12}:[A-Za-z0-9_-]{30,}\b'),
    re.compile(r'(?i)(?:https?|postgres(?:ql)?(?:\+[a-z]+)?|mysql(?:\+[a-z]+)?|redis)://[^\s/@:]+:[^\s/@]+@[^\s<>\"\']+'),
    re.compile(r'(?i)([?&](?:password|token|secret|api_key|access_token)=)[^&\s<>\"\']+'),
]


def redact_text(text):
    if not isinstance(text, str):
        return text
    # Only replace values; environment names/values are never placed in prompts.
    for key, value in os.environ.items():
        if len(value) >= 8 and re.search(r'(?i)(secret|password|passwd|token|api[_-]?key|database_url|private_key)', key):
            text = text.replace(value, REDACTED)
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    text = _ASSIGNMENT.sub(lambda m: (m.group(1) or m.group(5)) + REDACTED, text)
    return text


def redact_value(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: REDACTED if re.fullmatch(_LABEL, str(key), re.I) else redact_value(item) for key, item in value.items()}
    return value
