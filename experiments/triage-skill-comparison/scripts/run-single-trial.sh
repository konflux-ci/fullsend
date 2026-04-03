#!/usr/bin/env bash
# =============================================================================
# run-single-trial.sh — Runs one scenario x strategy through the dialogue loop
# =============================================================================
#
# This script simulates the asynchronous GitHub issue triage cycle:
#
#   1. Triage agent reads the issue + comments, decides to ASK or RESOLVE
#   2. If ASK:  question is appended as a comment
#   3. Reporter agent reads the issue + comments, answers the question
#   4. Answer is appended as a comment
#   5. Repeat until RESOLVE or max turns reached
#
# The "issue" is a JSON file with { title, body, comments: [...] }.
# Agents are invoked via `claude -p` or `opencode -p` in single-shot mode.
#
# Arguments:
#   $1  scenario_name   — Name of the scenario (matches scenarios/*.json)
#   $2  strategy_name   — Name of the strategy (matches adapters/*.md)
#   $3  trial_dir       — Directory to write outputs into
#   $4  max_turns       — Maximum number of dialogue turns
#   $5  agent_cli       — CLI to invoke ("claude" or "opencode")
#   $6  [--dry-run]     — Optional: print prompts instead of invoking agents
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

SCENARIO_NAME="${1:?Usage: $0 scenario strategy trial_dir max_turns agent_cli [--dry-run]}"
STRATEGY_NAME="${2:?}"
TRIAL_DIR="${3:?}"
MAX_TURNS="${4:?}"
AGENT_CLI="${5:?}"
DRY_RUN=false
if [[ "${6:-}" == "--dry-run" ]]; then
  DRY_RUN=true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPERIMENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------------------------------------------------------------------------
# Load scenario, adapter, and prompts
# ---------------------------------------------------------------------------

SCENARIO_FILE="$EXPERIMENT_DIR/scenarios/${SCENARIO_NAME}.json"
ADAPTER_FILE="$EXPERIMENT_DIR/adapters/${STRATEGY_NAME}.md"

if [[ ! -f "$SCENARIO_FILE" ]]; then
  echo "Error: scenario file not found: $SCENARIO_FILE" >&2
  exit 1
fi
if [[ ! -f "$ADAPTER_FILE" ]]; then
  echo "Error: adapter file not found: $ADAPTER_FILE" >&2
  exit 1
fi

SCENARIO_JSON="$(cat "$SCENARIO_FILE")"
ADAPTER_PROMPT="$(cat "$ADAPTER_FILE")"

# Extract scenario fields
ISSUE_TITLE="$(echo "$SCENARIO_JSON" | jq -r '.title')"
ISSUE_BODY="$(echo "$SCENARIO_JSON" | jq -r '.body')"
GROUND_TRUTH="$(echo "$SCENARIO_JSON" | jq -r '.ground_truth | tojson')"

# ---------------------------------------------------------------------------
# Base system prompts (embedded here for self-containment)
# ---------------------------------------------------------------------------

read -r -d '' TRIAGE_SYSTEM_PROMPT << 'TRIAGE_EOF' || true
You are a triage agent for a software project called TaskFlow. Your job is to
examine a GitHub issue and its comment history, then either:

(a) Ask ONE clarifying question to the reporter, or
(b) Declare the issue sufficiently triaged and produce a triage summary.

IMPORTANT: You must respond with ONLY valid JSON. No markdown fences, no
explanation outside the JSON. Your entire response must be a single JSON object.

If you decide to ASK a question, respond with:
{
  "action": "ask",
  "question": "Your single clarifying question here"
}

If you decide to RESOLVE (the issue is sufficiently understood), respond with:
{
  "action": "resolve",
  "triage_summary": {
    "title": "Refined issue title",
    "problem": "Clear description of the problem",
    "root_cause_hypothesis": "Most likely root cause based on available info",
    "reproduction_steps": ["step 1", "step 2", "..."],
    "environment": "Relevant environment details",
    "severity": "critical | high | medium | low",
    "recommended_fix": "What a developer should do to fix this",
    "information_gaps": ["Any remaining unknowns that didn't block triage"]
  }
}

Decision guidance:
- Resolve when you have enough information for a developer to create an
  implementation plan and fix the issue.
- Ask when critical information is missing that would change the approach.
- Do NOT ask questions whose answers wouldn't change your triage outcome.
TRIAGE_EOF

read -r -d '' REPORTER_SYSTEM_PROMPT << 'REPORTER_EOF' || true
You are a person who filed a bug report on a software project. A triage
agent is asking you clarifying questions about your issue. Answer them
based on YOUR ACTUAL EXPERIENCE described in the ground truth below.

