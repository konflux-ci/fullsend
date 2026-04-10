#!/usr/bin/env bash
# Local harness runner — mimics the pre-script → agent → post-script flow
# that a GitHub Actions workflow (or future harness runner) would execute.
#
# Usage:
#   run-code-agent.sh --repo <owner/repo> --issue <number> [--dry-run] [--no-push]
#   run-code-agent.sh --issue <number> [--dry-run] [--no-push]   (from inside a repo)
#
# When --repo is given and we're not already inside that repo, the script
# clones it into a temp directory (mimicking what actions/checkout does in CI).
#
# Agent artifacts (agents/, skills/, scripts/) must either:
#   - Already exist in the repo (pre-committed or copied there), or
#   - Be provided via --artifacts <path-to-fullsend-repo> to copy them in
#
# Environment:
#   ANTHROPIC_API_KEY  required for claude invocation
#   FULLSEND_DIR       path to the fullsend repo (alternative to --artifacts)
set -euo pipefail

# ── colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

phase() { printf "\n${BOLD}${CYAN}━━━ %s ━━━${RESET}\n" "$1"; }
info()  { printf "${GREEN}✓${RESET} %s\n" "$1"; }
warn()  { printf "${YELLOW}!${RESET} %s\n" "$1"; }
fail()  { printf "${RED}✗${RESET} %s\n" "$1"; }
die()   { fail "$1"; exit 1; }

# ── parse args ──────────────────────────────────────────────────────────────
ISSUE_NUMBER=""
GH_REPO=""
ARTIFACTS_DIR="${FULLSEND_DIR:-}"
DRY_RUN=false
NO_PUSH=false
WORKDIR=""
CLONED=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)       GH_REPO="$2"; shift 2 ;;
    --issue)      ISSUE_NUMBER="$2"; shift 2 ;;
    --artifacts)  ARTIFACTS_DIR="$2"; shift 2 ;;
    --dry-run)    DRY_RUN=true; shift ;;
    --no-push)    NO_PUSH=true; shift ;;
    -h|--help)
      echo "Usage: run-code-agent.sh --repo <owner/repo> --issue <number> [options]"
      echo ""
      echo "Flags:"
      echo "  --repo <owner/repo>   Target repository (auto-detected if inside one)"
      echo "  --issue <n>           Issue number to implement (required)"
      echo "  --artifacts <path>    Path to fullsend repo to copy agent artifacts from"
      echo "  --dry-run             Run pre/post steps only, skip agent invocation"
      echo "  --no-push             Run everything but don't push or create PR"
      echo ""
      echo "Environment:"
      echo "  FULLSEND_DIR          Alternative to --artifacts"
      echo "  ANTHROPIC_API_KEY     Required for claude"
      exit 0 ;;
    *) die "Unknown arg: $1" ;;
  esac
done

[[ -n "${ISSUE_NUMBER}" ]] || die "Missing --issue <number>"

# ═══════════════════════════════════════════════════════════════════════════
#  PRE-SCRIPT PHASE
# ═══════════════════════════════════════════════════════════════════════════
phase "PRE-SCRIPT"

# ── step 1: clone or detect repo ───────────────────────────────────────────

# Auto-detect repo if not specified and we're inside one
if [[ -z "${GH_REPO}" ]]; then
  if git rev-parse --is-inside-work-tree &>/dev/null; then
    GH_REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" \
      || die "Cannot detect repo. Pass --repo <owner/repo>."
    info "Detected repo: ${GH_REPO}"
  else
    die "Not inside a git repo and --repo not specified"
  fi
fi

# Check if we're already inside the target repo
ALREADY_IN_REPO=false
if git rev-parse --is-inside-work-tree &>/dev/null; then
  CURRENT_REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")"
  if [[ "${CURRENT_REPO}" == "${GH_REPO}" ]]; then
    ALREADY_IN_REPO=true
    WORKDIR="$(git rev-parse --show-toplevel)"
  fi
