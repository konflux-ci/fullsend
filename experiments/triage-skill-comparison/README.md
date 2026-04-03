# Experiment: Triage Skill Comparison via GitHub Issue Dialogue

Related: [Issue #126 — Story 3: Triage Agent](https://github.com/fullsend-ai/fullsend/issues/126)

## Hypothesis

Existing third-party coding agent skills designed for interactive brainstorming/clarification (such as obra/superpowers' `brainstorming` skill) can be adapted to perform asynchronous issue triage via GitHub issue comments, producing well-triaged issues from poorly-framed bug reports through iterative question-and-answer cycles.

## Background

Interactive coding agent skills like superpowers' `brainstorming` work by asking one clarifying question at a time in a live terminal session. They refine a vague idea into a well-formed spec through Socratic dialogue. The core question: **can this same pattern work asynchronously over GitHub issue comments, with short-lived agents that die after each interaction?**

### Skills under evaluation

| Skill | Source | Mechanism |
|-------|--------|-----------|
| **superpowers-brainstorming** | [obra/superpowers](https://github.com/obra/superpowers) `skills/brainstorming/SKILL.md` | One question at a time, multiple choice preferred, propose 2-3 approaches, incremental validation |
| **structured-triage** | Custom (baseline) | Checklist-based: expected behavior, actual behavior, reproduction steps, environment — asks for each missing item |
| **socratic-refinement** | Custom (inspired by superpowers + general Socratic method) | Open-ended probing questions, follows up on answers, discovers unstated assumptions and constraints |

#### Note on oh-my-claude and oh-my-openagent

The user mentioned `oh-my-claude` and `oh-my-openagent` as potential tools. These do not appear to exist as public GitHub repositories (confirmed 404 on multiple URL variations). They may be private, renamed, or not yet published. If they surface later, they can be added as additional adapters following the pattern established here.

The experiment uses three strategies that represent the major approaches in the skills ecosystem:
1. A **real third-party skill** (superpowers brainstorming, adapted)
2. A **structured checklist** approach (common in issue templates)
3. A **Socratic open-ended** approach (inspired by the best parts of brainstorming skills)

## Experiment Design

### Architecture

```
                                    GitHub Issue
                                   ┌─────────────┐
                                   │  Title/Body  │
                                   │  Comments    │
                                   └──────┬───────┘
                                          │
                              ┌───────────┴───────────┐
                              │                       │
                    ┌─────────▼─────────┐   ┌────────▼────────┐
                    │   Triage Agent    │   │  Reporter Agent  │
                    │   (short-lived)   │   │  (short-lived)   │
                    │                   │   │                  │
                    │ Reads issue +     │   │ Reads question   │
                    │ comments, decides │   │ comment, answers │
                    │ to ask or resolve │   │ like a human who │
                    │                   │   │ filed the bug    │
                    └─────────┬─────────┘   └────────┬────────┘
                              │                       │
                              ▼                       ▼
                        Post question            Post answer
                        as comment               as comment
                        (then die)               (then die)
```

### Agent lifecycle

Each agent invocation is **single-shot**:

1. **Triage agent** starts, reads the full issue (title, body, all comments), applies the configured skill/strategy to decide: (a) ask a clarifying question, or (b) declare the issue sufficiently triaged and produce a triage summary.
2. If asking a question: posts a comment on the issue, then exits.
3. **Reporter agent** starts (triggered by the new comment), reads the issue + all comments, and responds to the latest question as a human would.
4. The cycle repeats until the triage agent decides the issue is well-understood.

### What the experiment simulates

Since we don't have live GitHub API access from this environment, the experiment uses a **local file-based simulation** of the GitHub issue lifecycle:

- An "issue" is a JSON file containing `title`, `body`, and a `comments` array.
- Agents are invoked via `claude -p` (Claude Code CLI in print mode) or `opencode` with specific prompts.
- Each agent reads the current state of the issue file, produces output, and the orchestrator appends it as a new comment.
- The orchestrator script manages the turn-taking loop.

### Claude Code vs OpenCode limitations

| Aspect | Claude Code (`claude -p`) | OpenCode |
|--------|--------------------------|----------|
| Non-interactive mode | `claude -p "prompt"` reads stdin/args, prints result, exits | `opencode -p "prompt"` or equivalent |
| Skill loading | Skills loaded via CLAUDE.md or plugin system | Skills loaded via .opencode config or AGENTS.md |
| Subagent support | Built-in Task tool | Built-in task/subagent system |
| Max context | Model-dependent (200k tokens typical) | Model-dependent |
| Key constraint | **No `question` tool in `-p` mode** — agent cannot interactively prompt the user. Perfect for our use case: the agent must post to the issue instead. | Same constraint in non-interactive mode |

Both tools work for this experiment. The key insight: **non-interactive mode (`-p`) is exactly the constraint we want**. In interactive mode, skills like brainstorming use the `question` tool to ask the user. In `-p` mode, the agent has no user to ask — it must output its question as text, which we capture and post to the issue.

### Scenarios (fictional issues)

The experiment runs three scenarios, each representing a different quality of initial bug report:

| Scenario | Quality | Description |
|----------|---------|-------------|
| `crash-on-save` | Very poor | "app crashes when I save" — no version, no steps, no error message |
| `slow-search` | Medium | Reports slow search with some context but missing key details (dataset size, query patterns, expected vs actual latency) |
| `auth-redirect-loop` | Good but ambiguous | Detailed report but the actual root cause could be several things; needs clarification on flow and environment |

Each scenario includes:
- An initial issue (`title` + `body`)
- A "ground truth" persona for the reporter agent (what the reporter actually experienced but didn't write down)
- Expected information that a good triage should extract

### Triage strategies (adapters)

Each adapter translates a skill's approach into a system prompt for the triage agent:

#### 1. `superpowers-brainstorming` adapter

Adapts the core principles from obra/superpowers brainstorming:
- One question at a time
- Prefer multiple choice when possible
- Explore approaches before settling
- Scale complexity to what's needed
- YAGNI — don't ask for information you don't need

#### 2. `structured-triage` adapter

A traditional checklist approach:
- Check for: expected behavior, actual behavior, reproduction steps, environment/version, error messages/logs
- Ask for the first missing item
- Move on when all items are present

#### 3. `socratic-refinement` adapter

Open-ended Socratic probing:
- Start with "what were you trying to accomplish?"
- Follow up on each answer with deeper questions
- Discover unstated assumptions
- Probe for edge cases and environmental factors

### Judging criteria

An independent judge agent evaluates each triage outcome on:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| **Completeness** | 25% | Does the triage summary contain all information needed to implement a fix? |
| **Accuracy** | 25% | Is the information consistent with the reporter's ground truth? |
| **Efficiency** | 20% | How many turns did the conversation take? Were questions redundant? |
| **Question quality** | 15% | Were questions insightful, well-targeted, and appropriate? |
| **Actionability** | 15% | Could an implementation agent create a plan from this triage summary? |

Each criterion is scored 1-5. The judge also provides qualitative notes.

## Running the experiment

### Prerequisites

- `claude` CLI installed and authenticated (Claude Code)
- OR `opencode` CLI installed and configured
- bash, jq

### Execution

```bash
# Full experiment (all scenarios x all strategies)
./scripts/run-experiment.sh

# Single scenario with single strategy
./scripts/run-experiment.sh --scenario crash-on-save --strategy superpowers-brainstorming

# With OpenCode instead of Claude
AGENT_CLI=opencode ./scripts/run-experiment.sh

# Dry run (print prompts without executing)
./scripts/run-experiment.sh --dry-run
```

### Output

Results are written to `results/` with the following structure:

```
results/
  <timestamp>/
    crash-on-save/
      superpowers-brainstorming/
        conversation.json     # Full issue + comments
        triage-summary.md     # Final triage output
        judge-assessment.json # Judge scores + notes
      structured-triage/
        ...
      socratic-refinement/
        ...
    slow-search/
      ...
    auth-redirect-loop/
      ...
    summary.md               # Comparison table
```

## File index

| File | Purpose |
|------|---------|
| `scripts/run-experiment.sh` | Main orchestrator — runs all scenario/strategy combinations |
| `scripts/run-single-trial.sh` | Runs one scenario with one strategy through the full dialogue loop |
| `scripts/judge.sh` | Invokes the judge agent on a completed conversation |
| `scripts/seed-app.sh` | Creates a minimal fictional app for the scenarios to reference |
| `scripts/summarize.sh` | Generates the final comparison table |
| `prompts/triage-system.md` | Base system prompt for the triage agent |
| `prompts/reporter-system.md` | Base system prompt for the reporter agent |
| `prompts/judge-system.md` | System prompt for the judge agent |
| `prompts/seed-app.md` | Prompt for the initialization agent to create the fictional app |
| `adapters/superpowers-brainstorming.md` | Triage strategy adapter: superpowers brainstorming |
| `adapters/structured-triage.md` | Triage strategy adapter: structured checklist |
| `adapters/socratic-refinement.md` | Triage strategy adapter: Socratic method |
| `scenarios/crash-on-save.json` | Scenario: very poor bug report |
| `scenarios/slow-search.json` | Scenario: medium quality report |
| `scenarios/auth-redirect-loop.json` | Scenario: good but ambiguous report |

## Design decisions

### Why file-based simulation instead of live GitHub?

1. This experiment environment doesn't have GitHub API access.
2. File-based simulation makes the experiment reproducible and debuggable.
3. The adaptation from file-based to GitHub API is mechanical: replace `jq` reads/writes with `gh api` calls. The `scripts/github-adapter.sh` shows how.
4. The prompts and strategies are the intellectual core; the I/O layer is plumbing.

### Why `-p` (print/non-interactive) mode?

This is the key architectural insight. In interactive mode, brainstorming skills use platform-specific tools (`question` in Claude Code) to ask the user. In `-p` mode, there is no user — the agent must express its question as output text. This is **exactly** the behavior we want for GitHub issue comments: the agent writes a comment and then dies.

No hooks are needed. No skill modification is needed. The constraint of non-interactive mode naturally forces the behavior we want.

### Why not modify the skills directly?

The skills themselves don't need modification. What changes is the **I/O layer**:
- Instead of: skill asks user via `question` tool -> user responds in terminal
- We get: skill outputs question as text -> orchestrator posts as comment -> reporter responds -> next agent invocation reads the response

The skill's decision-making logic (what to ask, when to stop, how to synthesize) stays intact. We extract that logic into adapter prompts that encode the same principles.

### Turn limit

Each trial has a maximum of 8 turns (4 triage questions, 4 reporter answers). If the triage agent hasn't declared sufficiency by then, it must produce a triage summary with whatever it has. This prevents infinite loops and ensures the experiment completes in bounded time.

## Extending the experiment

### Adding a new strategy

1. Create `adapters/my-strategy.md` following the pattern of existing adapters.
2. Add the strategy name to the `STRATEGIES` array in `run-experiment.sh`.
3. Run the experiment.

### Adding a new scenario

1. Create `scenarios/my-scenario.json` with `title`, `body`, and `ground_truth` fields.
2. Add the scenario name to the `SCENARIOS` array in `run-experiment.sh`.
3. Run the experiment.

### Converting to live GitHub

Replace the file I/O in `run-single-trial.sh` with GitHub API calls. A sketch is provided in `scripts/github-adapter.sh`. The core change:
- Read issue: `gh api repos/{owner}/{repo}/issues/{number}` instead of `jq . issue.json`
- Post comment: `gh api repos/{owner}/{repo}/issues/{number}/comments -f body="..."` instead of `jq '.comments += [...]' issue.json`
- Wait for response: poll for new comments or use webhooks + GitHub Actions

The prompts and strategies are unchanged.
