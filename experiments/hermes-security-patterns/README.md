# Experiment: Hermes-Inspired Security Patterns for Fullsend

Evaluates security patterns from [Hermes Agent](https://github.com/NousResearch/hermes-agent) for integration into fullsend's autonomous SDLC pipeline. Tests two integration strategies: static file scanning via [Tirith](https://github.com/sheeki03/tirith) CLI and runtime SSRF protection via a Claude Code PreToolUse hook.

Related: [Hermes Agent Security Analysis](../../../Research/hermes-agent-security-analysis.md) | [Tirith Security Analysis](../../../Research/tirith-terminal-security-analysis.md)

## Hypothesis

Fullsend's runtime security gaps (secret redaction, SSRF protection, context file injection scanning, Unicode normalization) can be addressed by composing existing tools rather than building new scanners:

1. **Tirith CLI** handles static scanning (unicode normalization, context injection detection, secret detection) as a GitHub Actions workflow step — it already covers 80+ rules across these categories with fuzz-tested Rust implementations.
2. **Claude Code PreToolUse hook** handles SSRF protection at the agent runtime boundary — intercepting `Bash` and `WebFetch` tool calls before the agent can make outbound requests to internal networks or cloud metadata endpoints.

## Architecture

```
                     GitHub Actions Workflow
                     ┌──────────────────────────────────────┐
                     │                                      │
  Issue/PR created ──┤  1. tirith scan --json .             │
                     │     ├── unicode normalization         │
                     │     ├── context injection detect      │
                     │     └── AI config file scanning       │
                     │                                      │
                     │  2. Agent execution                   │
                     │     ├── claude-code / gemini-cli      │
                     │     │                                │
                     │     ├── PreToolUse hook ──────────┐  │
                     │     │  ssrf_pretool.py            │  │
                     │     │   ├── Bash: extract URLs    │  │
                     │     │   ├── WebFetch: check URL   │  │
                     │     │   └── Block internal/meta   │  │
                     │     │                             │  │
                     │     └── PostToolUse hook ─────────┤  │
                     │        secret_redact_posttool.py  │  │
                     │         ├── Mask 35+ key prefixes │  │
                     │         ├── Redact env/JSON/keys  │  │
                     │         └── Agent sees *** only   │  │
                     │                                   │  │
                     └───────────────────────────────────┘
```

## Components

### 1. Tirith CLI — Static Scanning (GHA workflow step)

Tirith replaces three custom Python scanners with its battle-tested Rust implementation:

| Fullsend Concern | Tirith Rule Module | Coverage |
|---|---|---|
| Unicode normalization | `terminal.rs` — zero-width, bidi, tags, variation selectors, ANSI | 80+ invisible character types, joining-script context awareness |
| Context injection | `configfile.rs` — 50+ AI config file patterns | CLAUDE.md, .cursorrules, AGENTS.md, etc. with prompt injection detection |

**Usage in workflow:**

```yaml
- name: Security scan
  run: |
    tirith scan --json --sarif-output scan-results.sarif .
    # Block on critical/high findings
    tirith scan --fail-on high .
```

### 2. SSRF PreToolUse Hook (`hooks/ssrf_pretool.py`)

A Claude Code PreToolUse hook that intercepts `Bash` and `WebFetch` tool calls to block SSRF attempts. This runs inside the agent's runtime, not as a workflow step, because SSRF happens when the agent makes HTTP requests during execution.

**Blocklists:**
- RFC 1918 private networks (10/8, 172.16/12, 192.168/16)
- Cloud metadata endpoints (169.254.169.254, metadata.google.internal, fd00:ec2::254)
- Loopback, link-local, CGNAT, reserved ranges
- Dangerous schemes (file://, gopher://, ftp://, data://)

**Installation:**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|WebFetch",
        "hooks": [
          {
            "type": "command",
            "command": "python3 hooks/ssrf_pretool.py"
          }
        ]
      }
    ]
  }
}
```

**Protocol:** Reads Claude Code hook JSON from stdin. Returns `{"decision": "block", "reason": "..."}` on stdout with exit code 1 to block, or exits 0 to allow. Fails open on parse errors.

### 3. Secret Redaction PostToolUse Hook (`hooks/secret_redact_posttool.py`)

A Claude Code PostToolUse hook that intercepts tool results and redacts secrets before they enter the LLM context window. Adapted from Hermes Agent's `agent/redact.py` masking strategy.

**Why PostToolUse, not PreToolUse or workflow step?** Secrets appear in tool *output* — a `Bash` command might print an API key from env vars, or a `Read` might show a config file with tokens. The agent must never see the raw value, so redaction happens between tool execution and the LLM context. This is how Hermes handles it: redaction sits in the agent loop, after each tool call, before results enter the message history.

**Coverage (35+ patterns):**
- Known prefixes: `sk-` (OpenAI), `ghp_` (GitHub), `sk-ant-` (Anthropic), `AKIA` (AWS), `xox[baprs]-` (Slack), `SG.` (SendGrid), `hf_` (HuggingFace), `sk_live_` (Stripe), and more
- Structural: ENV assignments, JSON secret fields, Authorization headers, private key blocks, database connection strings

**Masking strategy:**
- Short tokens (<18 chars): fully masked as `***`
- Long tokens (>=18 chars): first 6 + last 4 preserved for debuggability (e.g., `sk-pro...901vwx`)
- Private key blocks: replaced with `[REDACTED PRIVATE KEY]`

**Installation:**

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash|WebFetch|Read",
        "hooks": [
          {
            "type": "command",
            "command": "python3 hooks/secret_redact_posttool.py"
          }
        ]
      }
    ]
  }
}
```

