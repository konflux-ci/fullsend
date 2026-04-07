# Experiment: Hermes-Inspired Security Patterns for Fullsend

Evaluates security patterns from [Hermes Agent](https://github.com/NousResearch/hermes-agent) for integration into fullsend's autonomous SDLC pipeline. Focuses on four runtime security controls that fullsend currently lacks.

Related: [Hermes Agent Security Analysis](../../../Research/hermes-agent-security-analysis.md)

## Hypothesis

Hermes Agent's runtime security controls (secret redaction, SSRF protection, context file injection scanning, Unicode normalization) address gaps in fullsend's current defense posture. These controls can be extracted as standalone modules and integrated into fullsend's agent workflow stages without requiring changes to the core architecture.

## Background

Fullsend's security model excels at **structural separation** (zero trust between agents, per-role GitHub Apps, immutable config). But the [security threat model](../../docs/problems/security-threat-model.md) identifies gaps in runtime protections:

- No input sanitization for untrusted content (issue bodies, PR descriptions, code comments)
- No Unicode normalization or invisible character detection
- No secret redaction in agent-generated output (PR comments, issue bodies)
- No SSRF protection if agents fetch URLs during triage/implementation

Hermes Agent has production-tested implementations for all four. This experiment ports the patterns as standalone Python modules, evaluates them against fullsend-specific attack scenarios, and measures integration feasibility.

## Scanners

### 1. Secret Redaction (`scanners/secret_redactor.py`)

Regex-based redaction engine covering 35+ API key prefix patterns, JSON fields, authorization headers, private key blocks, and database connection strings. Adapted from Hermes Agent's `agent/redact.py`.

**Fullsend integration point:** Post-processing filter on all agent-generated GitHub API output (PR comments, issue comments, commit messages) before posting.

### 2. SSRF Validator (`scanners/ssrf_validator.py`)

URL validation against RFC 1918 private networks, cloud metadata endpoints, link-local, CGNAT, and loopback addresses. Validates redirect chains at each hop.

**Fullsend integration point:** Pre-fetch hook for any URL the triage or implementation agent accesses (issue links, referenced URLs, dependency sources).

### 3. Context File Injection Scanner (`scanners/context_injection_scanner.py`)

Regex-based scanner for prompt injection patterns in project context files (AGENTS.md, .cursorrules, CLAUDE.md, etc.). Detects instruction override attempts, hidden HTML/Unicode, credential exfiltration patterns, and execution-via-translation tricks.

**Fullsend integration point:** Pre-load scan before any agent ingests repository context files. Blocks or sanitizes files with detected injection patterns.

### 4. Unicode Normalizer (`scanners/unicode_normalizer.py`)

Strips invisible Unicode characters (zero-width spaces, bidirectional overrides, tag characters, variation selectors) and normalizes fullwidth characters via NFKC. Prevents command obfuscation and invisible payload injection.

**Fullsend integration point:** Input sanitization layer applied to all untrusted text before any agent processing. Integrates with the existing [guardrails-eval](../guardrails-eval/) LLM Guard recommendation.

## Payloads

Attack payloads targeting each scanner, designed around fullsend-specific scenarios:

| Payload | Target Scanner | Technique |
|---------|---------------|-----------|
| `leaked-secret-in-pr.yaml` | Secret Redactor | Agent leaks API key in PR comment |
| `leaked-secret-json.yaml` | Secret Redactor | Agent includes JSON config with tokens |
| `ssrf-metadata.yaml` | SSRF Validator | Issue body references cloud metadata URL |
| `ssrf-redirect.yaml` | SSRF Validator | Public URL redirects to internal endpoint |
| `context-injection-agents-md.yaml` | Context Injection | AGENTS.md with "ignore instructions" pattern |
| `context-injection-hidden-html.yaml` | Context Injection | Hidden HTML comment with override instructions |
| `context-injection-credential-exfil.yaml` | Context Injection | Context file with curl + credential env vars |
| `unicode-invisible-command.yaml` | Unicode Normalizer | Command with zero-width characters between keywords |
| `unicode-bidi-override.yaml` | Unicode Normalizer | Bidirectional override hiding malicious suffix |
| `unicode-tag-chars.yaml` | Unicode Normalizer | Tag characters (U+E0000-E007F) embedding hidden text |

## Running

```bash
cd experiments/hermes-security-patterns
uv venv .venv
uv pip install pyyaml requests

# Run all scanners against all payloads
uv run python run_eval.py

# Run individual scanner tests
uv run python -m pytest tests/ -v

# Run a specific scanner standalone
uv run python -m scanners.secret_redactor --test
uv run python -m scanners.ssrf_validator --test
uv run python -m scanners.context_injection_scanner --test
uv run python -m scanners.unicode_normalizer --test
```

## Integration Plan

### Phase 1: Standalone validation (this experiment)
- Port scanner logic as independent Python modules
- Test against fullsend-specific payloads
- Measure latency and false positive rates

### Phase 2: GitHub Actions integration
- Package scanners as a composite action or reusable workflow step
- Insert into triage/implementation/review workflows
- Wire output to fullsend's label state machine (block on detection, apply `requires-manual-review`)

### Phase 3: Agent-level integration
- Embed scanners in fullsend CLI entrypoints (`fullsend entrypoint triage|implementation|review`)
- Secret redactor wraps all GitHub API write calls
- SSRF validator wraps all HTTP fetches
- Context injection scanner runs before agent prompt assembly
- Unicode normalizer runs on all ingested text

## Comparison with Existing Experiments

| Concern | Existing Coverage | This Experiment |
|---------|-------------------|-----------------|
| Prompt injection detection | guardrails-eval (LLM Guard 83%) | Context file injection scanning (pre-load, complementary) |
| Unicode attacks | guardrails-eval/zero-width-chars.yaml | Full normalizer (strip + NFKC, not just detect) |
| Secret leakage | None | Secret redactor (35+ patterns) |
| SSRF | None | SSRF validator (RFC 1918, metadata, redirects) |
| Pre-exec scanning | None | Context injection scanner (Tirith-like) |
