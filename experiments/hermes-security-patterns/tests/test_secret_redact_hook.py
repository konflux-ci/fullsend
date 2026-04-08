"""Tests for the secret redaction PostToolUse hook."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).parent.parent / "hooks" / "secret_redact_posttool.py"


def run_hook(tool_name: str, tool_result: str) -> tuple[int, dict | None]:
    """Run the hook and return (exit_code, parsed_stdout)."""
    payload = json.dumps({
        "tool_name": tool_name,
        "tool_input": {},
        "tool_result": tool_result,
    })
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=5,
    )
    output = None
    if result.stdout.strip():
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return result.returncode, output


class TestPrefixPatterns:
    def test_openai_key(self):
        code, output = run_hook(
            "Bash",
            "The key is sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx here",
        )
        assert code == 0
        assert output is not None
        assert "sk-pro" in output["tool_result"]
        assert "abc123def456" not in output["tool_result"]

    def test_github_pat(self):
        code, output = run_hook(
            "Bash",
            "Token: ghp_FAKEtesttoken0000000000000000000000",
        )
        assert code == 0
        assert output is not None
        assert "ghp_FA" in output["tool_result"]
        assert "0000000000000000000000" not in output["tool_result"]

    def test_aws_access_key(self):
        code, output = run_hook("Bash", "AWS key: AKIAIOSFODNN7EXAMPLE")
        assert code == 0
        assert output is not None
        assert "AKIAIO" in output["tool_result"]

    def test_stripe_key(self):
        code, output = run_hook(
            "Bash",
            "sk_live_abcdef1234567890abcdef",
        )
        assert code == 0
        assert output is not None
        assert "sk_liv" in output["tool_result"]

    def test_anthropic_key(self):
        code, output = run_hook(
            "Bash",
            "key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456",
        )
        assert code == 0
        assert output is not None
        assert "sk-ant" in output["tool_result"]

    def test_slack_token(self):
        code, output = run_hook(
            "Bash",
            "SLACK_TOKEN=xoxb-not-a-real-slack-token-value",
        )
        assert code == 0
        assert output is not None
        assert "not-a-real" not in output["tool_result"]

    def test_sendgrid_key(self):
        code, output = run_hook(
            "Bash",
            "SG.abcdefghijklmnopqrstuv.ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrs",
        )
        assert code == 0
        assert output is not None


class TestStructuralPatterns:
    def test_env_assignment(self):
        code, output = run_hook(
            "Bash",
            'export DATABASE_PASSWORD="supersecretpassword123"',
        )
        assert code == 0
        assert output is not None
        assert "supersecretpassword123" not in output["tool_result"]

    def test_json_field(self):
        code, output = run_hook(
            "Read",
            '{"api_key": "abcdef1234567890abcdef1234567890"}',
        )
        assert code == 0
        assert output is not None
        assert "abcdef1234567890abcdef1234567890" not in output["tool_result"]

    def test_private_key(self):
        code, output = run_hook(
            "Read",
            "-----BEGIN RSA PRIVATE KEY-----\nMIIE...data...\n-----END RSA PRIVATE KEY-----",
        )
        assert code == 0
        assert output is not None
        assert "[REDACTED PRIVATE KEY]" in output["tool_result"]
        assert "MIIE" not in output["tool_result"]

    def test_db_connection_string(self):
        code, output = run_hook(
            "Bash",
            "postgres://admin:supersecretpassword@db.internal:5432/mydb",
        )
        assert code == 0
        assert output is not None
        assert "supersecretpassword" not in output["tool_result"]

    def test_auth_header(self):
        code, output = run_hook(
            "Bash",
            "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature",
        )
        assert code == 0
        assert output is not None
        assert "payload.signature" not in output["tool_result"]


class TestMaskingStrategy:
    def test_short_token_fully_masked(self):
        """Tokens < 18 chars should be fully masked as ***."""
        # env_secret structural pattern catches short values
        code, output = run_hook("Bash", "export MY_SECRET_KEY=shortvalue123")
        assert code == 0
        assert output is not None
        assert "***" in output["tool_result"]
        assert "shortvalue123" not in output["tool_result"]

    def test_long_token_preserves_edges(self):
        """Tokens >= 18 chars should preserve first 6 + last 4."""
        code, output = run_hook(
            "Bash",
            "sk-proj-abcdefghijklmnopqrstuvwxyz1234",
        )
        assert code == 0
        assert output is not None
        redacted = output["tool_result"]
        assert "sk-pro" in redacted
        assert "1234" in redacted
        assert "..." in redacted
        assert "abcdefghij" not in redacted


class TestCleanContent:
    def test_no_secrets_no_output(self):
        """Clean content should produce no output (no modification)."""
        code, output = run_hook(
            "Bash",
            "total 42\ndrwxr-xr-x  5 user staff 160 Apr  7 10:00 .\n",
        )
        assert code == 0
        assert output is None

    def test_code_with_no_secrets(self):
        code, output = run_hook(
            "Read",
            'func main() {\n\tfmt.Println("hello world")\n}',
        )
        assert code == 0
        assert output is None


class TestMetadata:
    def test_findings_metadata(self):
        code, output = run_hook(
            "Bash",
            "OPENAI_API_KEY=sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx "
            "and ghp_FAKEtesttoken0000000000000000000000",
        )
        assert code == 0
        assert output is not None
        assert output["metadata"]["secrets_redacted"] >= 2
        patterns = output["metadata"]["patterns"]
        assert "openai_key" in patterns
        assert "github_pat" in patterns


class TestEdgeCases:
    def test_empty_stdin(self):
        result = subprocess.run(
            [sys.executable, str(HOOK_PATH)],
            input="",
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0

    def test_malformed_json(self):
        result = subprocess.run(
            [sys.executable, str(HOOK_PATH)],
            input="not json",
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0

    def test_empty_tool_result(self):
        code, output = run_hook("Bash", "")
        assert code == 0
        assert output is None

    def test_never_blocks(self):
        """PostToolUse hook should always exit 0 (never block)."""
        code, _ = run_hook(
            "Bash",
            "AKIA1234567890ABCDEF ghp_x0000000000000000 sk-proj-longkey12345678901234567890",
        )
        assert code == 0