Rules:
- Answer naturally, as a real user would — not as a developer or tester.
- Only share information that YOU would know from your experience. Don't
  volunteer technical root cause details unless the question specifically
  leads you to reveal them.
- If the question touches on something from your ground truth experience,
  share that specific detail. If it doesn't, give a reasonable "I'm not
  sure" or "I don't think so" answer.
- Keep answers concise (1-3 sentences typical, occasionally longer if the
  question warrants it).
- You may express frustration or urgency — you're a real person with a
  real problem.

IMPORTANT: You must respond with ONLY valid JSON. No markdown fences, no
explanation outside the JSON. Your entire response must be a single JSON object:
{
  "answer": "Your response to the question"
}
REPORTER_EOF

# ---------------------------------------------------------------------------
# Initialize issue state
# ---------------------------------------------------------------------------

ISSUE_JSON="$(jq -n \
  --arg title "$ISSUE_TITLE" \
  --arg body "$ISSUE_BODY" \
  '{title: $title, body: $body, comments: []}'
)"

# ---------------------------------------------------------------------------
# Helper: invoke agent CLI
# ---------------------------------------------------------------------------

invoke_agent() {
  local prompt="$1"

  if $DRY_RUN; then
    echo "[dry-run] Would invoke $AGENT_CLI with prompt (${#prompt} chars):"
    echo "---BEGIN PROMPT---"
    # Print first 500 chars to keep dry-run output manageable
    echo "${prompt:0:500}..."
    echo "---END PROMPT (truncated)---"
    echo ""
    return 0
  fi

  local result
  if [[ "$AGENT_CLI" == "claude" ]]; then
    # claude -p takes the prompt as an argument
    result="$(claude -p "$prompt" --output-format text 2>/dev/null)" || true
  else
    # opencode -p also takes the prompt as an argument
    result="$(opencode -p "$prompt" 2>/dev/null)" || true
  fi

  echo "$result"
}

# ---------------------------------------------------------------------------
# Helper: extract JSON from agent response
# ---------------------------------------------------------------------------
# Agents are instructed to return pure JSON, but sometimes they wrap it in
# markdown fences or add preamble. This function tries to extract valid JSON.

extract_json() {
  local raw="$1"

  # Try the raw string first
  if echo "$raw" | jq . &>/dev/null 2>&1; then
    echo "$raw"
    return 0
  fi

  # Try extracting from markdown json fence
  local fenced
  fenced="$(echo "$raw" | sed -n '/^```json$/,/^```$/p' | sed '1d;$d')"
  if [[ -n "$fenced" ]] && echo "$fenced" | jq . &>/dev/null 2>&1; then
    echo "$fenced"
    return 0
  fi

  # Try extracting from generic markdown fence
  fenced="$(echo "$raw" | sed -n '/^```$/,/^```$/p' | sed '1d;$d')"
  if [[ -n "$fenced" ]] && echo "$fenced" | jq . &>/dev/null 2>&1; then
    echo "$fenced"
    return 0
  fi

  # Try to find the first { ... } block using grep + awk
  local braced
  braced="$(echo "$raw" | awk '/{/{found=1} found{print} /}/{if(found) exit}')"
  if [[ -n "$braced" ]] && echo "$braced" | jq . &>/dev/null 2>&1; then
    echo "$braced"
    return 0
  fi

  # Give up — return raw and let the caller handle the error
  echo "$raw"
  return 1
}

# ---------------------------------------------------------------------------
# Dialogue loop
# ---------------------------------------------------------------------------

TURN=0

echo "  Starting dialogue: $SCENARIO_NAME x $STRATEGY_NAME (max $MAX_TURNS turns)"

while [[ $TURN -lt $MAX_TURNS ]]; do
  TURN=$((TURN + 1))

  # --- Triage agent turn ---

  # Build the full prompt: system prompt + adapter + current issue state
  TRIAGE_PROMPT="$TRIAGE_SYSTEM_PROMPT

--- TRIAGE STRATEGY ---

$ADAPTER_PROMPT

--- CURRENT ISSUE STATE ---

$(echo "$ISSUE_JSON" | jq .)

--- INSTRUCTIONS ---

Examine the issue above (title, body, and all comments so far).
Apply the triage strategy described above.
Decide whether to ASK a clarifying question or RESOLVE the issue.
Respond with ONLY valid JSON as specified in the system prompt."

  # If this is the forced final turn, override instructions
  if [[ $TURN -eq $MAX_TURNS ]]; then
    TRIAGE_PROMPT="$TRIAGE_SYSTEM_PROMPT