fi

if [[ "${ALREADY_IN_REPO}" == true ]]; then
  info "Already inside ${GH_REPO} at ${WORKDIR}"
else
  # Clone the repo — this is what actions/checkout@v4 does in CI
  WORKDIR="$(mktemp -d)/$(basename "${GH_REPO}")"
  info "Cloning ${GH_REPO} → ${WORKDIR}..."
  gh repo clone "${GH_REPO}" "${WORKDIR}" -- --depth=50 \
    || die "Clone failed for ${GH_REPO}"
  CLONED=true
  info "Clone complete"
fi

cd "${WORKDIR}"
info "Working directory: $(pwd)"

# ── step 2: provision agent artifacts ──────────────────────────────────────

if [[ -f agents/code.md ]] && [[ -f skills/code-implementation/SKILL.md ]] && [[ -x scripts/scan-secrets ]]; then
  info "Agent artifacts already present in repo"
elif [[ -n "${ARTIFACTS_DIR}" ]]; then
  info "Provisioning agent artifacts from ${ARTIFACTS_DIR}..."

  [[ -f "${ARTIFACTS_DIR}/agents/code.md" ]] \
    || die "Cannot find agents/code.md in ${ARTIFACTS_DIR}"

  mkdir -p agents skills/code-implementation scripts .claude

  cp "${ARTIFACTS_DIR}/agents/code.md" agents/code.md
  cp "${ARTIFACTS_DIR}/skills/code-implementation/SKILL.md" skills/code-implementation/SKILL.md
  cp "${ARTIFACTS_DIR}/scripts/scan-secrets" scripts/scan-secrets
  chmod +x scripts/scan-secrets

  # Set up .claude symlinks
  ln -sf ../agents .claude/agents 2>/dev/null || true
  ln -sf ../skills .claude/skills 2>/dev/null || true

  info "Provisioned: agents/code.md, skill, scan-secrets, .claude symlinks"
else
  die "Agent artifacts not found in repo and --artifacts / FULLSEND_DIR not set"
fi

# Validate everything is in place
[[ -f agents/code.md ]]                    || die "Missing agents/code.md"
[[ -f skills/code-implementation/SKILL.md ]] || die "Missing skills/code-implementation/SKILL.md"
[[ -x scripts/scan-secrets ]]              || die "Missing or non-executable scripts/scan-secrets"
info "Agent artifacts validated"

# Fetch and validate the issue
info "Fetching issue #${ISSUE_NUMBER} from ${GH_REPO}..."
ISSUE_JSON="$(gh issue view "${ISSUE_NUMBER}" --repo "${GH_REPO}" \
  --json number,title,labels,state 2>/dev/null)" \
  || die "Cannot fetch issue #${ISSUE_NUMBER}"

ISSUE_TITLE="$(echo "${ISSUE_JSON}" | jq -r '.title')"
ISSUE_STATE="$(echo "${ISSUE_JSON}" | jq -r '.state')"
HAS_READY="$(echo "${ISSUE_JSON}" | jq '[.labels[].name] | any(. == "ready-to-code")')"

info "Issue: #${ISSUE_NUMBER} — ${ISSUE_TITLE}"
[[ "${ISSUE_STATE}" == "OPEN" ]] || die "Issue is ${ISSUE_STATE}, expected OPEN"
[[ "${HAS_READY}" == "true" ]]   || die "Issue missing 'ready-to-code' label"
info "Issue is open and triaged (ready-to-code)"

# Determine default branch
DEFAULT_BRANCH="$(git rev-parse --abbrev-ref origin/HEAD 2>/dev/null | cut -d/ -f2)" \
  || DEFAULT_BRANCH="main"
info "Default branch: ${DEFAULT_BRANCH}"

