# Experiment: Pluggable Guardrails Evaluation

Evaluates prompt injection scanning tools as pre-LLM guardrails for fullsend's autonomous SDLC pipeline. Extends the [Model Armor experiment](../model-armor-vs-agent-triage/) (PR #117) with additional attack payloads and alternative scanning backends.

Related: [Story 6 (#129)](https://github.com/fullsend-ai/fullsend/issues/129) — Prompt injection defense

## Hypothesis

LLM Guard's DeBERTa-v3 classifier with sentence-level matching detects prompt injection attacks that Model Armor misses, including unicode/encoding tricks and indirect injection via file content.

## Background

PR #117 found that Model Armor detected only 1/4 injection payloads (25%) at maximum sensitivity. The [prompt-injection-defense](../prompt-injection-defense/) experiment found that Claude Sonnet 4.6 is inherently resilient, but the DeBERTa v1 classifier "adds no value" beyond what the model catches.

This experiment tests whether:
1. LLM Guard's v2 classifier with sentence-level matching improves detection
2. NeMo Guardrails' YARA rules catch LLM prompt injection (spoiler: they don't)
3. Model Armor handles extended attack types (unicode, indirect injection)

## Attack Payloads

### Original (from `../prompt-injection-defense/attacks/`)

| Payload | Technique |
|---------|-----------|
| benign | Clean commit message (control) |
| obvious-injection | "Ignore all previous instructions" |
| subtle-injection | Social engineering ("already approved") |
| bypass-classifier | Social engineering in git trailers |
| bypass-sandwiching | Mimics sandwich defense closing instruction |
| bypass-spotlighting | Closes data markers early |

### Extended (new in `payloads/`)

| Payload | Technique | Category |
|---------|-----------|----------|
| unicode-homoglyph | Cyrillic characters replacing Latin | unicode/encoding |
| zero-width-chars | ZWNJ (U+200C) between trigger word chars | unicode/encoding |
| base64-encoded | Injection instructions as base64 string | encoding |
| indirect-code-comment | Injection disguised as TODO comments | indirect |
| indirect-review-feedback | Fake review feedback requesting escalation | indirect |
| indirect-ci-output | Injection in fake test failure SUGGESTION | indirect |
| indirect-multistep | Benign project config planting later instructions | indirect |

## Results

| Category | Model Armor | LLM Guard (full) | LLM Guard (sentence) |
|----------|-------------|-------------------|----------------------|
| Original (social engineering) | 1/5 (20%) | 2/5 (40%) | 5/5 (100%) |
| Unicode/encoding | 0/2 (0%) | 1/2 (50%) | 2/2 (100%) |
| Indirect injection | 0/4 (0%) | 0/4 (0%) | 3/4 (75%) |
| Encoding (base64) | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| **Overall** | **1/12 (8%)** | **3/12 (25%)** | **10/12 (83%)** |
| **False positives** | **0/1** | **0/1** | **0/1** |

### Key Findings

1. **LLM Guard sentence mode: 83% detection, 0 false positives.** Sentence-level splitting isolates social engineering phrases for independent classification, catching attacks diluted in full-text scanning.

2. **Model Armor: 8% detection.** Only catches crude "ignore all instructions." Same dilution problem as LLM Guard full mode — detects social engineering in isolation but misses when embedded in larger text. No sentence-splitting option.

3. **Two fundamentally undetectable attack classes:** Base64 encoding (classifier sees random alphanumeric) and multi-step delayed injection (each step individually benign). These require architectural mitigations (CODEOWNERS, permission boundaries).

### Latency

Measured on Intel i7-1365U (10c/12t, 5.2GHz), 32GB RAM. GitHub Actions `ubuntu-latest` (4 vCPU, 16GB) expected ~2-3x slower.

| Scanner | Local Latency | Est. Actions Runner |
|---------|---------------|---------------------|
| LLM Guard (sentence, ONNX CPU) | 216ms | ~450-650ms |
| LLM Guard (full, ONNX CPU) | 72ms | ~150-200ms |
| Model Armor (GCP) | 216ms | ~216ms (network-bound) |

## Running

```bash
cd experiments/guardrails-eval
uv venv .venv
uv pip install "llm-guard[onnxruntime]" pyyaml yara-python nemoguardrails

# LLM Guard evaluation (original payloads)
uv run python eval-llm-guard.py

# NeMo / YARA comparison
uv run python eval-nemo-guardrails.py

# Full 13-payload evaluation (LLM Guard + InvisibleText)
uv run python eval-extended.py

# Model Armor evaluation (requires GCP auth + env vars)
# export GCP_PROJECT_ID=<your-gcp-project>
# export MODEL_ARMOR_TEMPLATE=<your-template-name>
# gcloud auth activate-service-account --key-file=<sa-key.json>
uv run python eval-model-armor.py
```

## Recommendation

Use **LLM Guard with `match_type=SENTENCE`** as the default always-on local scanner in fullsend workflows. Cloud scanners (Model Armor, promptfoo Enterprise) are optional parallel checks but currently add no unique detection capability.

```python
from llm_guard.input_scanners import PromptInjection
from llm_guard.input_scanners.prompt_injection import MatchType

scanner = PromptInjection(threshold=0.92, match_type=MatchType.SENTENCE, use_onnx=True)
sanitized, is_valid, risk_score = scanner.scan(text)
# is_valid=False means injection detected
```