**Protocol:** Reads JSON from stdin (`tool_name`, `tool_input`, `tool_result`). Returns `{"tool_result": "...", "metadata": {...}}` on stdout with the redacted result. Always exits 0 — redaction transforms but never blocks.

## Payloads

Attack payloads targeting each security concern:

| Payload | Tested By | Technique |
|---------|-----------|-----------|
| `leaked-secret-in-pr.yaml` | Redact hook | Agent leaks API key in PR comment |
| `leaked-secret-json.yaml` | Redact hook | Agent includes JSON config with tokens |
| `ssrf-metadata.yaml` | SSRF hook | Issue body references cloud metadata URL |
| `ssrf-redirect.yaml` | SSRF hook | Public URL redirects to internal endpoint |
| `context-injection-agents-md.yaml` | Tirith scan | AGENTS.md with "ignore instructions" pattern |
| `context-injection-hidden-html.yaml` | Tirith scan | Hidden HTML comment with override instructions |
| `context-injection-credential-exfil.yaml` | Tirith scan | Context file with curl + credential env vars |
| `unicode-invisible-command.yaml` | Tirith scan | Command with zero-width characters |
| `unicode-bidi-override.yaml` | Tirith scan | Bidirectional override hiding malicious suffix |
| `unicode-tag-chars.yaml` | Tirith scan | Tag characters embedding hidden text |

## Running

```bash
cd experiments/hermes-security-patterns

# Install dependencies
uv venv .venv
uv pip install pyyaml

# Install tirith (for static scanning tests)
# macOS
brew install sheeki03/tap/tirith
# Linux (amd64)
curl -fsSL https://github.com/sheeki03/tirith/releases/latest/download/tirith-x86_64-unknown-linux-gnu.tar.gz \
  | tar xz -C /usr/local/bin tirith
# Linux (arm64)
curl -fsSL https://github.com/sheeki03/tirith/releases/latest/download/tirith-aarch64-unknown-linux-gnu.tar.gz \
  | tar xz -C /usr/local/bin tirith
# Or via cargo (any platform)
cargo install tirith

# Run full evaluation
uv run python run_eval.py

# Hook tests only (no tirith needed)
uv run python run_eval.py --hooks-only

# Tirith scan tests only
uv run python run_eval.py --tirith-only

# Unit tests
uv run python -m pytest tests/ -v
```

## Integration Plan

### Phase 1: Validation (this experiment)
- Test tirith scan against fullsend-specific payloads
- Test SSRF hook against metadata/redirect payloads
- Measure detection rates and false positives

### Phase 2: GitHub Actions integration
- Add `tirith scan` as a workflow step before agent execution
- Install SSRF hook in agent runner's `.claude/settings.json`
- Wire findings to fullsend's label state machine (`requires-manual-review`)

### Phase 3: Multi-agent support
- Adapt SSRF hook for Gemini CLI (different hook protocol)
- Add tirith scan to post-agent output validation
- SARIF output integration for GitHub Security tab

## Comparison with Existing Experiments

| Concern | Existing Coverage | This Experiment |
|---------|-------------------|-----------------|
| Prompt injection detection | guardrails-eval (LLM Guard 83%) | Tirith configfile scanning (pre-load, complementary) |
| Unicode attacks | guardrails-eval/zero-width-chars.yaml | Tirith terminal rules (80+ types, not just detect) |
| Secret leakage | None | PostToolUse redaction hook (35+ patterns, Hermes masking strategy) |
| SSRF | None | PreToolUse hook (RFC 1918, metadata, schemes) |
| Pre-exec scanning | None | Tirith scan in workflow + SSRF hook at runtime |

## Key Design Decisions

1. **Tirith over custom scanners**: Tirith has fuzz-tested Rust implementations with 80+ rules. Reimplementing in Python/Go adds maintenance burden with less coverage.
2. **SSRF as PreToolUse hook**: SSRF happens at request time inside the agent runtime. A workflow step can't intercept URLs the agent discovers during execution.
3. **Secret redaction as PostToolUse hook**: Following Hermes Agent's architecture — redaction sits in the agent loop, between tool execution and the LLM context window. The agent never sees raw secrets, so it can't leak them in subsequent output (PR comments, issue bodies). This is more robust than pre-scanning repo files, which only catches secrets already committed.
4. **Fail-open on errors**: All hooks fail open on parse/timeout errors. This prioritizes availability — a broken security hook shouldn't block all agent work. Override with `--fail-on` for strict mode.
