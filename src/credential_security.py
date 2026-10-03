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
# Literal delimiters avoid both quadratic scheme matching and blind spots
# when a log prefix ends in digits/punctuation. This masks URL-like text; it
# does not validate schemes. Every authority scan ends before the next ://.
USERINFO_URL = re.compile(r"://")
AUTHORITY_END = re.compile(r"[/\s]")
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


def _redact_userinfo(value):
    if "://" not in value or "@" not in value:
        return value

    pieces = []
    through = 0
    for match in USERINFO_URL.finditer(value):
        start = match.end()
        boundary = AUTHORITY_END.search(value, start)
        end = boundary.start() if boundary else len(value)
        authority = value[start:end]
        marker = authority.rfind("@")
        if marker >= 0 and ":" in authority[:marker]:
            pieces.extend((value[through:start], REDACTED))
            through = start + marker
    if not pieces:
        return value
    pieces.append(value[through:])
    return "".join(pieces)


def redact_text(text):
    decoded = text
    userinfo_changed = False
    for step in range(4):
        # Parse JSON before touching URL text, so a URL authority can never
        # consume punctuation or another field from its serialized siblings.
        if decoded.lstrip().startswith(("{", "[")):
            try:
                duplicate_keys = False

                def object_pairs(pairs):
                    nonlocal duplicate_keys
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            duplicate_keys = True
                        result[key] = value
                    return result

                parsed = json.loads(decoded, object_pairs_hook=object_pairs)
                cleaned = sanitize(parsed)
                # Never return a discarded duplicate value verbatim: it may
                # contain a credential even though the last value is harmless.
                if duplicate_keys or cleaned != parsed:
                    return json.dumps(
                        cleaned, ensure_ascii=False, separators=(",", ":")
                    )
                return decoded if userinfo_changed else text
            except (ValueError, TypeError):
                pass
        # Mask credentials before percent-decoding can turn an encoded
        # password slash/space/newline into an apparent URL boundary.
        protected = _redact_userinfo(decoded)
        userinfo_changed = userinfo_changed or protected != decoded
        decoded = protected
        if step == 3:
            break
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value

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
        return _redact_userinfo(value)

    safe_decoded = redact(decoded)
    return safe_decoded if userinfo_changed or text == decoded or safe_decoded != decoded else redact(text)


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
                    def secret_field(key):
                        decoded_key = str(key)
                        for _ in range(3):
                            next_key = unquote(decoded_key)
                            if next_key == decoded_key:
                                break
                            decoded_key = next_key
                        return SECRET_KEY.fullmatch(re.sub(r"[-_\s]", "", decoded_key)) or re.search(
                            r"(?:^|_)(?:API_KEY|TOKEN|SECRET|SECRET_KEY|PASSWORD)$", decoded_key
                        )

                    return {
                        (redact_text(key) if isinstance(key, str) else key): REDACTED
                        if secret_field(key)
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