--- TRIAGE STRATEGY ---

$ADAPTER_PROMPT

--- CURRENT ISSUE STATE ---

$(echo "$ISSUE_JSON" | jq .)

--- INSTRUCTIONS ---

You have reached the maximum number of dialogue turns. You MUST produce a
triage summary NOW with whatever information you have. Do NOT ask another
question. Respond with a JSON object with action 'resolve'."
  fi

  echo "  [Turn $TURN] Triage agent thinking..."
  TRIAGE_RAW="$(invoke_agent "$TRIAGE_PROMPT")"

  if $DRY_RUN; then
    # In dry-run mode, simulate a resolve after printing prompts for both agents
    # First show what the reporter prompt would look like
    REPORTER_PROMPT="$REPORTER_SYSTEM_PROMPT

--- YOUR GROUND TRUTH EXPERIENCE ---

$GROUND_TRUTH

--- CURRENT ISSUE STATE ---

$(echo "$ISSUE_JSON" | jq .)

--- INSTRUCTIONS ---

The latest comment is a question from the triage agent. Answer it based on
your ground truth experience. Respond with ONLY valid JSON."

    echo "  [Turn $TURN] Reporter agent prompt:"
    invoke_agent "$REPORTER_PROMPT"
    continue
  fi

  # Parse triage response
  TRIAGE_JSON="$(extract_json "$TRIAGE_RAW")" || {
    echo "  Warning: Could not parse triage agent response as JSON on turn $TURN" >&2
    echo "  Raw response saved to $TRIAL_DIR/error-turn-${TURN}-triage.txt" >&2
    echo "$TRIAGE_RAW" > "$TRIAL_DIR/error-turn-${TURN}-triage.txt"
    # Treat unparseable response as needing one more try
    continue
  }

  ACTION="$(echo "$TRIAGE_JSON" | jq -r '.action // "unknown"')"

  # --- Handle RESOLVE ---
  if [[ "$ACTION" == "resolve" ]]; then
    echo "  [Turn $TURN] Triage agent resolved the issue."

    # Append the resolution as a final comment
    TRIAGE_SUMMARY="$(echo "$TRIAGE_JSON" | jq -r '.triage_summary // empty')"
    ISSUE_JSON="$(echo "$ISSUE_JSON" | jq \
      --arg author "triage-agent" \
      --arg body "[TRIAGE RESOLVED] $(echo "$TRIAGE_JSON" | jq -c '.triage_summary')" \
      '.comments += [{author: $author, body: $body}]'
    )"

    # Write triage summary as markdown
    echo "$TRIAGE_JSON" | jq -r '.triage_summary' | jq -r '
      "# Triage Summary\n\n" +
      "**Title:** " + .title + "\n\n" +
      "## Problem\n" + .problem + "\n\n" +
      "## Root Cause Hypothesis\n" + .root_cause_hypothesis + "\n\n" +
      "## Reproduction Steps\n" + (.reproduction_steps | to_entries | map("  " + (.key+1|tostring) + ". " + .value) | join("\n")) + "\n\n" +
      "## Environment\n" + .environment + "\n\n" +
      "## Severity\n" + .severity + "\n\n" +
      "## Recommended Fix\n" + .recommended_fix + "\n\n" +
      "## Information Gaps\n" + (.information_gaps | map("- " + .) | join("\n"))
    ' > "$TRIAL_DIR/triage-summary.md" 2>/dev/null || {
      # If the jq formatting fails, just dump the raw JSON
      echo "# Triage Summary (raw JSON)" > "$TRIAL_DIR/triage-summary.md"
      echo "" >> "$TRIAL_DIR/triage-summary.md"
      echo '```json' >> "$TRIAL_DIR/triage-summary.md"
      echo "$TRIAGE_JSON" | jq '.triage_summary' >> "$TRIAL_DIR/triage-summary.md"
      echo '```' >> "$TRIAL_DIR/triage-summary.md"
    }

    break
  fi

  # --- Handle ASK ---
  if [[ "$ACTION" == "ask" ]]; then
    QUESTION="$(echo "$TRIAGE_JSON" | jq -r '.question')"
    echo "  [Turn $TURN] Triage agent asks: ${QUESTION:0:80}..."

    # Append question as comment
    ISSUE_JSON="$(echo "$ISSUE_JSON" | jq \
      --arg author "triage-agent" \
      --arg body "$QUESTION" \
      '.comments += [{author: $author, body: $body}]'
    )"

    # --- Reporter agent turn ---

    REPORTER_PROMPT="$REPORTER_SYSTEM_PROMPT

