"""Security tests — verify defenses against common attack vectors."""

import pytest

from aria.dsremo.core.security import (
    RateLimiter,
    generate_api_key,
    sanitize_identifier,
    sanitize_string,
    sign_telemetry,
    validate_payload_size,
    verify_api_key,
    verify_signature,
)


class TestApiKeyManagement:
    def test_generate_returns_pair(self):
        plaintext, hashed = generate_api_key()
        assert plaintext.startswith("stl_")
        assert len(hashed) == 64  # SHA-256 hex

    def test_verify_correct_key(self):
        plaintext, hashed = generate_api_key()
        assert verify_api_key(plaintext, hashed)

    def test_verify_wrong_key(self):
        _, hashed = generate_api_key()
        assert not verify_api_key("stl_wrong_key", hashed)

    def test_keys_are_unique(self):
        key1, _ = generate_api_key()
        key2, _ = generate_api_key()
        assert key1 != key2


class TestHmacSigning:
    def test_sign_and_verify(self):
        payload = {"satellite_id": "SAT-01", "value": 7.4}
        secret = "test_secret_key"
        sig = sign_telemetry(payload, secret)
        assert verify_signature(payload, sig, secret)

    def test_tampered_payload_fails(self):
        payload = {"satellite_id": "SAT-01", "value": 7.4}
        secret = "test_secret_key"
        sig = sign_telemetry(payload, secret)

        # Tamper with payload
        payload["value"] = 999.0
        assert not verify_signature(payload, sig, secret)

    def test_wrong_secret_fails(self):
        payload = {"satellite_id": "SAT-01", "value": 7.4}
        sig = sign_telemetry(payload, "secret_a")
        assert not verify_signature(payload, sig, "secret_b")

    def test_deterministic_signatures(self):
        payload = {"b": 2, "a": 1}  # field order shouldn't matter
        sig1 = sign_telemetry(payload, "secret")
        sig2 = sign_telemetry({"a": 1, "b": 2}, "secret")
        assert sig1 == sig2  # canonical JSON ensures this


class TestSanitization:
    def test_sanitize_string_strips_xss(self):
        result = sanitize_string('<script>alert("xss")</script>')
        # Dangerous chars (<, >, ", ') are stripped; safe words like 'alert' remain
        assert "<" not in result
        assert ">" not in result
        assert '"' not in result

    def test_sanitize_string_strips_sql(self):
        result = sanitize_string("'; DROP TABLE telemetry; --")
        assert "DROP" not in result
        assert "'" not in result

    def test_sanitize_string_enforces_length(self):
        long = "a" * 500
        result = sanitize_string(long, max_length=100)
        assert len(result) <= 100

    def test_sanitize_identifier_allows_valid(self):
        assert sanitize_identifier("SAT-01") == "SAT-01"
        assert sanitize_identifier("battery_voltage") == "battery_voltage"
        assert sanitize_identifier("test.param.1") == "test.param.1"

    def test_sanitize_identifier_strips_invalid(self):
        assert sanitize_identifier("SAT<>01") == "SAT01"
        assert sanitize_identifier("param; DROP") == "paramDROP"


class TestRateLimiter:
    def test_allows_under_limit(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert limiter.is_allowed("key1")

    def test_blocks_over_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            assert limiter.is_allowed("key1")
        assert not limiter.is_allowed("key1")

    def test_different_keys_independent(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        assert limiter.is_allowed("key1")
        assert limiter.is_allowed("key1")
        assert not limiter.is_allowed("key1")
        assert limiter.is_allowed("key2")  # different key, fresh limit

    def test_reset(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("key1")
        assert not limiter.is_allowed("key1")
        limiter.reset("key1")
        assert limiter.is_allowed("key1")


class TestPayloadSize:
    def test_within_limit(self):
        assert validate_payload_size(b"x" * 1000, max_bytes=1_048_576)

    def test_exceeds_limit(self):
        assert not validate_payload_size(b"x" * 2_000_000, max_bytes=1_048_576)

    def test_empty_payload(self):
        assert validate_payload_size(b"", max_bytes=1_048_576)
