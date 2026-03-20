# Agent Observability

How do we see what agents are doing, why they made particular decisions, how much they cost, and where they fail?

This document explores the observability layer for an agentic development system. It is distinct from [testing-agents.md](testing-agents.md) (which verifies that agent instructions produce correct behavior) and [production-feedback.md](production-feedback.md) (which feeds platform execution signals back into agent work). Here we focus on making agent execution itself inspectable: tracing individual agent runs, attributing actions to causes, tracking cost and latency, and detecting anomalies in agent behavior over time.

## Why this matters

Traditional software has mature observability: structured logs, distributed traces, metrics dashboards, alerting. LLM-based agents are fundamentally harder to observe:

- **Non-determinism** — the same input can produce different outputs, so "what happened" is not reproducible from inputs alone. You need the actual trace.
- **Opaque reasoning** — an agent's decision is the product of a system prompt, user input, model weights, and temperature. Without capturing the full prompt/completion pair, you cannot reconstruct why an agent did what it did.
- **Cost opacity** — every LLM call has a token cost. Without per-call tracking, aggregate bills arrive with no attribution. At org scale across dozens of repos and multiple agent types, this becomes a budgeting problem.
- **Multi-step workflows** — an agent reviewing a PR may make 5–15 LLM calls: summarize the diff, check intent alignment, evaluate correctness, assess security, draft a comment. A single "review" is a tree of operations, not a single call.
- **Multi-agent composition** — when multiple sub-agents evaluate the same PR (see [code-review.md](code-review.md)), their individual traces need to be correlated into a single session to understand the overall review decision.

Without observability, debugging agent failures is guesswork. When an agent approves something it shouldn't have, or rejects something valid, or takes 45 seconds instead of 5, or costs $3 instead of $0.30 — you need to be able to answer "what happened and why."

## What needs to be observable

### Individual agent runs (traces)

Every agent invocation should produce a structured trace capturing:

- **Input context** — what the agent was given (diff, issue, intent record, prior agent outputs)
- **System prompt** — the instructions the agent operated under (version-pinned)
- **LLM calls** — each call with its prompt, completion, model, token usage, latency, and cost
- **Tool calls** — any non-LLM operations (git clone, linter run, API call) with timing and results
- **Decision output** — what the agent decided (approve, reject, escalate, comment) and its reasoning
- **Metadata** — repo, PR number, agent role, instruction version, model version, timestamp

This is the unit of debugging. When something goes wrong, you pull the trace and read it.

### Sessions and workflows

A PR review is not one agent call — it's a workflow. The triage agent classifies the PR, the intent alignment agent checks authorization, the correctness agent evaluates the code, the security agent checks for vulnerabilities, and the injection defense agent looks for prompt injection. These are separate traces that belong to the same logical session.

Session-level observability answers questions like:
- How long did the full review take end-to-end?
- Which sub-agent was the bottleneck?
- Did sub-agents disagree, and if so, how was the disagreement resolved?
- What was the total cost of this review?

### Cost and token tracking

At org scale, LLM costs are a real operational concern. Observability should provide:

- **Per-call cost** — token count and model-specific pricing for each LLM invocation
- **Per-agent cost** — aggregate cost by agent role (review agent vs. triage agent vs. implementation agent)
- **Per-repo cost** — which repos consume the most agent resources, and why
- **Per-model cost** — if multiple models are used (see [security-threat-model.md](security-threat-model.md), model diversity), which models cost what
- **Budget alerts** — threshold-based alerting when costs exceed expected ranges, per-repo or per-agent
- **Trend analysis** — are costs increasing over time? Did a prompt change increase token usage?

### Latency and performance

Agent latency directly affects developer experience and CI pipeline duration:

- **Per-call latency** — time spent waiting for LLM responses vs. time spent in tool execution
- **Queue time** — time between PR event and agent pickup (depends on [agent-infrastructure.md](agent-infrastructure.md))
- **End-to-end latency** — time from PR open to review posted
- **Latency percentiles** — p50, p95, p99 across agent types and repos
- **Bottleneck identification** — which step in a multi-agent workflow is slowest

### Behavioral drift detection

Even without instruction changes, agent behavior can drift due to model updates, context changes, or subtle prompt interactions (see [testing-agents.md](testing-agents.md), "Measuring agent capability drift"). Observability supports drift detection by:

- **Scoring agent outputs over time** — using automated evaluators (LLM-as-a-judge, rule-based checks) to score each agent decision on relevant dimensions (correctness, thoroughness, false positive rate)
- **Tracking score distributions** — if an agent's average correctness score drops over a week, that's a signal
- **Correlating drift with changes** — did the score change coincide with a model update, an instruction change, or a context change?
- **Human feedback capture** — when a human overrides an agent's decision, that's a training signal. Observability should capture the override and link it to the original trace.

### Audit and attribution