--- YOUR GROUND TRUTH EXPERIENCE ---

$GROUND_TRUTH

--- CURRENT ISSUE STATE ---

$(echo "$ISSUE_JSON" | jq .)

--- INSTRUCTIONS ---

The latest comment is a question from the triage agent. Read the question and
answer it based on your ground truth experience. Remember: you are a user, not
a developer. Share what you experienced, not technical analysis.

Respond with ONLY valid JSON: {\"answer\": \"your response\"}"

    echo "  [Turn $TURN] Reporter agent responding..."
    REPORTER_RAW="$(invoke_agent "$REPORTER_PROMPT")"

    REPORTER_JSON="$(extract_json "$REPORTER_RAW")" || {
      echo "  Warning: Could not parse reporter agent response on turn $TURN" >&2
      echo "$REPORTER_RAW" > "$TRIAL_DIR/error-turn-${TURN}-reporter.txt"
      # Use a generic fallback answer
      REPORTER_JSON='{"answer": "I am not sure, I just know something is wrong."}'
    }

    ANSWER="$(echo "$REPORTER_JSON" | jq -r '.answer // "I am not sure."')"
    echo "  [Turn $TURN] Reporter answers: ${ANSWER:0:80}..."

    # Append answer as comment
    ISSUE_JSON="$(echo "$ISSUE_JSON" | jq \
      --arg author "reporter" \
      --arg body "$ANSWER" \
      '.comments += [{author: $author, body: $body}]'
    )"
  else
    echo "  [Turn $TURN] Warning: unexpected action '$ACTION' from triage agent" >&2
    echo "$TRIAGE_RAW" > "$TRIAL_DIR/error-turn-${TURN}-unknown-action.txt"
  fi
done

# ---------------------------------------------------------------------------
# If we exhausted turns without resolving, force a final resolution
# ---------------------------------------------------------------------------

if [[ $TURN -ge $MAX_TURNS ]] && ! $DRY_RUN; then
  # Check if the last action was a resolve
  LAST_ACTION="$(echo "$ISSUE_JSON" | jq -r '.comments[-1].body // ""' | grep -c '^\[TRIAGE RESOLVED\]' || true)"
  if [[ "$LAST_ACTION" -eq 0 ]]; then
    echo "  [Max turns reached] Forcing final triage resolution..."

    FORCE_PROMPT="$TRIAGE_SYSTEM_PROMPT

--- TRIAGE STRATEGY ---

$ADAPTER_PROMPT

--- CURRENT ISSUE STATE ---

$(echo "$ISSUE_JSON" | jq .)

--- INSTRUCTIONS ---

You have reached the maximum number of dialogue turns. You MUST produce a
triage summary NOW with whatever information you have gathered. Do NOT ask
another question. Respond with a JSON object with action 'resolve'."

    FORCE_RAW="$(invoke_agent "$FORCE_PROMPT")"
    FORCE_JSON="$(extract_json "$FORCE_RAW")" || {
      echo "  Error: Could not parse forced resolution response" >&2
      echo "$FORCE_RAW" > "$TRIAL_DIR/error-forced-resolution.txt"
      # Create a minimal summary
      FORCE_JSON='{"action":"resolve","triage_summary":{"title":"(forced resolution - parse error)","problem":"Agent could not produce valid JSON","root_cause_hypothesis":"unknown","reproduction_steps":[],"environment":"unknown","severity":"medium","recommended_fix":"Manual triage required","information_gaps":["Everything"]}}'
    }

    ISSUE_JSON="$(echo "$ISSUE_JSON" | jq \
      --arg author "triage-agent" \
      --arg body "[TRIAGE RESOLVED] $(echo "$FORCE_JSON" | jq -c '.triage_summary // {}')" \
      '.comments += [{author: $author, body: $body}]'
    )"

    echo "$FORCE_JSON" | jq -r '.triage_summary' > "$TRIAL_DIR/triage-summary.md" 2>/dev/null || {
      echo '{"note": "forced resolution after max turns"}' > "$TRIAL_DIR/triage-summary.md"
    }
  fi
fi

# ---------------------------------------------------------------------------
# Save final conversation state
# ---------------------------------------------------------------------------

if ! $DRY_RUN; then
  echo "$ISSUE_JSON" | jq . > "$TRIAL_DIR/conversation.json"
  echo "  Saved conversation.json ($TURN turns, $(echo "$ISSUE_JSON" | jq '.comments | length') comments)"
fi
