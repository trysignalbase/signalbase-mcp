"""Normal MCP data must not turn credential redaction into a CPU amplifier."""
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

from credential_security import redact_text, sanitize


@pytest.mark.parametrize("prefix", ["", " ", "(URL ", "prefix: ", "\n"])
@pytest.mark.parametrize("scheme", ["https", "postgresql", "git+ssh", "CUSTOM-1.2"])
def test_url_authority_secrets_preserved_across_scheme_boundaries(prefix, scheme):
    url = f"{prefix}{scheme}://user:private-value@host.test:5432/path?not_secret=yes"
    for value in (url, quote(url, safe=""), quote(quote(url, safe=""), safe="")):
        result = redact_text(value)
        assert "private-value" not in result
        assert "[REDACTED]@host.test:5432/path" in result


def test_long_plain_identifiers_and_urls_finish_within_a_process_deadline():
    # Run in a child so reintroducing the old superlinear regex fails in
    # bounded time instead of hanging the whole test runner. No network.
    code = """
import json
from credential_security import redact_text
word = 'a' * 32768
for text in (word, word + '@example.test', 'https://' + word + '.test/path',
             word + ' https://user:secret@host.test/path'):
    result = redact_text(text)
    assert 'user:secret' not in result
    assert word in result
print(json.dumps({'completed': 4}))
"""
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0, 'src');\n" + code],
        cwd=root, capture_output=True, text=True, timeout=5, check=True,
    )
    assert json.loads(result.stdout) == {"completed": 4}


def test_nested_json_and_malformed_authorities_still_redact():
    values = ["https://:secret@host.test/", "https://user:secret@other@host.test/",
              "https://user:secret@host.test/next https://second:password@other.test/"]
    for value in values:
        safe = sanitize({"serialized": json.dumps({"url": value}), "token": "private-token"})
        encoded = json.dumps(safe)
        assert "secret" not in encoded and "password" not in encoded and "private-token" not in encoded
        assert json.loads(safe["serialized"])["url"].count("[REDACTED]") >= 1


@pytest.mark.parametrize("suffix", ["%23suffix", "%3Fsuffix", "%22suffix", "%2Fsuffix", "%20suffix", "%0Asuffix", "#suffix", "?suffix"])
def test_encoded_authority_password_stays_hidden_when_another_secret_changes_decoded_text(suffix):
    text = f"postgresql://user:privatePassword{suffix}@fixture.invalid/db Bearer opaque-secret"
    safe = redact_text(text)
    assert "privatePassword" not in safe
    assert "opaque-secret" not in safe
    assert safe.count("[REDACTED]") == 2


def test_json_urls_do_not_consume_other_fields_and_secret_keys_are_sanitized():
    ordinary = {"url": "https://public.test", "email": "public:name@example.test"}
    assert json.loads(redact_text(json.dumps(ordinary))) == ordinary
    encoded = {"url": "postgresql://user:private%2Fsuffix@host.test/db", "label": "retain this field"}
    for value in (json.dumps(encoded), quote(json.dumps(encoded), safe=""), json.dumps({"nested": json.dumps(encoded)})):
        safe = redact_text(value)
        assert "private" not in safe and "retain this field" in safe
        json.loads(safe)
    key = "ff_live_" + "a" * 32
    assert key not in redact_text(json.dumps({key: "value"}))


@pytest.mark.parametrize("secret", ["ff_live_" + "a" * 32, "postgresql://user:privatePassword@host/db"])
def test_discarded_duplicate_json_values_cannot_reappear_in_raw_passthrough(secret):
    raw = '{"value":' + json.dumps(secret) + ',"value":"harmless"}'
    for text in (raw, quote(raw,safe=""), json.dumps({"nested":raw})):
        safe = redact_text(text)
        assert secret not in safe and "privatePassword" not in safe
        json.loads(safe)


@pytest.mark.parametrize("key", ["api%5Fkey", "%61uthorization", "SERVICE_API%255FKEY"])
def test_percent_encoded_secret_field_names_are_recognized(key):
    safe = redact_text(json.dumps({key:"privateValue"}))
    assert "privateValue" not in safe
    assert list(json.loads(safe).values()) == ["[REDACTED]"]
