#!/usr/bin/env bash
# =============================================================================
# run-experiment.sh — Main orchestrator for the triage skill comparison
# =============================================================================
#
# Runs all (or selected) scenario x strategy combinations, then judges
# each result and generates a summary comparison table.
#
# Usage:
#   ./scripts/run-experiment.sh                               # all combos
#   ./scripts/run-experiment.sh --scenario crash-on-save      # one scenario
#   ./scripts/run-experiment.sh --strategy socratic-refinement # one strategy
#   ./scripts/run-experiment.sh --dry-run                     # prompts only
#   ./scripts/run-experiment.sh --max-turns 4                 # limit turns
#   AGENT_CLI=opencode ./scripts/run-experiment.sh            # use opencode
#
# Flags:
#   --scenario NAME    Run only this scenario (default: all)
#   --strategy NAME    Run only this strategy (default: all)
#   --dry-run          Print prompts without invoking agents
#   --max-turns N      Maximum dialogue turns per trial (default: 8)
#
# Environment:
#   AGENT_CLI          Agent CLI to use: "claude" (default) or "opencode"
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCENARIOS=(crash-on-save slow-search auth-redirect-loop)
STRATEGIES=(superpowers-brainstorming structured-triage socratic-refinement)

AGENT_CLI="${AGENT_CLI:-claude}"
MAX_TURNS=8
DRY_RUN=false
FILTER_SCENARIO=""
FILTER_STRATEGY=""

# Resolve the experiment root relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPERIMENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------------------------------------------------------------------------
# Parse flags
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario)   FILTER_SCENARIO="$2"; shift 2 ;;
    --strategy)   FILTER_STRATEGY="$2"; shift 2 ;;
    --dry-run)    DRY_RUN=true; shift ;;
    --max-turns)  MAX_TURNS="$2"; shift 2 ;;
    *)
      echo "Unknown flag: $1" >&2
      echo "Usage: $0 [--scenario NAME] [--strategy NAME] [--dry-run] [--max-turns N]" >&2
      exit 1
      ;;
  esac
done

# Apply filters: if a specific scenario/strategy was requested, narrow the
# arrays down to just that entry (exit with error if the name is invalid).
if [[ -n "$FILTER_SCENARIO" ]]; then
  found=false
  for s in "${SCENARIOS[@]}"; do [[ "$s" == "$FILTER_SCENARIO" ]] && found=true; done
  if ! $found; then
    echo "Error: unknown scenario '$FILTER_SCENARIO'" >&2
    echo "Valid scenarios: ${SCENARIOS[*]}" >&2
    exit 1
  fi
  SCENARIOS=("$FILTER_SCENARIO")
fi

if [[ -n "$FILTER_STRATEGY" ]]; then
  found=false
  for s in "${STRATEGIES[@]}"; do [[ "$s" == "$FILTER_STRATEGY" ]] && found=true; done
  if ! $found; then
    echo "Error: unknown strategy '$FILTER_STRATEGY'" >&2
    echo "Valid strategies: ${STRATEGIES[*]}" >&2
    exit 1
  fi
  STRATEGIES=("$FILTER_STRATEGY")
fi

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

check_prereqs() {
  local missing=()

  if ! command -v "$AGENT_CLI" &>/dev/null; then
    missing+=("$AGENT_CLI (agent CLI)")
  fi
  if ! command -v jq &>/dev/null; then
    missing+=("jq")
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Error: missing prerequisites:" >&2
    for m in "${missing[@]}"; do echo "  - $m" >&2; done
    exit 1
  fi
}

if ! $DRY_RUN; then
  check_prereqs
fi

# ---------------------------------------------------------------------------
# Create timestamped results directory
# ---------------------------------------------------------------------------

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
RESULTS_DIR="$EXPERIMENT_DIR/results/$TIMESTAMP"
mkdir -p "$RESULTS_DIR"

echo "============================================================"
echo " Triage Skill Comparison Experiment"
echo "============================================================"
echo " Agent CLI:    $AGENT_CLI"
echo " Max turns:    $MAX_TURNS"
echo " Dry run:      $DRY_RUN"
echo " Scenarios:    ${SCENARIOS[*]}"
echo " Strategies:   ${STRATEGIES[*]}"
echo " Results dir:  $RESULTS_DIR"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# Run trials
# ---------------------------------------------------------------------------

TOTAL=$(( ${#SCENARIOS[@]} * ${#STRATEGIES[@]} ))
CURRENT=0

for scenario in "${SCENARIOS[@]}"; do
  for strategy in "${STRATEGIES[@]}"; do
    CURRENT=$((CURRENT + 1))
    TRIAL_DIR="$RESULTS_DIR/$scenario/$strategy"
    mkdir -p "$TRIAL_DIR"

    echo "[$CURRENT/$TOTAL] Running: $scenario x $strategy"
    echo "  => $TRIAL_DIR"

    DRY_RUN_FLAG=""
    if $DRY_RUN; then
      DRY_RUN_FLAG="--dry-run"
    fi

    # run-single-trial.sh expects positional args:
    #   scenario_name strategy_name results_dir max_turns agent_cli [--dry-run]
    "$SCRIPT_DIR/run-single-trial.sh" \
      "$scenario" \
      "$strategy" \
      "$TRIAL_DIR" \
      "$MAX_TURNS" \
      "$AGENT_CLI" \
      $DRY_RUN_FLAG

    echo "  => Trial complete."
    echo ""
  done
done

# ---------------------------------------------------------------------------
# Judge each trial
# ---------------------------------------------------------------------------

if $DRY_RUN; then
  echo "[dry-run] Skipping judge and summary phases."
  exit 0
fi

echo "============================================================"
echo " Judging trials"
echo "============================================================"
echo ""

CURRENT=0
for scenario in "${SCENARIOS[@]}"; do
  for strategy in "${STRATEGIES[@]}"; do
    CURRENT=$((CURRENT + 1))
    TRIAL_DIR="$RESULTS_DIR/$scenario/$strategy"

    echo "[$CURRENT/$TOTAL] Judging: $scenario x $strategy"

    "$SCRIPT_DIR/judge.sh" "$TRIAL_DIR" "$AGENT_CLI"

    echo "  => Judgement complete."
    echo ""
  done
done

# ---------------------------------------------------------------------------
# Generate summary
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generating summary"
echo "============================================================"
echo ""

"$SCRIPT_DIR/summarize.sh" "$RESULTS_DIR"

echo ""
echo "============================================================"
echo " Experiment complete!"
echo " Results:  $RESULTS_DIR"
echo " Summary:  $RESULTS_DIR/summary.md"
echo "============================================================"
