#!/usr/bin/env bash
# =============================================================================
# judge.sh — Invokes an independent judge agent on a completed trial
# =============================================================================
#
# Reads the conversation and triage summary from a trial directory, compares
# against the scenario's ground truth, and produces a scored assessment.
#
# Arguments:
#   $1  trial_dir   — Path to the trial directory (contains conversation.json,
#                     triage-summary.md)
#   $2  agent_cli   — CLI to invoke ("claude" or "opencode")
#
# Output:
#   Writes judge-assessment.json to the trial directory.
# =============================================================================

set -euo pipefail

TRIAL_DIR="${1:?Usage: $0 trial_dir agent_cli}"
AGENT_CLI="${2:?Usage: $0 trial_dir agent_cli}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPERIMENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------------------------------------------------------------------------
# Validate inputs
# ---------------------------------------------------------------------------

if [[ ! -f "$TRIAL_DIR/conversation.json" ]]; then
  echo "Error: $TRIAL_DIR/conversation.json not found" >&2
  exit 1
fi
if [[ ! -f "$TRIAL_DIR/triage-summary.md" ]]; then
  echo "Error: $TRIAL_DIR/triage-summary.md not found" >&2
  exit 1
fi

# Determine which scenario this trial belongs to by inspecting the path.
# Expected path structure: results/<timestamp>/<scenario>/<strategy>/
SCENARIO_NAME="$(basename "$(dirname "$TRIAL_DIR")")"
STRATEGY_NAME="$(basename "$TRIAL_DIR")"
SCENARIO_FILE="$EXPERIMENT_DIR/scenarios/${SCENARIO_NAME}.json"

if [[ ! -f "$SCENARIO_FILE" ]]; then
  echo "Error: scenario file not found: $SCENARIO_FILE" >&2
  echo "  (Inferred scenario='$SCENARIO_NAME' from trial dir path)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

CONVERSATION="$(cat "$TRIAL_DIR/conversation.json")"
TRIAGE_SUMMARY="$(cat "$TRIAL_DIR/triage-summary.md")"
GROUND_TRUTH="$(jq '.ground_truth' "$SCENARIO_FILE")"
ORIGINAL_TITLE="$(jq -r '.title' "$SCENARIO_FILE")"
ORIGINAL_BODY="$(jq -r '.body' "$SCENARIO_FILE")"

# Count conversation metrics
NUM_COMMENTS="$(echo "$CONVERSATION" | jq '.comments | length')"
NUM_TRIAGE_QUESTIONS="$(echo "$CONVERSATION" | jq '[.comments[] | select(.author == "triage-agent") | select(.body | startswith("[TRIAGE RESOLVED]") | not)] | length')"

# ---------------------------------------------------------------------------
# Build judge prompt
# ---------------------------------------------------------------------------

read -r -d '' JUDGE_PROMPT << 'JUDGE_EOF' || true
You are an independent judge evaluating the quality of an automated issue
triage process. You will compare a triage agent's output against the ground
truth about what actually happened.

SCORING CRITERIA (each scored 1-5):

1. COMPLETENESS (weight: 25%)
   How much of the ground truth information was extracted during triage?
   5 = All critical details captured
   3 = Most important details captured, some gaps
   1 = Major critical information missing

2. ACCURACY (weight: 25%)
   Is the triaged information consistent with the ground truth?
   5 = Everything stated is accurate
   3 = Mostly accurate, minor inaccuracies
   1 = Contains significant inaccuracies or wrong conclusions

3. EFFICIENCY (weight: 20%)
   Were the conversation turns used well? Were questions redundant?
   5 = Minimal turns, no redundancy, every question added value
   3 = Some unnecessary questions but generally focused
   1 = Many wasted turns, redundant or irrelevant questions

4. QUESTION_QUALITY (weight: 15%)
   Were questions insightful, well-targeted, and appropriate?
   5 = Questions were incisive — they directly uncovered key information
   3 = Questions were reasonable but not particularly insightful
   1 = Questions were generic, vague, or poorly targeted

5. ACTIONABILITY (weight: 15%)
   Could an implementation agent create a fix plan from this triage summary?
   5 = A developer could start coding a fix immediately
   3 = A developer would have a general direction but need more info
   1 = The summary doesn't provide enough to begin work

