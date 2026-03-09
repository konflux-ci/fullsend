# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Fullsend is a living design document exploring fully autonomous agentic development for the [konflux-ci](https://github.com/konflux-ci/) GitHub organization. It contains no application code — only prose documents organized by problem domain.

## Repository structure

```
docs/
  vision.md                         # The overarching goal and principles
  problems/                         # One file per problem domain, evolving independently
    intent-representation.md        # How to capture/verify what changes are wanted
    security-threat-model.md        # Prompt injection, insider threats, agent drift, supply chain
    agent-architecture.md           # Agent roles, authority, interaction patterns
    autonomy-spectrum.md            # When to auto-merge vs. escalate
    governance.md                   # Who controls the agents and their config
    repo-readiness.md               # Test coverage baseline and readiness criteria
    code-review.md                  # How agents review code, security sub-agents
    tekton-pipeline-review.md       # Reviewing Tekton tasks/pipelines as a distinct domain
    architectural-invariants.md     # Enforcing things that must always be true
    multi-tenancy.md                # How agents preserve tenant isolation boundaries
    migration-path.md               # Incremental path from human-driven to agent-driven
  landscape.md                      # Survey of AI code review tools (time-sensitive)
  experiments/                      # Logs/results from practical experiments
```

## How to work in this repo

- This is a design exploration, not a spec. Documents should present multiple options with trade-offs, not prescribe single solutions.
- Each problem document has an "Open questions" section — this is where unresolved issues live.
- When adding new problem areas, create a new file in `docs/problems/` and link it from `README.md`.
- The security threat model (threat priority: external injection > insider > drift > supply chain) should inform all other documents.
- Coverage data in `repo-readiness.md` references the live dashboard at https://konflux-ci.dev/coverage-dashboard/ and may need periodic updates.
- The target audience is the konflux-ci contributor community — keep language accessible, avoid presuming solutions.

## Key design decisions made

- **Autonomy model:** Binary per-repo, with CODEOWNERS enforcing human approval on specific paths
- **Problem structure:** Problem-oriented documents (not ADRs or RFCs) that can evolve independently, with ADRs spun off later when decisions crystallize
- **Threat priority order:** External prompt injection > insider/compromised creds > agent drift > supply chain
- **Scope:** All repos in the konflux-ci org (heterogeneous — Go, React, Tekton, Python, shell)
- **Code generation is considered a solved problem.** The hard problems are review, intent, governance, and security.
- **Trust derives from repository permissions, not agent identity.** No agent trusts another based on who produced the output.
- **CODEOWNERS files are always human-owned.** Agents cannot modify their own guardrails.
- **The repo is the coordinator.** No coordinator agent — branch protection, CODEOWNERS, and status checks are the coordination layer.
- **The konflux-ci/architecture repo** is a key source of architectural invariants that agents should enforce.
