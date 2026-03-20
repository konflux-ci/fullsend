# Experiment: NVIDIA OpenShell for Agent Sandboxing

**Date:** 2026-03-20
**Status:** Partially complete (blocked on Docker availability)
**Author:** AI agent (Claude opus-4-6) with human direction

## Goal

Evaluate [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell) as a sandboxing mechanism for AI coding agents in the konflux-ci environment. Specifically:

1. Can OpenShell control network egress for agent tool calls?
2. Does a positive test (egress allowed) work?
3. Does a negative test (egress denied) work?
4. What surprising findings emerge?

## What is OpenShell?

OpenShell ([github.com/NVIDIA/OpenShell](https://github.com/NVIDIA/OpenShell)) is NVIDIA's open-source sandbox runtime for autonomous AI agents. It provides:

- **Sandboxed execution environments** using K3s (lightweight Kubernetes) inside Docker
- **Declarative YAML policies** that control filesystem access, network egress, and process permissions
- **Default-deny networking** -- all outbound traffic is blocked unless explicitly permitted by policy
- **L7 (HTTP method-level) enforcement** -- policies can allow GET but block POST to the same endpoint
- **Hot-reloadable policies** -- network rules can be updated on a running sandbox without restart
- **Per-binary scoping** -- network policies can be restricted to specific binaries (e.g., allow only `/usr/bin/curl` to reach an endpoint)
- **Audit logging** -- every allowed and denied connection is logged with destination, binary, and reason

OpenShell is a Rust project (2.7k GitHub stars, Apache-2.0 licensed) that explicitly supports OpenCode as a sandbox target: `openshell sandbox create -- opencode`.

## The Prompt

To induce a network-based tool call from opencode, we use:

```
Use bash to run this exact command and show the output: curl -sf --max-time 5 https://httpbin.org/get
```

This prompt is chosen because:
- It forces the agent to use the **bash tool** (which spawns a subprocess)
- Subprocess tools are what OpenShell intercepts and enforces policy against
- It targets a well-known test endpoint (httpbin.org) that returns structured JSON
- The `-sf` flags make the output clean on success and exit non-zero on failure

We deliberately avoid asking the agent to use `webfetch` because that tool runs in-process within the opencode Node.js runtime, making it invisible to any OS-level sandbox. This is discussed further in the findings section.

## Test Design

### Test 1: Baseline (no sandbox)

Run `opencode run` with the network prompt directly. Confirms network egress works in the devaipod environment.

**Outcome:** PASS -- curl returns httpbin.org JSON response.

### Test 2: OpenShell with egress allowed (`policy-allow-egress.yaml`)

Create an OpenShell sandbox with a policy that permits all HTTPS egress. Run the same prompt inside the sandbox.

**Expected outcome:** PASS -- curl should succeed because the policy allows it.

**Actual outcome:** BLOCKED -- cannot run. Docker is not available in the devaipod container. See "Blockers" below.

### Test 3: OpenShell with egress denied (`policy-deny-egress.yaml`)

Create an OpenShell sandbox with no `network_policies` section (default-deny). Run the same prompt inside the sandbox.

**Expected outcome:** FAIL -- curl should get HTTP 403 from the OpenShell proxy because no policy authorizes the connection.

**Actual outcome:** BLOCKED -- same Docker dependency.

## What We Could Verify

Even without Docker, we verified:

1. **OpenShell CLI installs cleanly** in the devaipod environment:
   ```
   $ curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh
   openshell: installed openshell 0.0.12 to /home/devenv/.local/bin/openshell
   ```

2. **CLI is a self-contained static binary** (Rust, musl-linked, ~30MB). No runtime dependencies beyond Docker for the gateway.

3. **Gateway requires Docker** -- `openshell gateway start` fails with:
   ```
   Error: Failed to create Docker client.
     Socket not found: /var/run/docker.sock
   ```

4. **Policy YAML structure is straightforward** -- we created both allow and deny policies (see `policy-allow-egress.yaml` and `policy-deny-egress.yaml`).

5. **OpenShell knows about OpenCode** -- it's a first-class sandbox target (`openshell sandbox create -- opencode`), with provider auto-detection for `OPENAI_API_KEY` and `OPENROUTER_API_KEY`.

## Blockers

### Docker is required but unavailable

OpenShell runs its gateway as a K3s cluster inside a Docker container. The devaipod environment has Podman 5.7.0 but:
- No Docker socket (`/var/run/docker.sock` does not exist)
- No `docker` command
- Podman cannot create user namespaces in this container (`newuidmap: Operation not permitted`)

This is a hard blocker. OpenShell cannot function without Docker.

### Possible workarounds (untested)

1. **Docker-in-Docker (DinD):** Mount Docker socket from host into devaipod. Requires devaipod infrastructure changes.
2. **Remote gateway:** `openshell gateway start --remote user@host` deploys to a remote machine over SSH. Could point to a VM with Docker.
3. **Podman compatibility:** OpenShell checks for `/var/run/docker.sock` specifically. A `podman system service` socket aliased to the Docker path *might* work, but Podman's K3s compatibility is untested.

## Surprising Findings

### 1. OpenShell is architecturally different from namespace-based sandboxing

Initial instinct was to use bubblewrap (`bwrap`) or Linux user namespaces. OpenShell is fundamentally different:

| Property | bwrap / unshare | OpenShell |
|----------|----------------|-----------|
| Network control | Binary: namespace has network or doesn't | Granular: per-host, per-port, per-HTTP-method, per-binary |
| Policy model | Compile-time (set at sandbox creation) | Runtime (hot-reload YAML policies) |
| Enforcement layer | Kernel (network namespaces) | Proxy (L4/L7 interception) |
| Audit trail | None built-in | Every connection logged |
| Agent awareness | None | First-class agent support |
| Dependency | Linux kernel features | Docker + K3s |

The L7 enforcement is the key differentiator. OpenShell can allow an agent to *read* from GitHub but not *write* -- something namespace-based isolation fundamentally cannot do.

### 2. Default-deny is the right default

OpenShell starts with **all egress denied**. You explicitly allow what the agent needs. This is the opposite of most development environments (where everything is open and you selectively restrict). For autonomous agents, default-deny is the correct security posture.

### 3. The in-process tool gap still applies

OpenShell intercepts network connections at the OS level (via the sandbox proxy). This means:
- **bash tool calls** (subprocess → curl, wget, etc.): sandboxed and policy-enforced
- **webfetch tool calls** (in-process HTTP from Node.js): likely also intercepted, since all traffic goes through the sandbox proxy
- **MCP server calls**: intercepted if the MCP server runs inside the sandbox

This is better than our initial bwrap experiment found, because OpenShell's proxy intercepts at the network level (not the process namespace level), so in-process HTTP requests from Node.js should *also* be caught. However, this needs empirical verification.

### 4. OpenShell treats agent infrastructure as a first-class concern

The project explicitly supports OpenCode, Claude Code, Codex, and Copilot. It handles credential injection (providers), workspace mounting, and agent-specific policy presets. This is not a generic container runtime bolted onto agents -- it's purpose-built.

### 5. The heavyweight dependency chain is a real concern

OpenShell requires Docker → K3s → Helm charts → gateway container → sandbox container. For a development sandbox, this is a lot of infrastructure. The tradeoff is clear:
- **Simple sandboxing** (bwrap): lightweight, kernel-only, but coarse-grained
- **OpenShell**: heavyweight, but fine-grained L7 policy enforcement with audit trail

For konflux-ci's use case (autonomous agents modifying production infrastructure), the fine-grained controls likely justify the complexity. But the Docker dependency is a deployment constraint.

### 6. OpenShell already exists inside devaipod's base image catalog

The fact that `openshell sandbox create -- opencode` is a supported command suggests that integrating OpenShell into the devaipod infrastructure is a natural fit. The main work is making Docker available to the devaipod container.

## Recommendations for Konflux-CI

### Short-term

- **Add Docker socket access to devaipod** so OpenShell experiments can run end-to-end
- **Evaluate OpenShell's Podman compatibility** -- if Podman's Docker socket emulation works, this avoids adding Docker to the stack

### Medium-term

- **Create a konflux-ci OpenShell policy template** that allows only the LLM API endpoints needed by agents (e.g., OpenRouter, Anthropic API) while denying all other egress
- **Integrate OpenShell into agent infrastructure** as described in `docs/problems/agent-infrastructure.md`

### Long-term

- **Use OpenShell's L7 enforcement** to create read-only GitHub policies for review agents (can read PRs but not merge) and write policies for implementation agents (can push to feature branches but not main)
- **Contribute back:** OpenShell is Apache-2.0 and actively developed. Konflux-ci-specific policy templates and devaipod integration could be contributed to the OpenShell-Community repo.

## Open Questions

1. **Does OpenShell's proxy intercept Node.js in-process HTTP?** If opencode uses `webfetch` (which makes HTTP requests from the Node.js process), does the sandbox proxy still intercept and enforce policy? Theory says yes (all traffic routes through the proxy), but this needs testing.

2. **Can Podman replace Docker for the gateway?** The `openshell gateway start` command checks for Docker specifically. Could Podman's Docker socket compatibility mode work?

3. **What's the latency overhead of L7 interception?** For agents making many rapid tool calls, does TLS termination and HTTP inspection add noticeable latency?

4. **How does OpenShell handle the agent-needs-LLM-API problem?** When the agent itself runs inside the sandbox, it needs network access to reach the LLM API. OpenShell's provider system injects credentials, but the network policy must also allow the LLM API endpoint. Does the default sandbox image pre-configure this?

5. **Can OpenShell policies be version-controlled alongside agent configs?** Could we store policies in the konflux-ci repo and apply them automatically when agents are deployed?

## How to Reproduce

### Install OpenShell CLI

```bash
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh
```

### Run tests (requires Docker)

```bash
# Start the gateway
openshell gateway start

# Run the test suite
cd experiments/openshell-sandboxing
./run-tests.sh
```

### Manual testing

```bash
# Create sandbox with egress allowed
openshell sandbox create --name test-allow \
  --policy policy-allow-egress.yaml \
  --keep --no-auto-providers

# Inside sandbox: should succeed
curl -sf https://httpbin.org/get

# Apply deny policy
openshell policy set test-allow --policy policy-deny-egress.yaml --wait

# Inside sandbox: should fail with 403
curl -sf https://httpbin.org/get

# Check logs
openshell logs test-allow --since 5m

# Clean up
openshell sandbox delete test-allow
```

## Files

- `README.md` -- This document
- `policy-allow-egress.yaml` -- OpenShell policy permitting all HTTPS egress
- `policy-deny-egress.yaml` -- OpenShell policy denying all egress (default-deny)
- `run-tests.sh` -- Automated test harness (requires Docker for OpenShell gateway)