IMPORTANT: Respond with ONLY valid JSON. Your entire response must be:
{
  "scenario": "<scenario name>",
  "strategy": "<strategy name>",
  "scores": {
    "completeness": <1-5>,
    "accuracy": <1-5>,
    "efficiency": <1-5>,
    "question_quality": <1-5>,
    "actionability": <1-5>
  },
  "weighted_score": <computed weighted average, 2 decimal places>,
  "num_turns": <number of question-answer exchanges>,
  "notable_questions": ["list of the most insightful questions asked"],
  "missed_information": ["list of ground truth details NOT captured"],
  "inaccuracies": ["list of incorrect conclusions or statements"],
  "qualitative_notes": "2-3 sentence overall assessment"
}
JUDGE_EOF

FULL_JUDGE_PROMPT="$JUDGE_PROMPT

--- ORIGINAL ISSUE ---
Title: $ORIGINAL_TITLE
Body: $ORIGINAL_BODY

--- FULL CONVERSATION ---
$CONVERSATION

--- TRIAGE SUMMARY PRODUCED ---
$TRIAGE_SUMMARY

--- GROUND TRUTH (what actually happened) ---
$GROUND_TRUTH

--- METADATA ---
Scenario: $SCENARIO_NAME
Strategy: $STRATEGY_NAME
Total comments: $NUM_COMMENTS
Triage questions asked: $NUM_TRIAGE_QUESTIONS

--- INSTRUCTIONS ---
Evaluate the triage output against the ground truth using the criteria above.
Compute the weighted score as:
  (completeness * 0.25) + (accuracy * 0.25) + (efficiency * 0.20) +
  (question_quality * 0.15) + (actionability * 0.15)
Round to 2 decimal places.
Respond with ONLY valid JSON."

# ---------------------------------------------------------------------------
# Invoke judge agent
# ---------------------------------------------------------------------------

echo "  Invoking judge agent..."

if [[ "$AGENT_CLI" == "claude" ]]; then
  JUDGE_RAW="$(claude -p "$FULL_JUDGE_PROMPT" --output-format text 2>/dev/null)" || true
else
  JUDGE_RAW="$(opencode -p "$FULL_JUDGE_PROMPT" 2>/dev/null)" || true
fi

# ---------------------------------------------------------------------------
# Parse and save
# ---------------------------------------------------------------------------

# Try to extract JSON from the response
extract_json() {
  local raw="$1"
  if echo "$raw" | jq . &>/dev/null 2>&1; then
    echo "$raw"; return 0
  fi
  local fenced
  fenced="$(echo "$raw" | sed -n '/^```json$/,/^```$/p' | sed '1d;$d')"
  if [[ -n "$fenced" ]] && echo "$fenced" | jq . &>/dev/null 2>&1; then
    echo "$fenced"; return 0
  fi
  local braced
  braced="$(echo "$raw" | awk '/{/{found=1} found{print} /}/{if(found) exit}')"
  if [[ -n "$braced" ]] && echo "$braced" | jq . &>/dev/null 2>&1; then
    echo "$braced"; return 0
  fi
  echo "$raw"; return 1
}

JUDGE_JSON="$(extract_json "$JUDGE_RAW")" || {
  echo "  Warning: Could not parse judge response as JSON" >&2
  echo "$JUDGE_RAW" > "$TRIAL_DIR/error-judge-raw.txt"
  # Create a minimal fallback assessment
  JUDGE_JSON="$(jq -n \
    --arg scenario "$SCENARIO_NAME" \
    --arg strategy "$STRATEGY_NAME" \
    '{
      scenario: $scenario,
      strategy: $strategy,
      scores: {completeness:0, accuracy:0, efficiency:0, question_quality:0, actionability:0},
      weighted_score: 0,
      num_turns: 0,
      notable_questions: [],
      missed_information: ["Judge could not parse response"],
      inaccuracies: [],
      qualitative_notes: "Judge agent response could not be parsed. See error-judge-raw.txt."
    }'
  )"
}

echo "$JUDGE_JSON" | jq . > "$TRIAL_DIR/judge-assessment.json"

SCORE="$(echo "$JUDGE_JSON" | jq -r '.weighted_score // "N/A"')"
echo "  Weighted score: $SCORE"
