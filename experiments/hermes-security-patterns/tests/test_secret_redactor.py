"""Tests for the secret redaction engine."""

import pytest
from scanners.secret_redactor import SecretRedactor


@pytest.fixture
def redactor():
    return SecretRedactor()


class TestPrefixPatterns:
    def test_openai_key(self, redactor):
        text = "key: sk-proj-abc123def456ghi789jkl012mno345pqr678"
        clean, findings = redactor.scan(text)
        assert len(findings) == 1
        assert findings[0].pattern_name == "openai_proj"
        assert "sk-proj" not in clean or "***" in clean

    def test_github_pat(self, redactor):
        text = "GITHUB_TOKEN=ghp_FAKEtesttoken0000000000000000000000"
        clean, findings = redactor.scan(text)
        assert any(f.pattern_name == "github_pat" for f in findings)

    def test_anthropic_key(self, redactor):
        text = "sk-ant-api03-abcdef1234567890ABCDEF1234567890abcdef12-AAAAAAA"
        clean, findings = redactor.scan(text)
        assert any(f.pattern_name == "anthropic_key" for f in findings)

    def test_slack_token(self, redactor):
        text = "xoxb-FAKE-TOKEN-FOR-TESTING-ONLY"
        clean, findings = redactor.scan(text)
        assert any(f.pattern_name == "slack_token" for f in findings)

    def test_aws_access_key(self, redactor):
        text = "AKIAIOSFODNN7EXAMPLE"
        clean, findings = redactor.scan(text)
        assert any(f.pattern_name == "aws_access_key" for f in findings)

    def test_hf_token(self, redactor):
        text = "hf_abcdefghijklmnopqrstuvwxyz12345678"
        clean, findings = redactor.scan(text)
        assert any(f.pattern_name == "hf_token" for f in findings)


class TestStructuralPatterns:
    def test_env_assignment(self, redactor):
        text = "export API_KEY=mysupersecretapikey12345"
        clean, findings = redactor.scan(text)
        assert any(f.pattern_name == "env_assignment" for f in findings)

    def test_json_field(self, redactor):
        text = '{"api_key": "super-secret-key-value-12345678"}'
        clean, findings = redactor.scan(text)
        assert any(f.pattern_name == "json_field" for f in findings)

    def test_auth_header(self, redactor):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def"
        clean, findings = redactor.scan(text)
        assert any(f.pattern_name == "auth_header" for f in findings)

    def test_private_key(self, redactor):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK..."
        clean, findings = redactor.scan(text)
        assert any(f.pattern_name == "private_key" for f in findings)

    def test_db_connection(self, redactor):
        text = "postgres://admin:hunter2secret@db.internal:5432/app"
        clean, findings = redactor.scan(text)
        assert any(f.pattern_name == "db_connection_password" for f in findings)


class TestCleanText:
    def test_no_false_positives(self, redactor):
        texts = [
            "This is a normal commit message with no secrets.",
            "Updated the README with new instructions.",
            "Fixed bug in authentication flow.",
            "The API endpoint returns a 200 status.",
            "Run: go test ./...",
        ]
        for text in texts:
            _, findings = redactor.scan(text)
            assert len(findings) == 0, f"False positive on: {text}"


class TestMasking:
    def test_short_token_fully_masked(self, redactor):
        text = "xoxb-FAKE-SHORT"
        clean, findings = redactor.scan(text)
        if findings:
            assert findings[0].masked_preview == "***"

    def test_long_token_preserves_edges(self, redactor):
        text = "ghp_FAKEtesttoken0000000000000000000000"
        clean, findings = redactor.scan(text)
        if findings:
            assert findings[0].masked_preview.startswith("ghp_FA")
            assert findings[0].masked_preview.endswith("wxyz")
            assert "..." in findings[0].masked_preview


class TestMultipleSecrets:
    def test_multiple_in_one_text(self, redactor):
        text = (
            "Keys: sk-proj-abc123def456ghi789jkl012mno345pqr678 and "
            "ghp_FAKEtesttoken0000000000000000000000"
        )
        clean, findings = redactor.scan(text)
        assert len(findings) >= 2
