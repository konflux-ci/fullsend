#!/usr/bin/env bash
# =============================================================================
# summarize.sh — Generates a comparison table from all judge assessments
# =============================================================================
#
# Reads all judge-assessment.json files from a results directory and produces
# a markdown summary with:
#   - A comparison table (scenarios x strategies)
#   - A "best questions" section
#   - A "limitations and observations" section
#
# Arguments:
#   $1  results_dir  — Path to the timestamped results directory
#
# Output:
#   Writes summary.md to the results directory.
# =============================================================================

set -euo pipefail

RESULTS_DIR="${1:?Usage: $0 results_dir}"

if [[ ! -d "$RESULTS_DIR" ]]; then
  echo "Error: results directory not found: $RESULTS_DIR" >&2
  exit 1
fi

SCENARIOS=(crash-on-save slow-search auth-redirect-loop)
STRATEGIES=(superpowers-brainstorming structured-triage socratic-refinement)

OUTPUT="$RESULTS_DIR/summary.md"

# ---------------------------------------------------------------------------
# Helper: read a score from a judge assessment
# ---------------------------------------------------------------------------

get_field() {
  local scenario="$1" strategy="$2" field="$3"
  local file="$RESULTS_DIR/$scenario/$strategy/judge-assessment.json"
  if [[ -f "$file" ]]; then
    jq -r "$field" "$file" 2>/dev/null || echo "N/A"
  else
    echo "N/A"
  fi
}

# ---------------------------------------------------------------------------
# Generate summary
# ---------------------------------------------------------------------------

