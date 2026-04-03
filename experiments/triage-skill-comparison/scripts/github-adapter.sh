#!/usr/bin/env bash
# =============================================================================
# github-adapter.sh — Reference: converting file-based simulation to live GitHub
# =============================================================================
#
# THIS SCRIPT IS NOT MEANT TO BE RUN. It is a documented sketch showing how
# to adapt the experiment from local JSON files to live GitHub API calls.
#
# The experiment's core logic (prompts, strategies, judging) is identical.
# Only the I/O layer changes: instead of reading/writing a local JSON file,
# we read/write GitHub issues and comments via the `gh` CLI.
#
# =============================================================================

# Prevent accidental execution
echo "This script is a reference document, not meant to be executed."
echo "Read the source for the GitHub API adaptation patterns."
exit 0

# ============================================================================
# PATTERN 1: Creating an issue
# ============================================================================

create_issue() {
  local owner="$1" repo="$2" title="$3" body="$4"

  # Create the issue and capture the issue number from the response
  local issue_number
  issue_number=$(gh api "repos/$owner/$repo/issues" \
    --method POST \
    --field title="$title" \
    --field body="$body" \
    --jq '.number')

  echo "$issue_number"
}

# Usage:
# ISSUE_NUM=$(create_issue "myorg" "taskflow" "app crashes when I save" "The app keeps crashing...")

# ============================================================================
# PATTERN 2: Reading an issue with all comments
# ============================================================================

read_issue_state() {
  local owner="$1" repo="$2" issue_number="$3"

  # Fetch the issue metadata
  local issue_json
  issue_json=$(gh api "repos/$owner/$repo/issues/$issue_number")

  local title body
  title=$(echo "$issue_json" | jq -r '.title')
  body=$(echo "$issue_json" | jq -r '.body')

  # Fetch all comments (paginated — gh handles pagination with --paginate)
  local comments_json
  comments_json=$(gh api "repos/$owner/$repo/issues/$issue_number/comments" \
    --paginate \
    --jq '[.[] | {author: .user.login, body: .body, created_at: .created_at}]')

  # Combine into the same format used by the file-based simulation
  jq -n \
    --arg title "$title" \
    --arg body "$body" \
    --argjson comments "$comments_json" \
    '{title: $title, body: $body, comments: $comments}'
}

# Usage:
# ISSUE_STATE=$(read_issue_state "myorg" "taskflow" 42)
# This produces the same JSON structure as the local simulation's issue.json

# ============================================================================
# PATTERN 3: Posting a comment
# ============================================================================

post_comment() {
  local owner="$1" repo="$2" issue_number="$3" body="$4"

  gh api "repos/$owner/$repo/issues/$issue_number/comments" \
    --method POST \
    --field body="$body" \
    --jq '.id'
}

# Usage:
# COMMENT_ID=$(post_comment "myorg" "taskflow" 42 "Can you tell me what browser you're using?")

# ============================================================================
# PATTERN 4: Reading the latest comment
# ============================================================================

get_latest_comment() {
  local owner="$1" repo="$2" issue_number="$3"

  gh api "repos/$owner/$repo/issues/$issue_number/comments" \
    --jq '.[-1] | {author: .user.login, body: .body, created_at: .created_at}'
}

# ============================================================================
# PATTERN 5: Polling for new comments
# ============================================================================
#
# After the triage agent posts a question, the orchestrator needs to wait for
# the reporter to respond. In the simulation, this is instant (we invoke the
# reporter agent immediately). In a live GitHub setup, there are two options:
#
# Option A: Polling (simple, works anywhere)
# Option B: Webhooks + GitHub Actions (event-driven, preferred for production)

# --- Option A: Polling ---

poll_for_response() {
  local owner="$1" repo="$2" issue_number="$3"
  local last_known_count="$4"
  local poll_interval=30  # seconds
  local max_wait=3600     # 1 hour

  local elapsed=0
  while [[ $elapsed -lt $max_wait ]]; do
    local current_count
    current_count=$(gh api "repos/$owner/$repo/issues/$issue_number/comments" \
      --jq '. | length')

    if [[ "$current_count" -gt "$last_known_count" ]]; then
      # New comment(s) arrived
      get_latest_comment "$owner" "$repo" "$issue_number"
      return 0
    fi

    sleep "$poll_interval"
    elapsed=$((elapsed + poll_interval))
  done

  echo "Timeout waiting for response" >&2
  return 1
}

