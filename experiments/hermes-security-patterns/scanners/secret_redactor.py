"""Secret redaction engine adapted from Hermes Agent's agent/redact.py.

Scans text for API keys, tokens, credentials, and sensitive patterns.
Replaces detected secrets with masked versions preserving debuggability.

Usage:
    redactor = SecretRedactor()
    clean_text, findings = redactor.scan(text)
"""

import re
from dataclasses import dataclass


@dataclass
class RedactionFinding:
    pattern_name: str
    original_length: int
    masked_preview: str
    position: tuple[int, int]


# Prefix patterns for known API key formats.
# Each tuple: (name, regex_pattern)
_PREFIX_PATTERNS: list[tuple[str, str]] = [
    # OpenAI / Anthropic / AI providers (longer prefixes first to match before shorter)
    ("openai_proj", r"sk-proj-[a-zA-Z0-9_-]{20,}"),
    ("anthropic_key", r"sk-ant-[a-zA-Z0-9_-]{20,}"),
    ("openai_key", r"sk-[a-zA-Z0-9_-]{20,}"),
    # GitHub
    ("github_pat", r"ghp_[a-zA-Z0-9]{36,}"),
    ("github_fine_pat", r"github_pat_[a-zA-Z0-9_]{22,}"),
    ("github_oauth", r"gho_[a-zA-Z0-9]{36,}"),
    ("github_user_token", r"ghu_[a-zA-Z0-9]{36,}"),
    ("github_server_token", r"ghs_[a-zA-Z0-9]{36,}"),
    ("github_refresh_token", r"ghr_[a-zA-Z0-9]{36,}"),
    # Slack
    ("slack_token", r"xox[baprs]-[a-zA-Z0-9-]{10,}"),
    # Google
    ("google_api_key", r"AIza[a-zA-Z0-9_-]{35}"),
    # Perplexity
    ("perplexity_key", r"pplx-[a-f0-9]{48,}"),
    # fal.ai
    ("fal_key", r"fal_[a-zA-Z0-9_-]{20,}"),
    # Fireworks
    ("fireworks_key", r"fc-[a-zA-Z0-9_-]{20,}"),
    # Bitbucket
    ("bitbucket_key", r"bb_live_[a-zA-Z0-9_-]{20,}"),
    # AWS
    ("aws_access_key", r"AKIA[A-Z0-9]{16}"),
    # Stripe
    ("stripe_live", r"sk_live_[a-zA-Z0-9]{24,}"),
    ("stripe_test", r"sk_test_[a-zA-Z0-9]{24,}"),
    # SendGrid
    ("sendgrid_key", r"SG\.[a-zA-Z0-9_-]{22,}\.[a-zA-Z0-9_-]{20,}"),
    # Hugging Face
    ("hf_token", r"hf_[a-zA-Z0-9]{34,}"),
    # npm
    ("npm_token", r"npm_[a-zA-Z0-9]{36,}"),
    # PyPI
    ("pypi_token", r"pypi-[a-zA-Z0-9_-]{50,}"),
    # DigitalOcean
    ("digitalocean_token", r"dop_v1_[a-f0-9]{64}"),
    # Telegram
    ("telegram_bot_token", r"\d{8,10}:[a-zA-Z0-9_-]{35}"),
    # GitLab
    ("gitlab_pat", r"glpat-[a-zA-Z0-9_-]{20,}"),
    # Grafana
    ("grafana_key", r"glc_[a-zA-Z0-9_-]{20,}"),
    # Databricks
    ("databricks_token", r"dapi[a-f0-9]{32}"),
    # Confluent / Kafka
    ("confluent_key", r"[A-Z0-9]{16}"),  # too broad alone, only used in context
    # Vault
    ("vault_token", r"hvs\.[a-zA-Z0-9_-]{24,}"),
    # Age encryption
    ("age_secret_key", r"AGE-SECRET-KEY-[A-Z0-9]{59}"),
]

