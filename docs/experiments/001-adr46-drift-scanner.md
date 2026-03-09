# Experiment 001: ADR-0046 Drift Scanner

**Date:** 2026-03-06

## Hypothesis

Automated drift detection against architectural decision records (ADRs) is feasible with a simple, config-driven tool. Specifically: given ADR-0046 (common task runner image), we can programmatically identify Tekton task steps that use images they shouldn't.

## Setup

- **Tool:** Python CLI scanner (`experiments/adr46-scanner/`)
- **ADR:** [ADR-0046: Build a common Task Runner image](https://github.com/konflux-ci/architecture/blob/main/ADR/0046-common-task-runner-image.md)
- **Target:** The `modelcar-oci-ta` task from [konflux-ci/build-definitions](https://github.com/konflux-ci/build-definitions/blob/main/task/modelcar-oci-ta/0.1/modelcar-oci-ta.yaml)
- **Config:** Task runner image = `quay.io/konflux-ci/task-runner`, exempt = `quay.io/konflux-ci/build-trusted-artifacts` (per ADR-0046's explicit exception for trusted artifact steps)

## Method

1. Built a scanner that parses Tekton task YAML, extracts step images, and compares them against a config-driven allowlist (task runner image + exempt images)
2. Ran the scanner against the real modelcar-oci-ta task definition
3. Verified results against manual analysis of the task

## Results

The scanner found **7 violations** out of 8 steps. The one exempt step (`use-trusted-artifact`) was correctly excluded.

```
Found 7 step(s) not using the task runner image:

  Task: modelcar-oci-ta
  Step: download-model-files
  Image: quay.io/konflux-ci/oras

  Task: modelcar-oci-ta
  Step: create-modelcar-base-image
  Image: quay.io/konflux-ci/release-service-utils

  Task: modelcar-oci-ta
  Step: copy-model-files
  Image: registry.access.redhat.com/ubi9/python-311

  Task: modelcar-oci-ta
  Step: push-image
  Image: quay.io/konflux-ci/oras

  Task: modelcar-oci-ta
  Step: sbom-generate
  Image: quay.io/konflux-ci/mobster

  Task: modelcar-oci-ta
  Step: upload-sbom
  Image: quay.io/konflux-ci/appstudio-utils

  Task: modelcar-oci-ta
  Step: report-sbom-url
  Image: quay.io/konflux-ci/yq
```

### Task runner readiness for these steps

Cross-referencing with the [task runner's installed software](https://github.com/konflux-ci/task-runner/blob/main/Installed-Software.md):

| Step | Current image | Tools needed | In task runner? |
|---|---|---|---|
| download-model-files | oras | `oras`, `retry` | Yes |
| create-modelcar-base-image | release-service-utils | `get-image-architectures`, `oras` | `oras` yes, `get-image-architectures` **no** |
| copy-model-files | ubi9/python-311 | `pip install olot` | `python3` yes, `olot` **no** |
| push-image | oras | `oras`, `select-oci-auth`, `retry` | Yes |
| sbom-generate | mobster | `mobster` | **No** |
| upload-sbom | appstudio-utils | `cosign`, `select-oci-auth`, `retry` | Yes |
| report-sbom-url | yq | `yq` | Yes |

4 of 7 steps could use the task runner today. 3 need tools added first (`get-image-architectures`, `olot`, `mobster`).

## Analysis

### What worked

- **ADR-0046 is well-suited to automated enforcement.** The invariant ("steps should use the task runner image") is clear, mechanical, and binary. No LLM interpretation needed.
- **Config-driven approach is flexible.** The exempt image list and scan paths are configurable. Adding new exemptions (e.g., if certain specialized images are legitimately excluded) is a config change, not a code change.
- **The scanner is fast and simple.** 19 tests, ~200 lines of Python, runs in milliseconds.

### What this tells us about the broader problem

- **Not all ADRs are this mechanical.** ADR-0046 has a clear, testable invariant. Many ADRs describe design philosophy, preferred patterns, or architectural intent that can't be reduced to "does this YAML field match this value?" The [layered approach](../problems/architectural-invariants.md) (structural tests for mechanical invariants, LLM comprehension for design-level ones) seems right.
- **Detection is the easy part.** The scanner tells you *what* drifted, but fixing it requires understanding *why* each step uses a particular image and what needs to change. Some fixes are trivial (swap `oras` image for task runner), others require upstream work (add `mobster` to the task runner image first).
- **The two-process model (scanner files issues, fixer takes issues as input) makes sense.** The scanner can run broadly and cheaply. The fixer needs more context and judgment per violation. Separating them lets humans review and prioritize the issues before any fixes are attempted.

### Limitations of this PoC

- Only handles ADR-0046. Not generalizable to other ADRs without new scanner implementations.
- Doesn't understand step scripts — it only checks the image reference, not what tools the script actually uses. A step might use the task runner image but call a tool that isn't installed.
- Doesn't handle the case where a task's `stepTemplate` sets a default image for all steps.
- The scanner checks individual task files but doesn't aggregate across the repo (e.g., "how many tasks total have drift?").

## Next steps

1. **Run against the full build-definitions repo** to get a baseline drift count across all tasks
2. **File GitHub issues** for each task with drift (the scanner already has JSON output that could feed an issue-filing script)
3. **Build the fixer process** that takes filed issues as input and proposes PRs
4. **Explore generalization** — can the config-driven approach extend to other mechanical ADRs?