# --- Option B: GitHub Actions (preferred) ---
#
# Instead of polling, use a GitHub Actions workflow that triggers on issue
# comments. This is more efficient and more aligned with the "short-lived
# agent" model described in the experiment design.
#
# .github/workflows/triage-respond.yml:
#
# name: Triage Agent Response
# on:
#   issue_comment:
#     types: [created]
#
# jobs:
#   triage:
#     # Only run when:
#     #   1. The issue has the "triage-experiment" label
#     #   2. The comment was NOT from the triage bot (avoid infinite loops)
#     if: |
#       contains(github.event.issue.labels.*.name, 'triage-experiment') &&
#       github.event.comment.user.login != 'triage-bot[bot]'
#     runs-on: ubuntu-latest
#     steps:
#       - uses: actions/checkout@v4
#
#       - name: Install agent CLI
#         run: npm install -g @anthropic-ai/claude-code
#
#       - name: Read issue state
#         id: read-issue
#         run: |
#           ISSUE_STATE=$(gh api repos/${{ github.repository }}/issues/${{ github.event.issue.number }} \
#             --jq '{title: .title, body: .body}')
#           COMMENTS=$(gh api repos/${{ github.repository }}/issues/${{ github.event.issue.number }}/comments \
#             --paginate --jq '[.[] | {author: .user.login, body: .body}]')
#           FULL_STATE=$(echo "$ISSUE_STATE" | jq --argjson c "$COMMENTS" '. + {comments: $c}')
#           echo "issue_state<<EOF" >> $GITHUB_OUTPUT
#           echo "$FULL_STATE" >> $GITHUB_OUTPUT
#           echo "EOF" >> $GITHUB_OUTPUT
#         env:
#           GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
#
#       - name: Determine triage strategy
#         id: strategy
#         run: |
#           # Could be set per-issue via a label, or globally in repo config
#           STRATEGY=$(gh api repos/${{ github.repository }}/issues/${{ github.event.issue.number }} \
#             --jq '.labels[] | select(.name | startswith("strategy:")) | .name | sub("strategy:"; "")')
#           echo "strategy=${STRATEGY:-structured-triage}" >> $GITHUB_OUTPUT
#         env:
#           GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
#
#       - name: Run triage agent
#         id: triage
#         run: |
#           ADAPTER=$(cat adapters/${{ steps.strategy.outputs.strategy }}.md)
#           PROMPT="<triage system prompt here>
#
#           --- STRATEGY ---
#           $ADAPTER
#
#           --- ISSUE STATE ---
#           ${{ steps.read-issue.outputs.issue_state }}
#
#           Respond with JSON: {action: ask|resolve, ...}"
#
#           RESULT=$(claude -p "$PROMPT" --output-format text)
#           echo "result<<EOF" >> $GITHUB_OUTPUT
#           echo "$RESULT" >> $GITHUB_OUTPUT
#           echo "EOF" >> $GITHUB_OUTPUT
#         env:
#           ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
#
#       - name: Post response
#         run: |
#           ACTION=$(echo '${{ steps.triage.outputs.result }}' | jq -r '.action')
#           if [ "$ACTION" = "ask" ]; then
#             QUESTION=$(echo '${{ steps.triage.outputs.result }}' | jq -r '.question')
#             gh api repos/${{ github.repository }}/issues/${{ github.event.issue.number }}/comments \
#               --method POST --field body="$QUESTION"
#           elif [ "$ACTION" = "resolve" ]; then
#             SUMMARY=$(echo '${{ steps.triage.outputs.result }}' | jq -r '.triage_summary | tojson')
#             gh api repos/${{ github.repository }}/issues/${{ github.event.issue.number }}/comments \
#               --method POST --field body="## Triage Complete\n\n\`\`\`json\n$SUMMARY\n\`\`\`"
#             # Optionally add a label
#             gh api repos/${{ github.repository }}/issues/${{ github.event.issue.number }}/labels \
#               --method POST --input - <<< '["triaged"]'
#           fi
#         env:
#           GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

# ============================================================================
# PATTERN 6: Full live orchestration (replacing run-single-trial.sh)
# ============================================================================
#
# In a live GitHub setup, the orchestration is EVENT-DRIVEN, not loop-driven:
#
# 1. A new issue is created (or labeled "needs-triage")
#    -> GitHub Actions triggers the triage agent
#    -> Agent reads issue, posts a question comment, and EXITS
#
# 2. The reporter responds with a comment
#    -> GitHub Actions triggers the triage agent again
#    -> Agent reads the FULL issue (including all comments), decides:
#       - Ask another question -> post comment, exit
#       - Resolve -> post triage summary, add "triaged" label, exit
#
# 3. This repeats until resolved or max turns reached.
#
# The key differences from the file-based simulation:
#
# | Aspect          | File-based simulation         | Live GitHub                    |
# |-----------------|-------------------------------|--------------------------------|
# | Issue state     | Local JSON file               | GitHub API                     |
# | Agent lifecycle | Invoked by bash loop          | Invoked by GitHub Actions      |
# | Turn tracking   | Loop counter in bash          | Count comments by bot user     |
# | Reporter        | AI agent invoked immediately  | Real human (or separate bot)   |
# | Waiting         | No waiting (synchronous)      | Event-driven (webhook)         |
# | Max turns       | Enforced by loop              | Count bot comments, enforce    |
#
# The PROMPTS and STRATEGIES are identical. Only the I/O plumbing changes.

# ============================================================================
# PATTERN 7: Turn counting in live mode
# ============================================================================

count_bot_turns() {
  local owner="$1" repo="$2" issue_number="$3" bot_login="$4"

  gh api "repos/$owner/$repo/issues/$issue_number/comments" \
    --paginate \
    --jq "[.[] | select(.user.login == \"$bot_login\")] | length"
}

# Usage in the Actions workflow:
# BOT_TURNS=$(count_bot_turns "myorg" "taskflow" 42 "triage-bot[bot]")
# if [ "$BOT_TURNS" -ge "$MAX_TURNS" ]; then
#   # Force resolution
# fi
