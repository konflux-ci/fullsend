# Methodology

How this exploration progresses. Not a rigid process — a description of the phases we expect to pass through and what characterizes each one.

## Phase 0: Problem identification (nearing completion)

The goal was to expand the problem space: think about the idea of gate agents automatically merging agent-written code to production and identify everything that makes us uncomfortable about it. Each problem got its own document in `docs/problems/`.

This went well. We got a good handle on the problems quickly. But we're reaching diminishing returns — we can't productively ask more questions without deciding on, implementing, and resolving some basic ones. The right instinct in this phase was "what are we missing?" That instinct has done its job.

## Phase 1: Technical framework (next)

We need to make foundational technical choices and build an implementation that establishes the framework for addressing the problem set we seeded in Phase 0. The broader contributor community cannot contribute productively until a technical framework is in place for them to contribute *to*.

Choices that need to be made in this phase:

- What platform do agents run on? ([agent infrastructure](problems/agent-infrastructure.md))
- Are we reusing a larger framework (OpenHands, OpenClaw, etc.) or building on something lighter? ([agent infrastructure](problems/agent-infrastructure.md), [agent architecture](problems/agent-architecture.md))
- Where do we define agent skills? ([agent architecture](problems/agent-architecture.md), [codebase context](problems/codebase-context.md))
- How do we test changes to the agents themselves — CI for agents? ([testing agents](https://github.com/konflux-ci/fullsend/pull/14))
- How do we establish the flywheel, so that the system learns to propose improvements to itself?

Where possible, we continue to devise experiments to build confidence in solutions. Experiments should test both the positive case (does this approach work when things go right?) and the negative case (does it fail safely when things go wrong?). Experiments are documented in `experiments/`.

The exit criteria for this phase: a working proof of concept that people can react to and start contributing to. Not a production system — a concrete demonstration of the framework that makes the abstract problem documents tangible.

## Phase 2: Domain contributions

When the technical framework is in place, we can begin to invite the broader organization to observe the system's behavior and start planning domain-specific contributions. The questions shift from "how does the system work?" to "how do we teach it our domain?"

- What makes a good Konflux task?
- What makes a good Konflux build task?
- How do you debug a failed Konflux e2e test?
- How do you catch an "improvement" to Konflux that inadvertently degrades security?

This is where the community's diverse expertise becomes the critical input. The framework from Phase 1 gives them something concrete to work with — a system they can observe, critique, and extend.

## Governance and rollout

The path from validated solutions to adoption depends on how we resolve the [governance](problems/governance.md) problem. Governance determines who has authority to make binding decisions, how the community participates in those decisions, and what process turns an explored solution into an adopted one.

Rollout should be slow and deliberate. Start with low-risk repositories, expand scope as confidence grows, and maintain human review requirements until the system has earned trust through demonstrated reliability. The governance model should encode this — not as a permanent constraint, but as a starting posture that can be relaxed based on evidence.

The PoC at the end of Phase 1 is a critical enabler here: it gives the community something concrete to evaluate rather than asking them to react to abstract proposals.
