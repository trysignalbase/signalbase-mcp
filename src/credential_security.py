"""Credential selection and sanitization for controlled MCP output/diagnostics.

Platform access logs are outside this module; header transport avoids new keyed
connector URLs but does not claim to prevent every external logging leak.
"""

import json
import re
from urllib.parse import unquote

REDACTED = "[REDACTED]"
SECRET_KEY = re.compile(
    r"^(authorization|proxyauthorization|xapikey|xapiinternal|apikey|token|accesstoken|refreshtoken|password|secret|clientsecret|cookie|setcookie)$",
    re.I,
)
KEY = re.compile(r"^ff_live_[A-Za-z0-9]{32}$")
PATHS = {
    "",
    "/v2",
    "/v2/brief",
    "/v2/recruiting",
    "/v3",
    "/v3/recruiting",
    "/v3/recruiting/request",
    "/v3/monitoring",
}


def redact_text(text):
    decoded = text
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    for candidate in (text, decoded):
        if candidate.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(candidate)
                cleaned = sanitize(parsed)
                if cleaned != parsed:
                    return json.dumps(
                        cleaned, ensure_ascii=False, separators=(",", ":")
                    )
            except (ValueError, TypeError):
                pass

    def redact(value):
        value = re.sub(r"ff_live_[A-Za-z0-9]+", REDACTED, value)
        value = re.sub(
            r"(/(?:api/)?mcp(?:/[a-z0-9_-]+)*/c/)[^/?#\s\"'<>]+",
            lambda match: match[1] + REDACTED,
            value,
            flags=re.I,
        )
        value = re.sub(
            r"\bBearer\s+[A-Za-z0-9._~+/%=-]+", "Bearer " + REDACTED, value, flags=re.I
        )
        value = re.sub(
            r"([?&](?:api[_-]?key|key|token|access[_-]?token|secret|password)=)[^&#\s\"'<>]*",
            lambda match: match[1] + REDACTED,
            value,
            flags=re.I,
        )
        value = re.sub(
            r"(\b(?:authorization|x-api-internal|x-api-key)\s*[\"']?\s*[:=]\s*[\"']?)[^\r\n,\"'}]+",
            lambda match: match[1] + REDACTED,
            value,
            flags=re.I,
        )
        return re.sub(
            r"([a-z][a-z0-9+.-]*://)[^/@\s]+:[^/@\s]+@",
            lambda match: match[1] + REDACTED + "@",
            value,
            flags=re.I,
        )

    safe_decoded = redact(decoded)
    return safe_decoded if safe_decoded != decoded else redact(text)


def sanitize(value):
    seen = set()

    def visit(current, depth=0):
        if depth > 64:
            return "[REDACTED: depth limit]"
        if isinstance(current, str):
            return redact_text(current)
        if isinstance(current, (dict, list, tuple, BaseException)):
            if id(current) in seen:
                return "[Circular]"
            seen.add(id(current))
            try:
                if isinstance(current, BaseException):
                    return visit(
                        {
                            "name": type(current).__name__,
                            "message": str(current),
                            "cause": current.__cause__,
                        },
                        depth + 1,
                    )
                if isinstance(current, dict):
                    return {
                        key: REDACTED
                        if SECRET_KEY.fullmatch(re.sub(r"[-_\s]", "", str(key)))
                        or re.search(
                            r"(?:^|_)(?:API_KEY|TOKEN|SECRET|SECRET_KEY|PASSWORD)$",
                            str(key),
                        )
                        else visit(item, depth + 1)
                        for key, item in current.items()
                    }
                return [visit(item, depth + 1) for item in current]
            finally:
                seen.remove(id(current))
        return current

    return visit(value)


class CredentialError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def request_credentials(authorization, raw_path):
    """Header transport is primary. Recognized keyed paths must agree with it.

    Preserve public discovery on ordinary paths and historical bare headers.
    Keyed paths are accepted only for known profiles and canonical key format.
    """
    path = unquote(raw_path).rstrip("/")
    path_key = None
    if "/c/" in path:
        profile_path, _, candidate = path.rpartition("/c/")
        if profile_path not in PATHS:
            raise CredentialError(400, "Unknown connector credential path")
        path_key = unquote(candidate)
        if not KEY.fullmatch(path_key):
            raise CredentialError(401, "Invalid connector URL credential")
        path = profile_path
    value = (authorization or "").strip()
    scheme, _, credential = value.partition(" ")
    header_key = (
        credential.strip()
        if scheme.lower() == "bearer"
        else value
        if value and not credential
        else ""
    )
    if path_key and value and not header_key:
        raise CredentialError(401, "Invalid connector authorization")
    if path_key and header_key and path_key != header_key:
        raise CredentialError(400, "Conflicting connector credentials")
    return header_key or path_key or "", path
