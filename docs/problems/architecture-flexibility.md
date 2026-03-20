# Architecture Flexibility

How do we design a system that survives the rapid churn of the tools it depends on?

## Why this is hard

Architecture, in the most useful definition, is "the things that are hard to change later." Every architectural decision narrows future options. The challenge is that we're building on a landscape where the tooling layer is changing faster than architectural decisions normally tolerate.

Consider some recent history:

- **Agent CLI tools** — Claude Code became a favorite among developers for agentic coding. Then OpenCode emerged as an open-source alternative. Then Goose. Then OpenShell appeared last week. Each has different strengths, different licensing, different model provider dependencies. If we build our architecture assuming Claude Code is the agent runtime, and it later faces legal, regulatory, or licensing challenges, we need to swap it — and that swap needs to be cheap.
- **Agent frameworks** — Six months ago, LangChain looked like the obvious choice for building custom agents. Today, drop-in agentic tools (Claude Code, Codex CLI, Goose) have gained features faster than most teams could keep up with if they'd built their own on LangChain. The build-vs-buy calculus shifted under people's feet.
- **Models themselves** — The model a tool uses today may not be the model it uses in six months. Provider pricing changes, capability leaps, and regulatory shifts (export controls, data residency requirements) can all force a switch.
- **Review tools** — The [landscape analysis](../landscape.md) documents a field in rapid motion. CodeRabbit, Greptile, Qodo, and others are all iterating fast. Betting on one vendor's review architecture is a commitment that may not age well.

The fundamental tension: we need to make decisions that move us toward a functional system, but every decision we make now risks becoming a constraint we regret later. Doing nothing is also a decision — one that guarantees we never ship.

## What actually needs to be stable

Not everything changes at the same rate. The key to flexibility is distinguishing the parts of the system that should be stable from the parts that should be swappable, and making sure the boundary between them is clean.

**Things that change slowly (candidates for architectural commitment):**

- The coordination model (repo as coordinator, branch protection, CODEOWNERS — see [agent-architecture.md](agent-architecture.md))
- The trust model (zero trust between agents, trust derives from repo permissions)
- The communication protocol (GitHub status checks, PR comments, labels — the existing GitHub API surface)
- The intent and governance structures (how changes are authorized — see [intent-representation.md](intent-representation.md), [governance.md](governance.md))
- The security threat model and its priority ordering (see [security-threat-model.md](security-threat-model.md))

These are grounded in organizational principles and platform capabilities (GitHub, Kubernetes) that are unlikely to shift radically in the near term. They can be committed to with reasonable confidence.

**Things that change fast (candidates for abstraction or deferral):**

- Which CLI tool agents use to write code (Claude Code, OpenCode, Goose, whatever comes next)
- Which models power the agents (Claude, GPT, Gemini, open-weight models)
- Which framework or SDK connects agents to models
- Which review tool provides first-pass analysis
- The specific runtime environment agents execute in (see [agent-infrastructure.md](agent-infrastructure.md))

## Approaches

### 1. Interface-first architecture

Define the system in terms of interfaces (contracts between components) rather than implementations. The agent that writes code is defined by what it must do — create a branch, push commits, open a PR, respond to review comments — not by what tool it uses internally. The review agent is defined by what it must produce — a structured finding posted as a status check — not by which model or framework generates that finding.

**In practice:** each agent role (from [agent-architecture.md](agent-architecture.md)) becomes an interface specification:

| Agent role | Input | Output | Contract |
|---|---|---|---|
| Implementation agent | Issue + repo context | Branch with commits + PR | Must open PR against correct base, must not modify CODEOWNERS, must respond to blocking review comments |
| Review sub-agent | PR diff + relevant context | Status check (pass/fail) + structured comments | Must post within timeout, must evaluate independently, must treat input as untrusted |
| Triage agent | Issue event | Labels + priority assignment | Must classify within SLA, must be hardened against injection in issue text |

Any tool that satisfies the contract can fill the role. Claude Code today, OpenCode tomorrow, something that doesn't exist yet next quarter. The system doesn't care what's inside the box as long as the box honors the interface.

**Trade-offs:** Interface boundaries are themselves architectural decisions. Draw them wrong and you've locked in a bad decomposition. Draw them too abstractly and the interfaces don't constrain enough to be useful. The existing [agent architecture](agent-architecture.md) already defines roles with implicit contracts — making those contracts explicit is the work.

### 2. Thin integration layer

Instead of abstracting everything, keep the integration surface between the agentic system and the rest of the platform as thin as possible. The less code that touches a specific tool, the cheaper it is to replace.

**Concretely:** If an implementation agent is backed by Claude Code, the only code that knows about Claude Code is the shim that translates "here's an issue, produce a PR" into a Claude Code invocation. Everything upstream (triage, intent verification, priority assignment) and everything downstream (review, merge decision, post-merge monitoring) is tool-agnostic.

This is the strategy that [agent-infrastructure.md](agent-infrastructure.md) hints at with "thin orchestration layer" — build a small layer that triggers agents and gathers results, and let the actual agent runtime be swappable underneath.

**Trade-offs:** A thin integration layer can become a least-common-denominator problem. If Tool A has a powerful feature (e.g., built-in review capabilities) that Tool B lacks, the thin layer can't expose it without breaking abstraction. You end up underusing every tool, or building shims of increasing complexity.

### 3. Defer decisions, run experiments

Don't commit to a tool until you've tested it against your actual workloads. The [experiments/](../../experiments/) directory exists for this. Run the same task (e.g., fix a real bug in a real repo) with multiple tools. Document what worked, what didn't, and what constraints surfaced.

**The discipline:** Document the decision criteria *before* running the experiment, so you're comparing tools against requirements rather than rationalizing whichever one felt better. The criteria should include:

