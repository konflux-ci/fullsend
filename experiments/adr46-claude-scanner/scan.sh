#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 <adr-file> <task-yaml-file>" >&2
    exit 1
}

[[ $# -eq 2 ]] || usage

adr_file="$1"
task_file="$2"

[[ -f "$adr_file" ]] || { echo "Error: ADR file not found: $adr_file" >&2; exit 1; }
[[ -f "$task_file" ]] || { echo "Error: Task file not found: $task_file" >&2; exit 1; }

adr_content=$(<"$adr_file")
task_content=$(<"$task_file")

prompt="The following is an Architectural Decision Record (ADR) from the konflux-ci project:

---
${adr_content}
---

The following is a Tekton task definition from the same project:

---
${task_content}
---

Analyze this task for compliance with the ADR. For each violation you find, describe:
- What: which step violates the ADR and what it currently does
- Why: what the ADR requires and why this step doesn't comply
- Fix: what should be done to bring the step into compliance

If a step is legitimately exempt per the ADR, note that and explain why."

# Unset CLAUDECODE to allow invocation from within a claude session
env -u CLAUDECODE claude -p --model claude-sonnet-4-6 "$prompt"
