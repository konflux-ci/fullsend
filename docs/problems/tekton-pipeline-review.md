# Tekton Pipeline Review

Reviewing Tekton pipeline and task definitions is a distinct problem domain from reviewing application code. The konflux-ci org's most critical repository — [build-definitions](https://github.com/konflux-ci/build-definitions) — is almost entirely Tekton YAML with embedded shell. If agents can't review this content well, the entire autonomous development vision has a blind spot at the most security-sensitive layer.

## Why pipeline definitions are special

### They're infrastructure-as-code for the build system

Every Konflux build runs through a pipeline defined in build-definitions. Changes to these pipelines affect every user's builds. A bug in a Go controller might break one workflow; a bug in a build pipeline definition breaks every build that uses it. The blast radius is categorically different.

### They're multi-language by nature

A single Tekton task YAML file typically contains:

- **YAML structure** — task metadata, step definitions, parameter declarations, result declarations, workspace declarations
- **Shell scripts** — the actual logic, embedded in `script:` fields, often 50-200 lines of bash
- **OCI image references** — each step's container image, often with digest pinning
- **Tekton parameter substitution** — `$(params.foo)`, `$(results.bar.path)`, `$(workspaces.source.path)` expressions interpolated into the shell scripts
- **Occasional Python or other languages** — some steps embed Python scripts instead of bash

No single review model handles all of these well. A Go correctness agent doesn't understand bash. A shell linter doesn't understand Tekton parameter substitution. An image vulnerability scanner doesn't understand the YAML structure.

### The stringly-typed interface problem

Tekton pipelines compose tasks through string-based interfaces:

```yaml
# Pipeline passes a result from task A to task B
- name: build
  taskRef:
    name: buildah
  params:
    - name: IMAGE
      value: "$(tasks.clone.results.IMAGE_URL)"
```

If `clone` doesn't produce a result called `IMAGE_URL`, or produces it conditionally, or the name is subtly misspelled (`IMAGE_Url`), this fails at runtime — not at review time, not at admission time, not at any static check. The pipeline YAML is syntactically valid. The parameter reference resolves to an empty string or causes a Tekton resolution error.

Human reviewers catch these by familiarity with the specific tasks involved. They know which results a task produces because they've worked with it before. An agent needs this knowledge explicitly — either by loading the referenced task definitions or by having a schema of task inputs/outputs.

### Trusted tasks and the security model

Konflux's trusted task model (ADR-0053) means that specific tasks are blessed and their provenance is verified. Changes to trusted tasks have security implications beyond normal code changes:

- Modifying a trusted task's behavior changes what every pipeline using it does
- Adding or removing steps changes the security surface
- Changing image references in trusted tasks can introduce supply chain risks
- The trust boundary between the task definition (controlled by build-definitions maintainers) and the user's pipeline definition (controlled by the user) is a critical security seam

A review agent that doesn't understand the trusted task model will miss the significance of changes at this boundary.

## What a pipeline review agent needs to understand

### 1. Task-level semantics

- **Step ordering and dependencies** — steps within a task run sequentially. The review agent needs to understand data flow between steps (via workspace mounts, result files, environment variables).
- **Step image correctness** — is the image appropriate for what the script does? Does the image contain the tools the script calls? See the ADR-0046 drift scanner experiment for a mechanical version of this check.
- **Resource declarations** — are workspaces, volumes, and resource requests correct? Over-requesting resources wastes cluster capacity; under-requesting causes OOM kills.
- **Result declarations and writes** — does every declared result get written to in all code paths? A result that's declared but not written (because an error path skipped it) will cause downstream pipeline failures.

### 2. Pipeline-level semantics