# Clean up any existing agent branch for this issue
BRANCH_NAME="agent/${ISSUE_NUMBER}-fix"
if git show-ref --verify --quiet "refs/heads/${BRANCH_NAME}" 2>/dev/null; then
  warn "Branch ${BRANCH_NAME} exists from a previous run — deleting"
  git branch -D "${BRANCH_NAME}" >/dev/null
fi

# Record the current HEAD so we can detect new commits later
git fetch origin "${DEFAULT_BRANCH}" --quiet
BASE_SHA="$(git rev-parse "origin/${DEFAULT_BRANCH}")"
info "Base SHA: ${BASE_SHA:0:12}"

# ── export env vars for the agent ───────────────────────────────────────────
export ISSUE_NUMBER
export BRANCH_NAME
export TARGET_BRANCH="${DEFAULT_BRANCH}"
export SCAN_SECRETS="scripts/scan-secrets"
export GH_REPO

info "Environment set: ISSUE_NUMBER=${ISSUE_NUMBER} BRANCH_NAME=${BRANCH_NAME} TARGET_BRANCH=${TARGET_BRANCH}"

# ═══════════════════════════════════════════════════════════════════════════
#  AGENT PHASE
# ═══════════════════════════════════════════════════════════════════════════
phase "AGENT"

AGENT_EXIT=0

if [[ "${DRY_RUN}" == true ]]; then
  warn "DRY RUN — skipping agent invocation"
  warn "Would run: claude --agent agents/code.md"
  echo ""
  echo "  ISSUE_NUMBER=${ISSUE_NUMBER}"
  echo "  BRANCH_NAME=${BRANCH_NAME}"
  echo "  TARGET_BRANCH=${TARGET_BRANCH}"
  echo "  SCAN_SECRETS=${SCAN_SECRETS}"
  echo ""
else
  info "Launching claude agent..."
  echo ""

  claude --dangerously-skip-permissions --agent code \
    "Implement the fix for https://github.com/${GH_REPO}/issues/${ISSUE_NUMBER}" \
    < /dev/null || AGENT_EXIT=$?
  echo ""
fi

# ═══════════════════════════════════════════════════════════════════════════
#  POST-SCRIPT PHASE
# ═══════════════════════════════════════════════════════════════════════════
phase "POST-SCRIPT"

# Check what branch we're on
CURRENT_BRANCH="$(git branch --show-current)"
info "Current branch: ${CURRENT_BRANCH}"

# Detect whether the agent produced a commit
AGENT_COMMITS=0
if git show-ref --verify --quiet "refs/heads/${BRANCH_NAME}" 2>/dev/null; then
  AGENT_COMMITS="$(git rev-list --count "${BASE_SHA}..${BRANCH_NAME}" 2>/dev/null || echo 0)"
fi

# Also check if we're on the expected branch with new commits
if [[ "${CURRENT_BRANCH}" == "${BRANCH_NAME}" ]] && [[ "${AGENT_COMMITS}" -eq 0 ]]; then
  AGENT_COMMITS="$(git rev-list --count "${BASE_SHA}..HEAD" 2>/dev/null || echo 0)"
fi

if [[ "${AGENT_EXIT}" -ne 0 ]] || [[ "${AGENT_COMMITS}" -eq 0 ]]; then
  # ── FAILURE PATH ──────────────────────────────────────────────────────
  fail "Agent exited with code ${AGENT_EXIT}, produced ${AGENT_COMMITS} commit(s)"
  echo ""

  if [[ "${DRY_RUN}" == true ]]; then
    warn "DRY RUN — would post failure comment and add label"
  else
    info "Posting failure comment on issue #${ISSUE_NUMBER}..."
    COMMENT_BODY="Implementation agent failed.

- Exit code: ${AGENT_EXIT}
- Commits produced: ${AGENT_COMMITS}
- Runner: local ($(hostname))
- Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)