{
  cat << 'HEADER'
# Triage Skill Comparison — Experiment Results

## Methodology

Three fictional bug report scenarios of varying quality were triaged by an
AI agent using three different triage strategies. Each scenario x strategy
combination ran as an independent trial with up to 8 dialogue turns. An
independent judge agent then scored each trial on five criteria.

### Scoring Criteria

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Completeness | 25% | Did the triage capture all ground truth details? |
| Accuracy | 25% | Is the triaged information factually correct? |
| Efficiency | 20% | Were turns used well, without redundancy? |
| Question Quality | 15% | Were questions insightful and well-targeted? |
| Actionability | 15% | Could a developer start fixing from the triage summary? |

---

## Overall Scores

HEADER

  # --- Weighted score comparison table ---

  echo "| Scenario | superpowers-brainstorming | structured-triage | socratic-refinement |"
  echo "|----------|:------------------------:|:-----------------:|:-------------------:|"

  for scenario in "${SCENARIOS[@]}"; do
    row="| \`$scenario\`"
    for strategy in "${STRATEGIES[@]}"; do
      score="$(get_field "$scenario" "$strategy" '.weighted_score')"
      row="$row | $score"
    done
    echo "$row |"
  done

  # Compute averages per strategy
  echo ""
  echo "### Strategy Averages"
  echo ""
  echo "| Strategy | Avg Weighted Score | Avg Turns |"
  echo "|----------|:------------------:|:---------:|"

  for strategy in "${STRATEGIES[@]}"; do
    total_score=0
    total_turns=0
    count=0
    for scenario in "${SCENARIOS[@]}"; do
      score="$(get_field "$scenario" "$strategy" '.weighted_score')"
      turns="$(get_field "$scenario" "$strategy" '.num_turns')"
      if [[ "$score" != "N/A" && "$score" != "null" ]]; then
        total_score="$(echo "$total_score + $score" | bc -l)"
        count=$((count + 1))
      fi
      if [[ "$turns" != "N/A" && "$turns" != "null" ]]; then
        total_turns="$(echo "$total_turns + $turns" | bc -l)"
      fi
    done
    if [[ $count -gt 0 ]]; then
      avg_score="$(printf '%.2f' "$(echo "$total_score / $count" | bc -l)")"
      avg_turns="$(printf '%.1f' "$(echo "$total_turns / $count" | bc -l)")"
    else
      avg_score="N/A"
      avg_turns="N/A"
    fi
    echo "| \`$strategy\` | $avg_score | $avg_turns |"
  done

  # --- Detailed scores per trial ---

  echo ""
  echo "---"
  echo ""
  echo "## Detailed Scores"
  echo ""

  for scenario in "${SCENARIOS[@]}"; do
    echo "### Scenario: \`$scenario\`"
    echo ""
    echo "| Criterion | superpowers-brainstorming | structured-triage | socratic-refinement |"
    echo "|-----------|:------------------------:|:-----------------:|:-------------------:|"

    for criterion in completeness accuracy efficiency question_quality actionability; do
      row="| $criterion"
      for strategy in "${STRATEGIES[@]}"; do
        val="$(get_field "$scenario" "$strategy" ".scores.$criterion")"
        row="$row | $val"
      done
      echo "$row |"
    done

    row="| **Weighted**"
    for strategy in "${STRATEGIES[@]}"; do
      val="$(get_field "$scenario" "$strategy" '.weighted_score')"
      row="$row | **$val**"
    done
    echo "$row |"

    row="| Turns"
    for strategy in "${STRATEGIES[@]}"; do
      val="$(get_field "$scenario" "$strategy" '.num_turns')"
      row="$row | $val"
    done
    echo "$row |"

    echo ""
  done

  # --- Best questions ---

  echo "---"
  echo ""
  echo "## Notable Questions"
  echo ""
  echo "The most insightful questions identified by the judge for each trial:"
  echo ""

  for scenario in "${SCENARIOS[@]}"; do
    for strategy in "${STRATEGIES[@]}"; do
      file="$RESULTS_DIR/$scenario/$strategy/judge-assessment.json"
      if [[ -f "$file" ]]; then
        questions="$(jq -r '.notable_questions // [] | .[]' "$file" 2>/dev/null)"
        if [[ -n "$questions" ]]; then
          echo "**\`$scenario\` × \`$strategy\`:**"
          while IFS= read -r q; do
            echo "- $q"
          done <<< "$questions"
          echo ""
        fi
      fi
    done
  done

  # --- Qualitative notes ---

  echo "---"
  echo ""
  echo "## Qualitative Assessments"
  echo ""

  for scenario in "${SCENARIOS[@]}"; do
    for strategy in "${STRATEGIES[@]}"; do
      notes="$(get_field "$scenario" "$strategy" '.qualitative_notes')"
      if [[ "$notes" != "N/A" && "$notes" != "null" ]]; then
        echo "**\`$scenario\` × \`$strategy\`:** $notes"
        echo ""
      fi
    done
  done

  # --- Missed information ---

  echo "---"
  echo ""
  echo "## Information Gaps"
  echo ""
  echo "Ground truth details that were NOT captured during triage:"
  echo ""

  for scenario in "${SCENARIOS[@]}"; do
    for strategy in "${STRATEGIES[@]}"; do
      file="$RESULTS_DIR/$scenario/$strategy/judge-assessment.json"
      if [[ -f "$file" ]]; then
        missed="$(jq -r '.missed_information // [] | .[]' "$file" 2>/dev/null)"
        if [[ -n "$missed" ]]; then
          echo "**\`$scenario\` × \`$strategy\`:**"
          while IFS= read -r m; do
            echo "- $m"
          done <<< "$missed"
          echo ""
        fi
      fi
    done
  done

  # --- Limitations ---

  echo "---"
  echo ""
  echo "## Limitations and Observations"
  echo ""
  cat << 'LIMITATIONS'
1. **Simulated reporters.** The "reporter" is an AI agent with access to the
   ground truth. Real humans may give more ambiguous, emotional, or tangential
   answers. The reporter agent is instructed to behave naturally, but this is
   an approximation.

2. **Single run.** Each scenario x strategy was run once. LLM outputs are
   non-deterministic; running multiple times would give more reliable averages.
   Consider running 3-5 trials per combination for statistical significance.

3. **Judge subjectivity.** The judge is also an LLM. Its scores are consistent
   within a run but may vary across runs. Consider using multiple judge
   invocations and averaging.

4. **Prompt sensitivity.** Results depend heavily on the exact wording of the
   adapter prompts. Small changes to the triage strategy description can
   significantly affect agent behavior.

5. **Context window pressure.** As conversations grow longer, later turns have
   more context to process. This may disadvantage strategies that ask more
   questions (more tokens in context = more room for confusion).

6. **No tool access.** Agents cannot actually inspect code, run searches, or
   query databases. In a real triage scenario, an agent with tool access might
   resolve issues faster by investigating directly.

7. **File-based simulation.** This experiment simulates GitHub issue I/O via
   local JSON files. The adaptation to real GitHub API is mechanical (see
   `github-adapter.sh`) but untested.
LIMITATIONS

} > "$OUTPUT"

echo "Summary written to: $OUTPUT"
