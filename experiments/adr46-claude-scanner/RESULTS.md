# Experiment 002: Claude-based ADR Drift Scanner

**Date:** 2026-03-12

## Hypothesis

An LLM can read an ADR, understand its architectural intent, evaluate a code artifact against it, and produce useful analysis — including violations, reasoning, and fix recommendations — without any hardcoded rules. If true, this approach generalizes to ADRs that can't be reduced to mechanical checks.

## Setup

- **Tool:** A 40-line shell script (`experiments/adr46-claude-scanner/scan.sh`) that passes an ADR and a Tekton task YAML to `claude -p`
- **Model:** claude-sonnet-4-6
- **ADR:** [ADR-0046: Build a common Task Runner image](https://github.com/konflux-ci/architecture/blob/main/ADR/0046-common-task-runner-image.md)
- **Target:** The `modelcar-oci-ta` task from [konflux-ci/build-definitions](https://github.com/konflux-ci/build-definitions/blob/main/task/modelcar-oci-ta/0.1/modelcar-oci-ta.yaml)
- **No config files, no allowlists, no image-matching logic.** The prompt asks claude to analyze compliance — it derives what "compliance" means from the ADR text itself.

## Method

1. Wrote a hand-crafted [expected analysis](../../experiments/adr46-claude-scanner/expected/modelcar-oci-ta.md) as a human benchmark — our own reading of what violates the ADR and what to do about each case
2. Built a shell script that combines the ADR text and task YAML into a prompt and passes it to `claude -p`
3. Ran the scanner and captured [claude's output](../../experiments/adr46-claude-scanner/results/modelcar-oci-ta.md)
4. Evaluated against the expected analysis using a four-point rubric

## Results

### Violation detection

Claude found all 7 violations identified in our expected analysis. It correctly grouped `download-model-files` and `push-image` as the same class of violation (both use the oras tool-oriented image).

One divergence: our expected analysis called `sbom-generate` (mobster) a clear violation, but claude categorized it as a "gray area" — arguing that mobster might be a "use-case-oriented" image rather than a "tool-oriented" one, since the ADR distinguishes between these categories. This is a defensible reading of the ADR.

### Exemption recognition

Claude correctly exempted `use-trusted-artifact`, citing the ADR's explicit carve-out for Trusted Artifacts steps and the statement that "the Task Runner image does not replace the more specialized use-case-oriented images."

### Fix quality

Claude's fix recommendations were actionable and appropriately differentiated:

| Step | Our expected fix | Claude's fix | Match? |
|---|---|---|---|
| download-model-files | Swap image (tools available) | Swap image | Yes |
| create-modelcar-base-image | Add `get-image-architectures` to task runner first | Same | Yes |
| copy-model-files | Gray area — pip install may work | Stronger: runtime pip breaks hermetic builds | Claude went further |
| push-image | Swap image | Swap image | Yes |
| sbom-generate | Add `mobster` to task runner first | Argued potentially exempt as use-case-oriented | Divergence |
| upload-sbom | Swap image | Swap image, cited ADR by name | Yes |
| report-sbom-url | Swap image, noted `yq` not used | Same, with the same observation | Yes |

### Unexpected insights

Claude surfaced three things our expected analysis missed or underweighted:

1. **Hermetic build violation in `copy-model-files`:** Claude connected the runtime `pip install olot` to the ADR's requirement to "build and release via Konflux, hermetically if possible." Our analysis noted the gray area around `olot` as a tool, but didn't flag the hermetic build angle.

2. **Use-case vs. tool-oriented distinction for mobster:** Claude applied the ADR's taxonomy more carefully than we did. Whether mobster is "use-case-oriented" (like build-trusted-artifacts) or "tool-oriented" (like yq-container) is genuinely ambiguous, and claude engaged with that ambiguity rather than defaulting to "violation."

3. **Resource cost of duplicate oras steps:** Claude noted that having two steps using the oras image means paying the resource cost twice (since Tekton sums step resources), directly citing the ADR's discussion of this problem.

## Analysis

### What worked

The core hypothesis is validated. Claude read the ADR, understood its intent, identified violations, and produced fix recommendations — all without any hardcoded rules about images, allowlists, or Tekton task structure. The prompt was 6 lines of instruction; everything else came from the ADR and the task YAML.

The quality of reasoning exceeded our expectations in some areas. The hermetic build connection and the use-case/tool-oriented distinction show that claude is doing more than pattern matching — it's engaging with the ADR's design philosophy.

### What this tells us about the broader problem

**This approach generalizes.** The scan script is ADR-agnostic — swap in a different ADR and a different code artifact and it works without changes. For ADRs that express design philosophy rather than mechanical rules (which is most ADRs), this is the only approach that works at all. The Python scanner from Experiment 001 would need a new implementation for every ADR; this script wouldn't.

**LLM judgment adds value beyond detection.** The Python scanner can tell you *that* a step uses the wrong image. Claude can tell you *why* that matters in the context of the ADR's goals, *whether* an exemption applies, and *what* to do about it — including distinguishing between "swap today" and "add tooling first." The fix recommendations are the most practically useful part.

**Disagreements are interesting, not failures.** Claude categorizing mobster as a gray area rather than a clear violation isn't wrong — it's a legitimate interpretive difference that surfaces genuine ambiguity in the ADR. In a real workflow, this is exactly what you'd want flagged for human review.

### Comparison with Experiment 001

| Dimension | Experiment 001 (Python) | Experiment 002 (Claude) |
|---|---|---|
| Lines of code | ~200 Python + 19 tests | ~40 lines of bash |
| Config needed | YAML with image allowlist + exemptions | None |
| ADR-specific logic | All of it | None |
| Handles new ADRs | No — new implementation per ADR | Yes — swap the ADR file |
| Fix recommendations | None | Yes, with reasoning |
| Exemption reasoning | Config-driven (exempt_images list) | Derived from ADR text |
| Nuance | Binary (violation or not) | Graduated (violation, exempt, gray area) |
| Cost | Free (deterministic) | API cost per invocation |

### Limitations

- **Non-deterministic.** Running the same scan twice may produce different output. The quality is high but not guaranteed identical.
- **No batch mode.** The script processes one task at a time. Scanning all tasks in build-definitions would require a wrapper.
- **Accuracy depends on the model.** We used claude-sonnet-4-6. A weaker model might miss subtleties; a stronger model might find more.
- **No ground truth for "correct."** When claude and our expected analysis disagree (e.g., on mobster), there's no oracle — just two interpretations.

## Next steps

1. **Run against a non-mechanical ADR** — test with an ADR that expresses design philosophy rather than a concrete image requirement, to see if the approach holds
2. **Run against multiple tasks** — wrap the script to scan all tasks in build-definitions and aggregate results
3. **Test with different models** — compare sonnet vs. haiku vs. opus on the same inputs
4. **Build the fixer** — given a violation report, can claude also generate the PR to fix it?
