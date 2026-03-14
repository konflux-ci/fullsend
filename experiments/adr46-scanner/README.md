# Experiment 001: ADR-0046 Drift Scanner

A Python CLI tool that detects Tekton task steps drifting from [ADR-0046](https://github.com/konflux-ci/architecture/blob/main/ADR/0046-common-task-runner-image.md) (common task runner image) by comparing step images against a config-driven allowlist.

See [RESULTS.md](RESULTS.md) for hypothesis, results, and analysis.

## Usage

```bash
cd experiments/adr46-scanner
pip install -e ".[dev]"
adr46-scan --config config.yaml /path/to/build-definitions
```

## What it does

Parses Tekton task YAML files, extracts step images, and flags any that don't match the task runner image or an explicitly exempt image. Config-driven — the allowlist and scan paths are declared in `config.yaml`.

## Limitations

This scanner uses deterministic string matching. It validates that mechanical drift detection works, but doesn't generalize to ADRs that express design intent rather than concrete image requirements. See [Experiment 002](../adr46-claude-scanner/) for the LLM-based approach.