From the [security-threat-model.md](security-threat-model.md) cross-cutting principles: "every action is logged, attributable, and reviewable." Observability is the implementation of that principle for agent actions. Every merge should be traceable to: which agent approved it, under what instructions, with what model, processing what input, producing what reasoning.

This is not just a debugging concern — it's a security and governance requirement. When an incident is traced to an agent-merged PR, the investigation needs the full trace of the review that approved it.

## Langfuse as a candidate platform

[Langfuse](https://langfuse.com/) is an open-source LLM engineering platform that provides tracing, evaluation, and prompt management. It is worth evaluating because it addresses several of the observability needs above and aligns with konflux-ci's operational constraints.

### What Langfuse provides

**Tracing and sessions.** Langfuse captures structured traces of LLM application execution — each trace includes LLM calls, tool calls, timing, token usage, and cost. Traces can be grouped into sessions, which maps directly to the "PR review as a multi-agent workflow" pattern. An agent graph visualization shows the flow of complex agentic workflows.

**Cost and token tracking.** Per-call and aggregate cost tracking with model-specific pricing. Dashboard views show cost by time period, model, and user-defined dimensions (which could map to repo, agent role, or PR).

**Evaluation framework.** Langfuse supports multiple evaluation methods: LLM-as-a-judge (automated scoring of agent outputs), human annotation queues, user feedback capture, and custom evaluation pipelines via API. Evaluation scores attach to traces, enabling the "score distributions over time" pattern for drift detection.

**Prompt management.** Version-controlled prompt storage with deployment labels (production, staging), version comparison metrics (latency, cost, eval scores across versions), and a playground for interactive testing. This could complement the git-based prompt versioning described in [testing-agents.md](testing-agents.md) — git owns the source of truth, Langfuse provides the runtime metrics per version.

**Datasets and experiments.** Langfuse supports creating curated datasets (input/expected-output pairs) and running experiments against them, producing comparison reports. This overlaps with the golden-set evaluation approach in [testing-agents.md](testing-agents.md) and could provide the infrastructure for running those evaluations.

### Why it fits the constraints

**Open source and self-hostable.** Langfuse is MIT-licensed (core features) and can be self-hosted on Kubernetes, which is critical for konflux-ci's data residency and compliance needs. All product features (tracing, evaluation, prompt management, experiments) are available in the open-source self-hosted version. No data leaves the org's infrastructure.

**OpenTelemetry-based.** Langfuse's tracing is built on OpenTelemetry, which reduces vendor lock-in and allows integration with existing observability infrastructure (Prometheus, Jaeger, Grafana). If konflux-ci already runs an OTel collector, Langfuse can feed into or complement that stack.

**No runtime overhead.** SDKs send tracing data asynchronously in the background, so agent execution is not slowed by observability instrumentation.

**Multi-model support.** Langfuse traces work across model providers (OpenAI, Anthropic, etc.) and integrates with 50+ frameworks and libraries. This matters if the system uses model diversity as a security defense (see [security-threat-model.md](security-threat-model.md)).

**Air-gapped deployment.** After initial image pull, Langfuse does not require outbound network calls. This supports deployment in restricted environments.

### Where it falls short

**Single-application scope.** Langfuse is designed for one LLM application's observability. In our model, each agent type is effectively a separate application. Langfuse can handle this through projects (one per agent type) or through metadata tagging within a single project, but the multi-agent correlation story — "show me the full review workflow for PR #1234 across 5 agents" — requires session-level design work, not just out-of-the-box usage.

**No native multi-agent composition view.** Langfuse can group traces into sessions and visualize agent graphs, but it doesn't natively model the "multiple independent agents reviewing the same PR and producing a composite decision" pattern. The session and tagging primitives are there; the semantic layer is not.

**Evaluation is generic.** Langfuse's evaluation framework is flexible but domain-agnostic. The evaluators that matter for code review agents — "did this agent correctly detect tier escalation?", "did this agent miss a prompt injection?" — need to be built as custom evaluators on top of Langfuse's scoring API. The platform provides the infrastructure (attach scores to traces, track distributions, alert on regressions); the domain-specific logic is ours to write.

**Operational overhead.** Self-hosting Langfuse requires Postgres, ClickHouse, Redis, and S3-compatible storage. This is a non-trivial infrastructure footprint. Whether it's justified depends on scale — a few agents reviewing a few PRs per day may not warrant it; dozens of agents across 30+ repos generating hundreds of traces per day probably does.

**Enterprise features require a license.** SCIM, audit logging, and data retention policies are behind a commercial license. The core observability features are MIT-licensed, but the enterprise security add-ons may matter for a production deployment at Red Hat.

## Alternative approaches

### Build on existing infrastructure

If konflux-ci already runs Prometheus, Grafana, and an OpenTelemetry collector, agent observability could be built as a layer on top of that existing stack:

- Agents emit OpenTelemetry spans for each LLM call and tool call
- Custom metrics (token count, cost, latency, decision outcome) are exported as Prometheus metrics
- Grafana dashboards provide the visibility layer
- Alertmanager handles threshold-based alerting

**Pros:** No new infrastructure, consistent with existing operational practices, reuses existing expertise.

**Cons:** General-purpose observability tools are not designed for LLM-specific concerns. There's no native concept of "prompt/completion pair," "token cost," or "evaluation score." Everything would need custom instrumentation. The gap between "we have spans" and "we can debug why an agent made a bad decision" is significant.

### Use a different LLM observability platform

Other LLM observability tools exist:

- **[Arize Phoenix](https://phoenix.arize.com/)** — open-source, focused on LLM tracing and evaluation. Similar feature set to Langfuse. Built on OpenTelemetry. Arize also offers a commercial platform with more features.
- **[LangSmith](https://smith.langchain.com/)** — LangChain's observability platform. Deep integration with LangChain/LangGraph but tightly coupled to that ecosystem. Not self-hostable.
- **[Weights & Biases Weave](https://wandb.ai/site/weave)** — evaluation and tracing from W&B. Strong evaluation framework. Commercial, not self-hostable in the open-source tier.
- **[OpenLIT](https://openlit.io/)** — open-source, OpenTelemetry-native LLM observability. Lighter-weight than Langfuse. Backed by ClickHouse.

The selection criteria for konflux-ci would emphasize: open source, self-hostable, OpenTelemetry compatibility, no mandatory external data flow, active maintenance, and support for multi-agent workflows.

### Minimal viable observability (no platform)

Start with structured logging: every agent writes a JSON log per invocation with the key fields (input hash, output, model, tokens, cost, latency, decision, instruction version). Logs go into whatever log aggregation the org already uses. Analysis is ad-hoc (grep, jq, simple scripts).

**Pros:** Zero new infrastructure, immediate, no vendor or tool dependency.

**Cons:** No correlation across agents, no dashboards, no evaluation framework, no drift detection. This works for debugging individual failures but doesn't scale to continuous monitoring. You'll eventually need a platform — the question is whether to start with one.

## Relationship to other problem areas

- **[Agent Infrastructure](agent-infrastructure.md)** — Observability is a requirement of agent infrastructure. Where agents run determines what observability is possible (can we instrument the runtime? can we access the traces?). The infrastructure choice constrains observability options.
- **[Testing the Agents](testing-agents.md)** — Testing verifies behavior before deployment; observability monitors behavior in production. They are complementary. Langfuse's evaluation and dataset features overlap with the eval frameworks discussed there (promptfoo, deepeval) — the question is whether to use Langfuse for both runtime observability and offline evaluation, or to use separate tools for each.
- **[Production Feedback](production-feedback.md)** — Production feedback is about platform execution signals (PipelineRun failures, task errors) feeding into agent work. Agent observability is about the agents' own execution being observable. They intersect when an agent processes a production signal — the agent's trace shows how it interpreted and acted on that signal.
- **[Security Threat Model](security-threat-model.md)** — Auditability is a cross-cutting security principle. Agent observability is the implementation. Traces provide the audit trail for every agent action. Anomaly detection in agent behavior (unusual cost spikes, unexpected approval patterns) is a security signal.
- **[Governance](governance.md)** — Governance requires accountability: "trace an agent action back to the policy that authorized it." Observability provides the data. Every merge should link to the trace of the review that approved it, including the instruction version and model used.
- **[Code Review](code-review.md)** — The review sub-agents are the primary consumers of observability. Their multi-agent workflow is the most complex to trace and the most important to debug.

## Open questions

- What is the right level of trace granularity? Capturing every prompt/completion pair provides full debuggability but may be expensive to store and may raise data sensitivity concerns (prompts contain code snippets, issue content, etc.).
- Should traces be retained indefinitely (for audit) or subject to retention policies? What's the retention requirement for security-relevant traces (e.g., traces of reviews that led to merges)?
- How do we handle sensitive content in traces? Agent prompts include code diffs, issue descriptions, and potentially user data. Who has access to traces, and how is access controlled?
- Is Langfuse the right platform, or should we build on existing Prometheus/Grafana/OTel infrastructure? What's the threshold of agent activity that justifies a dedicated LLM observability platform?
- Can we use Langfuse's evaluation framework as the primary eval infrastructure (replacing or complementing promptfoo/deepeval), or are separate tools better for offline evaluation vs. runtime monitoring?
- How do we correlate agent traces with platform signals — e.g., "this PipelineRun failure was triaged by agent X (trace Y) which created issue Z which was fixed by agent W (trace V)"?
- What's the cost of observability itself? Storing traces, running evaluators, maintaining dashboards — this has infrastructure cost. At what scale does it pay for itself in debugging time saved?
- Should observability data feed back into agent instructions? For example, if an agent's false positive rate (measured via evaluations) exceeds a threshold, should the system automatically adjust its configuration?
- How do we prevent observability infrastructure from becoming a security target? Traces contain the full reasoning of review agents — an attacker who can read traces can learn exactly what the agents check for and craft bypasses.
