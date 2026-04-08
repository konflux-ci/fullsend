#!/usr/bin/env python3
"""Claude Code PostToolUse hook for secret redaction.

Intercepts tool results (Bash, WebFetch, Read, etc.) and redacts secrets
before they enter the LLM context window. This prevents the agent from
seeing or leaking credentials in subsequent output (PR comments, issue bodies).

Adapted from Hermes Agent's agent/redact.py masking strategy:
- Short tokens (<18 chars): fully masked as ***
- Long tokens (>=18 chars): first 6 + last 4 preserved for debuggability

Install in .claude/settings.json:
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash|WebFetch|Read",
        "hooks": [
          {
            "type": "command",
            "command": "python3 experiments/hermes-security-patterns/hooks/secret_redact_posttool.py"
          }
        ]
      }
    ]
  }
}

Protocol: reads JSON from stdin (tool_name, tool_input, tool_result),
writes JSON to stdout with modified tool_result if secrets found.
Exit code 0 always (redaction never blocks, only transforms).
"""

import json
import re
import sys


# ---------------------------------------------------------------------------
# Known secret prefix patterns (35+ from Hermes agent/redact.py)
# ---------------------------------------------------------------------------

_PREFIX_PATTERNS: list[tuple[str, re.Pattern]] = [
    # OpenAI
    ("openai_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    # GitHub
    ("github_pat", re.compile(r"(?:ghp|github_pat|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{16,}")),
    # Slack
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    # Google
    ("google_api_key", re.compile(r"AIza[A-Za-z0-9_-]{35}")),
    # Anthropic
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    # AWS
    ("aws_access_key", re.compile(r"AKIA[A-Z0-9]{16}")),
    ("aws_secret_key", re.compile(r"(?:aws_secret_access_key|AWS_SECRET_ACCESS_KEY)\s*[=:]\s*[A-Za-z0-9/+=]{40}")),
    # Stripe
    ("stripe_key", re.compile(r"(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{10,}")),
    # SendGrid
    ("sendgrid_key", re.compile(r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}")),
    # HuggingFace
    ("hf_token", re.compile(r"hf_[A-Za-z0-9]{20,}")),
    # npm
    ("npm_token", re.compile(r"npm_[A-Za-z0-9]{36}")),
    # PyPI
    ("pypi_token", re.compile(r"pypi-[A-Za-z0-9_-]{20,}")),
    # DigitalOcean
    ("digitalocean_token", re.compile(r"dop_v1_[a-f0-9]{64}")),
    # Perplexity
    ("perplexity_key", re.compile(r"pplx-[a-f0-9]{48}")),
    # Databricks
    ("databricks_token", re.compile(r"dapi[a-f0-9]{32}")),
    # Telegram bot token
    ("telegram_bot", re.compile(r"\d{8,10}:[A-Za-z0-9_-]{35}")),
    # Generic bearer/basic auth
    ("auth_header", re.compile(r"(?:Authorization|authorization)\s*:\s*(?:Bearer|Basic|Token)\s+[A-Za-z0-9_.+/=-]{20,}")),
]

# ---------------------------------------------------------------------------
# Structural patterns (env assignments, JSON fields, private keys, etc.)
# ---------------------------------------------------------------------------

_STRUCTURAL_PATTERNS: list[tuple[str, re.Pattern]] = [
    # ENV assignment: KEY=value (where KEY contains secret-like names)
    (
        "env_secret",
        re.compile(
            r"(?:^|\s)(?:export\s+)?(?:"
            r"[A-Z_]*(?:SECRET|TOKEN|KEY|PASSWORD|PASSWD|CREDENTIAL|API_KEY|APIKEY|AUTH)"
            r"[A-Z_]*)"
            r"\s*=\s*['\"]?([A-Za-z0-9_.+/=@:%-]{8,})['\"]?",
            re.MULTILINE,
        ),
    ),
    # JSON field: "apiKey": "value", "token": "value", etc.
    (
        "json_secret",
        re.compile(
            r'"(?:[^"]*(?:secret|token|key|password|credential|apikey|api_key|auth)[^"]*)"'
            r'\s*:\s*"([A-Za-z0-9_.+/=@:%-]{8,})"',
            re.IGNORECASE,
        ),
    ),
    # Private key blocks
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
            r"[\s\S]*?"
            r"-----END (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
        ),
    ),
    # Database connection strings with passwords
    (
        "db_password",
        re.compile(
            r"(?:postgres|mysql|mongodb|redis)(?:ql)?://[^:]+:([^@\s]{8,})@",
            re.IGNORECASE,
        ),
    ),
]


def mask_token(token: str) -> str:
    """Mask a secret token using Hermes strategy.

    Short tokens (<18 chars): fully masked as ***
    Long tokens (>=18 chars): first 6 + last 4 preserved
    """
    if len(token) < 18:
        return "***"
    return f"{token[:6]}...{token[-4:]}"


def redact_text(text: str) -> tuple[str, list[dict]]:
    """Scan text and redact any detected secrets.

    Returns (redacted_text, list_of_findings).
    """
    findings: list[dict] = []
    result = text

    # Apply prefix patterns
    for name, pattern in _PREFIX_PATTERNS:
        for match in pattern.finditer(result):
            token = match.group(0)
            masked = mask_token(token)
            if masked != token:
                findings.append({
                    "pattern": name,
                    "original_length": len(token),
                    "masked": masked,
                })
                result = result.replace(token, masked)

    # Apply structural patterns
    for name, pattern in _STRUCTURAL_PATTERNS:
        if name == "private_key":
            # Replace entire key block
            for match in pattern.finditer(result):
                block = match.group(0)
                findings.append({
                    "pattern": name,
                    "original_length": len(block),
                    "masked": "[REDACTED PRIVATE KEY]",
                })
                result = result.replace(block, "[REDACTED PRIVATE KEY]")
        else:
            # Replace captured group (the secret value)
            for match in pattern.finditer(result):
                if match.lastindex and match.lastindex >= 1:
                    token = match.group(1)
                    masked = mask_token(token)
                    if masked != token:
                        findings.append({
                            "pattern": name,
                            "original_length": len(token),
                            "masked": masked,
                        })
                        result = result.replace(token, masked)

    return result, findings


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)
        hook_input = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        # Fail open on parse errors
        sys.exit(0)

    tool_result = hook_input.get("tool_result", "")
    if not tool_result or not isinstance(tool_result, str):
        sys.exit(0)

    redacted, findings = redact_text(tool_result)

    if findings:
        json.dump({
            "tool_result": redacted,
            "metadata": {
                "secrets_redacted": len(findings),
                "patterns": [f["pattern"] for f in findings],
            },
        }, sys.stdout)

    sys.exit(0)


if __name__ == "__main__":
    main()