- Does it satisfy the interface contract for the agent role?
- What's the blast radius if we need to swap it out later?
- What data leaves our boundary? (Compliance, data residency — see [security-threat-model.md](security-threat-model.md))
- What's the licensing situation, and how stable is it?
- Can it run in our infrastructure, or does it require vendor-hosted compute?

**Trade-offs:** Deferral has a cost. Every week without a decision is a week without a functioning system. And "run experiments" can become an excuse to never commit. The discipline of explicit decision criteria and time-boxed experiments mitigates this, but doesn't eliminate it.

### 4. Compositional architecture over monolithic tooling

Resist the temptation to adopt a single platform that does everything (agent runtime + orchestration + review + model access). These all-in-one platforms are convenient, but they're the most expensive to leave.

Instead, compose the system from independent components that each do one thing:

- A tool that writes code (swappable)
- A tool that reviews code (swappable)
- A coordination layer that connects them (the repo itself — already decided, and unlikely to need swapping)
- A model provider (swappable via API compatibility)
- A runtime environment (swappable — see [agent-infrastructure.md](agent-infrastructure.md))

The key insight is that the repo-as-coordinator model from [agent-architecture.md](agent-architecture.md) already provides a natural composition boundary. Agents don't talk to each other directly — they communicate through GitHub's API surface (status checks, comments, labels). This means swapping one agent's implementation doesn't require changing any other agent. The repo is the stable interface.

**Trade-offs:** Composing independent components takes more upfront integration work than adopting a platform. You may re-implement features that a platform would give you for free. And the integration points themselves become maintenance surface area.

## The LangChain lesson

The LangChain trajectory is instructive. In early 2025, building custom agents on LangChain seemed like the path to maximum flexibility — you control the code, you choose the models, you design the workflows. By late 2025, drop-in tools like Claude Code and Codex CLI had surpassed what most custom LangChain agents could do, and they were iterating faster than any internal team could match.

The lesson is not "don't build custom." The lesson is: **don't build custom at the layer that's commoditizing fastest.** The code-generation layer is commoditizing rapidly. The review-judgment layer is commoditizing more slowly. The intent-verification and governance layers are not commoditizing at all — they're specific to your organization.

This suggests a strategy: **commit deeply to the layers that are specific to you (intent, governance, coordination, security), and hold loosely to the layers where the market is still competing (code generation, review tooling, model providers).** The specific-to-you layers are where your architecture should be opinionated. The commodity layers are where your architecture should be abstract.

## Relationship to other problem areas

- **Agent infrastructure** — the "adopt / use internal / build our own" question in [agent-infrastructure.md](agent-infrastructure.md) is a flexibility decision. The "thin orchestration layer" option is the flexibility-first approach.
- **Agent architecture** — the repo-as-coordinator model provides natural swap boundaries. Each agent role is independently replaceable because agents don't directly depend on each other. This is the system's biggest architectural advantage for flexibility.
- **Landscape analysis** — the [landscape](../landscape.md) documents a field in rapid motion. Any commitment to a specific tool needs to be re-evaluated periodically.
- **Governance** — tool selection is a governance question. Who decides to swap a tool? What's the process? What criteria must be met? The [governance model](governance.md) needs to accommodate tooling decisions without creating bottlenecks.
- **Codebase context** — the [context model](codebase-context.md) (CLAUDE.md, BOOKMARKS.md) already has a tool-specific name but tool-agnostic content. If the context file format becomes a standard across tools (as AGENTS.md suggests it might), that's a natural abstraction boundary. If each tool requires its own format, the context layer becomes a flexibility constraint.
- **Security threat model** — tool swaps introduce supply chain risk. A new tool means a new trust boundary, a new attack surface, new compliance evaluation. The security model needs to accommodate tool diversity without weakening defenses.
- **Testing agents** — the [testing-agents.md](testing-agents.md) behavioral contract approach becomes more important in a flexible architecture. If agents are swappable, the contracts that define correct behavior are what prevent regressions during a swap. Without them, every tool change is a leap of faith.

## The paradox

There's a genuine paradox here. Architecture is the set of decisions that are hard to reverse. We want an architecture that makes decisions easy to reverse. Taken to its extreme, this means "have no architecture" — which means "have no system."

The resolution is not to avoid all decisions, but to be deliberate about which decisions you make permanent and which you keep provisional. The repo-as-coordinator model, zero-trust between agents, and CODEOWNERS as the authority source — these are worth committing to. They're grounded in principles that won't change when the next agent CLI tool drops. The specific tool that writes code inside a container? That's not architecture. That's configuration. Keep it that way.

## Open questions

- How explicit should interface contracts be? Should we write formal specifications (OpenAPI-style) for each agent role, or are the implicit contracts in [agent-architecture.md](agent-architecture.md) sufficient?
- How do we handle tools that blur role boundaries? (e.g., an agent CLI tool that does both implementation *and* review — do we use it for both roles, or artificially separate them to maintain our decomposition?)
- What's the cost of a tool swap in practice? Can we estimate this for the current design? The answer determines how much abstraction investment is justified.
- How do we evaluate new tools as they appear without creating permanent evaluation overhead? Time-boxed experiments with explicit criteria are a start, but who runs them and how do results feed back into decisions?
- Is "agent context file" (CLAUDE.md / AGENTS.md) converging toward a standard, or will each tool continue to invent its own format? If formats diverge, does the context layer need an abstraction?
- How do we handle the transition period when swapping a tool? Do we run old and new in parallel (expensive but safe), cut over all at once (cheap but risky), or roll out repo by repo?
- At what point does "keeping options open" become a liability? What signals would tell us we've deferred too long and need to commit?
- How do we prevent the thin integration layer from becoming thick? What discipline prevents shim code from accumulating tool-specific logic over time?
