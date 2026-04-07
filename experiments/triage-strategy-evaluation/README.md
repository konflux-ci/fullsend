# Experiment: Triage Strategy Evaluation (v2)

Related: [Issue #126 — Story 3: Triage Agent](https://github.com/fullsend-ai/fullsend/issues/126)

Successor to the [triage-skill-comparison](../triage-skill-comparison/) experiment, which compared five questioning strategies across three scenarios. That study produced directionally useful results but had methodological limitations that this experiment addresses.

## What changed from v1

| Concern | v1 behavior | v2 fix |
|---------|------------|--------|
| Too few scenarios | 3 scenarios, rankings sensitive to individual scenario fit | 10 scenarios spanning 7 bug archetypes |
| Unrealistic reporter | Perfect recall, always cooperative | Reporter has a realism profile: sometimes uncertain, forgetful, or verbose with irrelevant details |
| Same model judges itself | Triage agent and judge share blind spots | `--judge-model` flag; default judge uses a different model than the triage agent |
| Premature resolution bias | Binary "ASK or RESOLVE" with no friction on resolve | Reframed: agent must justify readiness to resolve and self-check against its own information gaps |
| Unequal adapter effort | Adapters varied 20-84 lines; baselines were intentionally simple | All adapters normalized to ~40-50 lines with the same structural template |
| Efficiency criterion contradicts itself | Penalizes both wasted turns and premature closure, with no clear boundary | Split into **thoroughness** (did it ask enough?) and **economy** (did it waste turns?) |
| Parse failures distort scores | JSON formatting errors counted as strategy failures | Separate **reliability** metric; parse failures excluded from quality scores |
| Single correct interpretation | Ground truth has one root cause hierarchy | Judge evaluates against a set of **acceptable diagnostic paths**, not just the canonical one |

## Hypothesis

The same hypothesis as v1 — that interactive questioning strategies can be adapted for asynchronous GitHub issue triage — but with a sharper question: **which strategy properties matter, and under what conditions?**

Specifically:
1. Do phased/gated strategies (omo-prometheus, omc-deep-interview) outperform ungated ones (socratic-refinement, structured-triage) when the reporter is realistic rather than ideal?
2. Does the v1 finding of "premature resolution as the dominant failure mode" persist when the prompt framing no longer biases toward closure?
3. Do strategy rankings change across bug archetypes, or is one strategy universally better?

## Scenarios (10)

| # | Scenario | Archetype | Quality | Causal structure |
|---|----------|-----------|---------|-----------------|
| 1 | `crash-on-save` | Data/encoding | Very poor | Single cause, size-dependent trigger |
| 2 | `slow-search` | Performance regression | Medium | Single cause, clear diagnostic signal |
| 3 | `auth-redirect-loop` | Auth/integration | Good but ambiguous | Two interacting causes |
| 4 | `silent-data-corruption` | Data integrity | Medium | Subtle regex bug, batch process |
| 5 | `flaky-ci` | Testing/CI | Poor | Environment-dependent, non-deterministic |
| 6 | `memory-leak` | Resource/performance | Good (has metrics) | Gradual degradation, needs profiling |
| 7 | `intermittent-403` | Infrastructure/deployment | Medium | Stale deployment on 1-of-N servers |
| 8 | `email-delay` | Queue/integration | Medium-good | Priority inversion in queue |
| 9 | `file-upload-corruption` | Data/encoding | Poor | Size-dependent path split |
| 10 | `wrong-search-results` | Logic/data | Medium | Schema mapping inversion after migration |

Scenarios 1-3 are carried over from v1 (ground truth unchanged) for continuity. Scenarios 4-10 are new and chosen to cover archetypes that v1 missed: batch processing bugs, CI/infrastructure issues, gradual degradation, and logic errors.

### Scenario design principles

- **Multiple acceptable diagnostic paths.** Each scenario's ground truth includes `acceptable_paths` — alternative valid triage conclusions that are not the canonical root cause but would still lead a developer in a productive direction.
- **Reporter realism profiles.** Each scenario specifies a `reporter_profile` controlling how the simulated reporter behaves (see Reporter realism below).
- **Difficulty calibration.** Scenarios are tagged with expected difficulty (easy / medium / hard) based on how many questions an ideal triager would need.

## Strategies (5, normalized)

Same five strategies as v1, but with normalized adapters:

| # | Strategy | Source | Core mechanism |
|---|----------|--------|---------------|
| 1 | `superpowers-brainstorming` | obra/superpowers | One question, multiple choice, YAGNI, judgment-based sufficiency |
| 2 | `omc-deep-interview` | oh-my-claudecode | Clarity dimension scoring, ambiguity gating, challenge modes |
| 3 | `omo-prometheus` | oh-my-openagent | Phased engineer interview, pushes back on vague answers |
| 4 | `structured-triage` | Custom baseline | Checklist: expected/actual behavior, steps, environment, errors, frequency |
| 5 | `socratic-refinement` | Custom baseline | Open-ended Socratic probing, follows conversational threads |

### Adapter normalization

All adapters follow the same template:
1. **Approach** (1 paragraph) — what this strategy does differently
2. **Questioning rules** (4-6 numbered rules)
3. **Sufficiency criteria** — when to resolve
4. **When to stop asking** — when further questions have diminishing returns

Target length: 40-50 lines each. No adapter includes output format extensions (like `clarity_scores` or `confidence`) — those were removed because they conflated strategy evaluation with output format compliance.

## Key design changes

### Reporter realism

The reporter agent receives a `reporter_profile` from the scenario that controls its behavior:

| Profile | Behavior |
|---------|----------|
| `cooperative` | Answers fully from ground truth (v1 behavior, used sparingly as a control) |
| `typical` | Sometimes says "I'm not sure" or "I don't remember exactly"; gives partial answers to broad questions; occasionally volunteers irrelevant details |
| `difficult` | Misremembers some details; gives confidently wrong information on non-critical points; needs specific questions to surface key details; gets frustrated with overly technical questions |

Most scenarios use `typical`. One or two use `cooperative` (easy scenarios) and one or two use `difficult` (hard scenarios).

### Resolve/ask reframing

v1's triage prompt said:

> Decide: ASK a clarifying question or RESOLVE the issue.

v2 replaces this with:

> Your default action is to ask a clarifying question. You should only resolve when you are confident you have enough information for a developer to act without contacting the reporter again. Before resolving, review your own information gaps — if you have listed gaps that a question could fill, you should ask rather than resolve.

This makes "ask" the default and "resolve" the marked choice, reducing the bias toward premature closure observed in v1.

### Judge improvements

1. **Separate model.** The `--judge-model` flag allows using a different model (default: `claude-sonnet-4-6`) so the judge doesn't share the triage agent's blind spots.
2. **Split efficiency into thoroughness + economy.** Thoroughness asks "did it ask enough before resolving?" Economy asks "did it waste turns?" These are no longer in tension.
3. **Reliability metric.** Parse failures and malformed output are tracked separately. Trials where the agent produced unparseable output are flagged and excluded from quality scores, with a separate reliability rate reported per strategy.
4. **Acceptable diagnostic paths.** The judge receives not just the canonical root cause but a set of acceptable alternative conclusions. A triage that identifies a valid alternative path scores well on accuracy even if it doesn't match the canonical cause exactly.

### Scoring rubric (revised)

| Criterion | Weight | What it measures |
|-----------|--------|-----------------|
| Completeness | 25% | Did the triage extract the expected information? |
| Accuracy | 25% | Is the summary consistent with ground truth or an acceptable path? |
| Thoroughness | 15% | Did the agent ask enough questions before resolving? Were there obvious follow-ups it skipped? |
| Economy | 10% | Were turns well-spent? Any redundant or low-value questions? |
| Question quality | 15% | Were questions insightful and diagnostic? |
| Actionability | 10% | Could a developer start fixing from this summary? |

**Reliability** (parse success rate) is reported separately, not included in the weighted total.

## Running the experiment

### Prerequisites

- `claude` CLI authenticated, OR `opencode` CLI configured
- `bash`, `jq`

### Quick start

```bash
# Full experiment: 10 scenarios x 5 strategies x 5 trials = 250 runs
./scripts/run-experiment.sh

# Fewer trials for faster iteration
./scripts/run-experiment.sh --trials 2

# Single cell
./scripts/run-experiment.sh --scenario crash-on-save --strategy omc-deep-interview

# Use a different model for judging
./scripts/run-experiment.sh --judge-model claude-sonnet-4-6

# Dry run (print prompts without invoking agents)
./scripts/run-experiment.sh --dry-run
```

### Output structure

```
results/<timestamp>/
  seed-app/
  crash-on-save/
    superpowers-brainstorming/
      trial-1/
        conversation.json
        conversation.md
        triage-summary.json
        triage-summary.md
        judge-assessment.json
      trial-2/
        ...
    scenario-analysis.json
  slow-search/
    ...
  summary.md
```

## Extending the experiment

### Adding a new strategy

1. Create `adapters/my-strategy.md` following the normalized template (see existing adapters).
2. Add the name to the `STRATEGIES` array in `run-experiment.sh`.

### Adding a new scenario

1. Create `scenarios/my-scenario.json` with `title`, `body`, `quality`, `ground_truth` (including `acceptable_paths`), `expected_triage_extracts`, and `reporter_profile`.
2. Add the name to the `SCENARIOS` array in `run-experiment.sh`.

## File index

| File | Purpose |
|------|---------|
| `adapters/*.md` | Strategy adapters (normalized, ~40-50 lines each) |
| `scenarios/*.json` | Bug report scenarios with ground truth and reporter profiles |
| `prompts/triage-system.md` | Triage agent system prompt (revised resolve/ask framing) |
| `prompts/reporter-system.md` | Reporter agent system prompt (with realism profiles) |
| `prompts/judge-system.md` | Judge agent scoring rubric (revised, split efficiency) |
| `prompts/scenario-analysis-system.md` | Cross-strategy analysis prompt |
| `scripts/run-experiment.sh` | Main orchestrator |
| `scripts/run-single-trial.sh` | Single scenario x strategy dialogue loop |
| `scripts/judge.sh` | Judge agent invocation |
| `scripts/analyze-scenario.sh` | Cross-strategy scenario analysis |
| `scripts/summarize.sh` | Summary table generator (multi-trial aggregation) |
