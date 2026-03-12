# Experiment 002: Claude-based ADR Drift Scanner

A shell script that uses `claude` CLI to analyze Tekton tasks for ADR compliance. No hardcoded rules, no config files — all intelligence comes from claude's comprehension of the ADR text.

See [RESULTS.md](RESULTS.md) for hypothesis, results, and analysis.

## Usage

```bash
cd experiments/adr46-claude-scanner
./scan.sh fixtures/adr-0046.md fixtures/modelcar-oci-ta.yaml
```

Pass any ADR file and any code artifact. The script is ADR-agnostic.

## What it does

Combines the ADR text and the target file into a prompt, passes it to `claude -p`, and prints a prose analysis covering:

- **What** violates the ADR
- **Why** it violates (citing the ADR's requirements)
- **Fix** recommendations (distinguishing "swap today" from "needs upstream work")

## Files

- `scan.sh` — The scanner (reads two files, constructs prompt, invokes claude)
- `expected/` — Hand-written expected analysis (our human benchmark)
- `results/` — Claude's actual output
- `fixtures/` — Local copies of the ADR and task YAML used for testing

## Key result

Claude found all 7 violations, correctly exempted the trusted artifacts step, and surfaced insights our human analysis missed — including a hermetic build violation and a nuanced use-case vs. tool-oriented distinction. See [RESULTS.md](RESULTS.md) for the full comparison.