# Structural patterns (env assignments, JSON fields, headers)
_STRUCTURAL_PATTERNS: list[tuple[str, str]] = [
    # ENV assignment: KEY=value where KEY contains secret-like names
    (
        "env_assignment",
        r"(?:^|\s)(?:export\s+)?("
        r"[A-Z_]*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|PASSWD|AUTH|API_KEY)"
        r"[A-Z_]*"
        r")\s*=\s*['\"]?([^\s'\"]{8,})['\"]?",
    ),
    # JSON fields with secret-like names
    (
        "json_field",
        r'"(?:api[_-]?key|token|secret|password|credential|auth[_-]?token|access[_-]?key|private[_-]?key)"'
        r'\s*:\s*"([^"]{8,})"',
    ),
    # Authorization headers
    ("auth_header", r"(?i)(?:Authorization|X-Api-Key|X-Auth-Token)\s*:\s*(?:Bearer\s+)?(\S{8,})"),
    # Private key blocks
    ("private_key", r"-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE KEY-----"),
    # Database connection string passwords
    (
        "db_connection_password",
        r"(?:postgres|mysql|mongodb|redis)://[^:]+:([^@]{4,})@",
    ),
]


class SecretRedactor:
    def __init__(self, extra_patterns: list[tuple[str, str]] | None = None):
        self._prefix_regexes = [(name, re.compile(pattern)) for name, pattern in _PREFIX_PATTERNS]
        self._structural_regexes = [
            (name, re.compile(pattern, re.MULTILINE)) for name, pattern in _STRUCTURAL_PATTERNS
        ]
        if extra_patterns:
            self._prefix_regexes.extend(
                (name, re.compile(pattern)) for name, pattern in extra_patterns
            )

    @staticmethod
    def _mask(value: str) -> str:
        if len(value) < 18:
            return "***"
        return f"{value[:6]}...{value[-4:]}"

    def scan(self, text: str) -> tuple[str, list[RedactionFinding]]:
        findings: list[RedactionFinding] = []
        result = text

        # Prefix-based patterns (full match is the secret)
        for name, regex in self._prefix_regexes:
            for match in regex.finditer(result):
                secret = match.group(0)
                masked = self._mask(secret)
                findings.append(
                    RedactionFinding(
                        pattern_name=name,
                        original_length=len(secret),
                        masked_preview=masked,
                        position=(match.start(), match.end()),
                    )
                )
                result = result.replace(secret, masked, 1)

        # Structural patterns (capture group is the secret)
        for name, regex in self._structural_regexes:
            for match in regex.finditer(result):
                if name == "private_key":
                    # For private keys, just flag presence (don't try to extract value)
                    findings.append(
                        RedactionFinding(
                            pattern_name=name,
                            original_length=0,
                            masked_preview="[PRIVATE KEY BLOCK]",
                            position=(match.start(), match.end()),
                        )
                    )
                    continue

                # Use last capture group as the secret value
                groups = match.groups()
                secret = groups[-1] if groups else match.group(0)
                masked = self._mask(secret)
                findings.append(
                    RedactionFinding(
                        pattern_name=name,
                        original_length=len(secret),
                        masked_preview=masked,
                        position=(match.start(), match.end()),
                    )
                )
                result = result.replace(secret, masked, 1)

        return result, findings


if __name__ == "__main__":
    test_cases = [
        "My API key is sk-proj-abc123def456ghi789jkl012mno345pqr678",
        "Set GITHUB_TOKEN=ghp_FAKEtesttoken0000000000000000000000",
        '{"api_key": "super-secret-key-value-12345678"}',
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def",
        "Connect to postgres://admin:hunter2_secret@db.prod.internal:5432/app",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...",
        "No secrets in this clean text.",
    ]

    redactor = SecretRedactor()
    for text in test_cases:
        clean, findings = redactor.scan(text)
        status = f"REDACTED ({len(findings)} findings)" if findings else "CLEAN"
        print(f"  {status:<30} {clean[:80]}")
        for f in findings:
            print(f"    -> {f.pattern_name}: {f.masked_preview}")