- **Task graph correctness** — are `runAfter` declarations correct? Are there missing dependencies (task B reads task A's result but doesn't declare `runAfter: [A]`)?
- **Parameter threading** — do pipeline-level parameters correctly flow to task-level parameters? Are types consistent? Are there unused parameters that suggest a wiring error?
- **Result aggregation** — does the pipeline correctly aggregate task results into pipeline results? Missing aggregations mean the pipeline's consumers lose data.
- **When expressions** — conditional task execution. Does the pipeline behave correctly when a task is skipped? Do downstream tasks handle the absence of results from skipped tasks?
- **Matrix/fan-out** — parameterized fan-out. Are the matrix combinations correct? Does the fan-in (result aggregation from matrix runs) work?

### 3. Embedded shell review

This is arguably the hardest part. Embedded shell scripts need:

- **Correctness**: proper quoting (`"$VAR"` not `$VAR`), error handling (`set -euo pipefail`), exit code propagation, handling of special characters in filenames/URLs
- **Security**: command injection risks (especially when parameters come from user input via `$(params.*)`), credential handling, secret exposure in logs
- **Portability**: assumptions about the container environment (available tools, filesystem layout, network access)
- **Tekton-specific patterns**: writing results to `$(results.*.path)`, reading workspaces from `$(workspaces.*.path)`, handling optional workspaces

The Tekton parameter substitution (`$(params.foo)`) happens *before* the shell script runs, which means it's essentially string interpolation into shell. If `$(params.foo)` contains shell metacharacters, the script breaks or worse — it's a command injection vector. Human reviewers who work on build-definitions know to look for this. A generic code review agent won't.

### 4. Cross-cutting concerns

- **Backwards compatibility** — changing a task's parameters, results, or behavior breaks all pipelines that use the current version. Tekton's versioning model (tasks are versioned by directory: `task/buildah/0.1/`, `task/buildah/0.2/`) mitigates this, but only if the reviewer enforces it. Changes to an existing version must be backwards-compatible; breaking changes need a new version.
- **Migration path** — when a new task version is introduced, existing pipelines need migration. A review agent should flag when a new version is created without a corresponding migration plan or pipeline update.
- **Performance** — pipeline execution time matters. Adding steps, pulling larger images, or doing redundant work affects every build. Human reviewers consider this; agents need to be prompted to.

## Relationship to other problem areas

- **Code review** — Tekton pipeline review is a specialization of the general code review problem. The sub-agent decomposition in [code-review.md](code-review.md) needs to account for this content type.
- **Architectural invariants** — ADRs like 0046 (common task runner image) and 0053 (trusted task model) define invariants specific to pipeline definitions. The drift scanner experiment enforces one such invariant mechanically.
- **Security threat model** — pipeline definitions are a prime target for supply chain attacks. A compromised task definition affects every build using it. The content security agent from [agent-architecture.md](agent-architecture.md) needs deep Tekton knowledge.
- **Repo readiness** — build-definitions has no coverage data on the dashboard. Its "tests" are primarily integration tests (running pipelines in a cluster). Assessing readiness for agent autonomy requires different criteria than for Go repos.

## Open questions

- Should there be a dedicated Tekton review sub-agent, or should the existing sub-agents be parameterized per content type?
- Can we build a static analysis tool for Tekton parameter threading — checking that task A's results match task B's parameter references at PR time rather than runtime?
- How do we handle the embedded shell problem? ShellCheck can lint bash, but it doesn't understand Tekton parameter substitution (`$(params.*)` looks like shell arithmetic to ShellCheck).
- Can we derive a task interface schema (inputs, outputs, side effects) automatically from existing task definitions? This would help review agents verify pipeline wiring without loading full task definitions.
- How do we handle the versioning boundary — detecting when a change to `task/foo/0.1/` should actually be a new `task/foo/0.2/`?
- What does "test coverage" mean for a Tekton task? The task itself isn't tested in isolation — it's tested by running the pipeline in a cluster. How do we assess test adequacy for review purposes?
- How do we handle the `stepTemplate` pattern — where a task sets a default image for all steps? The drift scanner experiment doesn't handle this yet.