Review the agent transcript for details."

    gh issue comment "${ISSUE_NUMBER}" --repo "${GH_REPO}" \
      --body "${COMMENT_BODY}" 2>/dev/null \
      && info "Failure comment posted" \
      || warn "Could not post comment (permissions?)"

    gh issue edit "${ISSUE_NUMBER}" --repo "${GH_REPO}" \
      --add-label "requires-manual-review" 2>/dev/null \
      && info "Label 'requires-manual-review' applied" \
      || warn "Could not apply label (permissions?)"
  fi

  exit 1
fi

# ── SUCCESS PATH ──────────────────────────────────────────────────────────
info "Agent produced ${AGENT_COMMITS} commit(s) on ${BRANCH_NAME}"

# Post-script secret scan — the authoritative gate
info "Running post-script secret scan (authoritative gate)..."
git checkout "${BRANCH_NAME}" --quiet 2>/dev/null || true

CHANGED_FILES="$(git diff --name-only "${BASE_SHA}..HEAD")"
if [[ -z "${CHANGED_FILES}" ]]; then
  die "No changed files detected despite ${AGENT_COMMITS} commit(s)"
fi

info "Files changed by agent:"
echo "${CHANGED_FILES}" | while read -r f; do echo "  ${f}"; done

# Stage the agent's changes for scanning
git stash --quiet 2>/dev/null || true
SCAN_EXIT=0
# Use git diff to get files, then scan them
for f in ${CHANGED_FILES}; do
  if [[ -f "${f}" ]]; then
    scripts/scan-secrets "${f}" || SCAN_EXIT=1
  fi
done

if [[ "${SCAN_EXIT}" -ne 0 ]]; then
  fail "POST-SCRIPT SECRET SCAN FAILED — refusing to push"
  gh issue comment "${ISSUE_NUMBER}" --repo "${GH_REPO}" \
    --body "Post-script secret scan failed. Agent commit contains potential secrets. Requires manual review." \
    2>/dev/null || true
  gh issue edit "${ISSUE_NUMBER}" --repo "${GH_REPO}" \
    --add-label "requires-manual-review" 2>/dev/null || true
  exit 1
fi
info "Post-script secret scan passed"

# Show the commit(s)
echo ""
info "Commit(s) to push:"
git log --oneline "${BASE_SHA}..HEAD" | while read -r line; do echo "  ${line}"; done
echo ""

# Push and create PR
if [[ "${NO_PUSH}" == true ]] || [[ "${DRY_RUN}" == true ]]; then
  warn "SKIP PUSH — --no-push or --dry-run set"
  warn "Would run: git push -u origin ${BRANCH_NAME}"
  warn "Would run: gh pr create ..."
else
  info "Pushing branch..."
  git push -u origin "${BRANCH_NAME}" || die "Push failed"
  info "Branch pushed"

  COMMIT_MSG="$(git log -1 --format='%s')"
  PR_BODY="$(git log -1 --format='%b')"

  info "Creating PR..."
  PR_URL="$(gh pr create \
    --repo "${GH_REPO}" \
    --head "${BRANCH_NAME}" \
    --base "${DEFAULT_BRANCH}" \
    --title "${COMMIT_MSG}" \
    --body "${PR_BODY}

---
*Created by code agent run on $(date -u +%Y-%m-%dT%H:%M:%SZ)*" 2>&1)" \
    && info "PR created: ${PR_URL}" \
    || warn "PR creation failed: ${PR_URL}"
fi

# ── summary ─────────────────────────────────────────────────────────────────
phase "DONE"
info "Issue:    #${ISSUE_NUMBER} — ${ISSUE_TITLE}"
info "Branch:   ${BRANCH_NAME}"
info "Commits:  ${AGENT_COMMITS}"
info "Secrets:  passed (agent + post-script)"
if [[ "${NO_PUSH}" == true ]] || [[ "${DRY_RUN}" == true ]]; then
  warn "Push/PR:  skipped"
else
  info "Push/PR:  complete"
fi
if [[ "${CLONED}" == true ]]; then
  info "Workdir:  ${WORKDIR} (cloned — remove when done)"
fi
