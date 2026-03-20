#!/bin/bash
# run-tests.sh - OpenShell sandboxing experiment test harness.
#
# Runs three tests:
#   1. Baseline: opencode makes a network call without any sandbox (should pass)
#   2. Positive: opencode inside OpenShell with egress allowed (should pass)
#   3. Negative: opencode inside OpenShell with egress denied (should fail)
#
# Prerequisites:
#   - openshell CLI installed (curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh)
#   - Docker running (openshell gateway start)
#   - opencode installed
#
# The prompt used to induce a network-based tool call:
#   "Use bash to run: curl -sf --max-time 5 https://httpbin.org/get"
#
# This is a simple, deterministic prompt that causes the agent to invoke
# the bash tool with a curl command. We chose curl over webfetch because
# bash tool calls spawn a subprocess that OpenShell can intercept, while
# webfetch runs in-process and is invisible to the sandbox.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_FILE="${SCRIPT_DIR}/test-results.log"
SANDBOX_NAME="fullsend-egress-test"
NETWORK_PROMPT="Use bash to run this exact command and show the output: curl -sf --max-time 5 https://httpbin.org/get"

> "${RESULTS_FILE}"

log() {
    echo "$*" | tee -a "${RESULTS_FILE}"
}

check_prereqs() {
    local missing=0
    for cmd in openshell opencode curl; do
        if ! command -v "$cmd" &>/dev/null; then
            log "ERROR: ${cmd} is not installed"
            missing=1
        fi
    done
    if ! openshell status 2>&1 | grep -q "Running"; then
        log "ERROR: OpenShell gateway is not running."
        log "  Start it with: openshell gateway start"
        log "  (Requires Docker)"
        missing=1
    fi
    if [[ $missing -ne 0 ]]; then
        log ""
        log "Prerequisites not met. See README.md for setup instructions."
        exit 1
    fi
}

cleanup() {
    log "Cleaning up sandbox: ${SANDBOX_NAME}"
    openshell sandbox delete "${SANDBOX_NAME}" 2>/dev/null || true
}

# ---- Test 1: Baseline (no sandbox) ----
test_baseline() {
    log ""
    log "================================================================"
    log "TEST 1: Baseline - opencode network call without sandbox"
    log "================================================================"

    local output exit_code=0
    output=$(opencode run \
        --dir /workspaces/fullsend \
        --title "openshell-baseline" \
        "${NETWORK_PROMPT}" 2>&1) || exit_code=$?

    if echo "${output}" | grep -qi "httpbin\|origin"; then
        log "RESULT: PASS - Network call succeeded without sandbox"
    else
        log "RESULT: FAIL - Network call failed even without sandbox"
        log "Output: ${output}"
    fi
}

# ---- Test 2: Positive - OpenShell with egress allowed ----
test_allow_egress() {
    log ""
    log "================================================================"
    log "TEST 2: OpenShell sandbox with egress ALLOWED"
    log "================================================================"

    # Create sandbox with allow-egress policy
    openshell sandbox create \
        --name "${SANDBOX_NAME}" \
        --keep \
        --no-auto-providers \
        --policy "${SCRIPT_DIR}/policy-allow-egress.yaml" \
        --no-tty \
        -- echo "sandbox ready" 2>&1 | tee -a "${RESULTS_FILE}"

    # Get SSH config for the sandbox
    local ssh_config
    ssh_config=$(mktemp)
    openshell sandbox ssh-config "${SANDBOX_NAME}" > "${ssh_config}"
    local ssh_host
    ssh_host=$(awk '/^Host / { print $2; exit }' "${ssh_config}")

    # Run curl inside the sandbox
    local output exit_code=0
    output=$(ssh -F "${ssh_config}" "${ssh_host}" \
        curl -sf --max-time 10 https://httpbin.org/get 2>&1) || exit_code=$?

    rm -f "${ssh_config}"

    if [[ ${exit_code} -eq 0 ]] && echo "${output}" | grep -qi "origin"; then
        log "RESULT: PASS - curl succeeded inside allow-egress sandbox"
    else
        log "RESULT: FAIL - curl failed inside allow-egress sandbox (exit=${exit_code})"
    fi

    # Clean up before next test
    openshell sandbox delete "${SANDBOX_NAME}" 2>/dev/null || true
}

# ---- Test 3: Negative - OpenShell with egress denied ----
test_deny_egress() {
    log ""
    log "================================================================"
    log "TEST 3: OpenShell sandbox with egress DENIED"
    log "================================================================"

    # Create sandbox with deny-egress policy (no network_policies)
    openshell sandbox create \
        --name "${SANDBOX_NAME}" \
        --keep \
        --no-auto-providers \
        --policy "${SCRIPT_DIR}/policy-deny-egress.yaml" \
        --no-tty \
        -- echo "sandbox ready" 2>&1 | tee -a "${RESULTS_FILE}"

    # Get SSH config
    local ssh_config
    ssh_config=$(mktemp)
    openshell sandbox ssh-config "${SANDBOX_NAME}" > "${ssh_config}"
    local ssh_host
    ssh_host=$(awk '/^Host / { print $2; exit }' "${ssh_config}")

    # Run curl inside the sandbox -- this should FAIL
    local output exit_code=0
    output=$(ssh -F "${ssh_config}" "${ssh_host}" \
        curl -sf --max-time 10 https://httpbin.org/get 2>&1) || exit_code=$?

    rm -f "${ssh_config}"

    if [[ ${exit_code} -ne 0 ]]; then
        log "RESULT: PASS - curl correctly FAILED inside deny-egress sandbox (exit=${exit_code})"
        log "  Error: ${output}"
    else
        log "RESULT: FAIL - curl unexpectedly succeeded inside deny-egress sandbox!"
    fi

    cleanup
}

# ---- Main ----
log "=== OpenShell Sandboxing Experiment ==="
log "Date: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
log "openshell version: $(openshell --version 2>&1)"
log ""

check_prereqs
test_baseline
test_allow_egress
test_deny_egress

log ""
log "=== All tests complete ==="
log "Results saved to: ${RESULTS_FILE}"
