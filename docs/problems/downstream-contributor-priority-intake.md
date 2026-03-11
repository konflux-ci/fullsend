# Downstream Contributor Priority Intake

How do downstream contributors express business priorities into the Konflux open source project, and how does the project reconcile competing sources of strategic intent?

## Why this matters now

Konflux has one downstream contributor today: Red Hat. Red Hat employs most contributors, funds the infrastructure, and drives the roadmap. Red Hat's priorities become project priorities by default because nobody else is at the table.

This works — until it doesn't. The project's governance structure (the elected KGC, the ADR process, open contribution) is designed to support a multi-lateral community. But there is no formal mechanism for how downstream contributor business priorities become project priorities. That gap is invisible with one downstream contributor. With two or more, it becomes the central political question of the project.

Two things exist today that partially address direction-setting:

1. **The KGC** has formal authority over architectural decisions through ADRs. This governs the *shape* of the system — how things are built, what invariants hold.
2. **Feature direction** — *what* gets built and in what order — flows informally from Red Hat's internal planning. No project-level body formally owns this.

The gap between these two is where this problem lives.

## The contribution-weighted model and why it's breaking

Open source projects have traditionally resolved priority conflicts through contribution-weighted influence: what gets built is what someone shows up to build. If a downstream contributor wants a feature, it assigns engineers to implement it. If nobody cares enough to write the code, the feature doesn't happen.

This worked as a natural filter. Code was expensive to produce. Only well-motivated priorities attracted sufficient investment. The cost of implementation served as a proxy for organizational commitment.

LLM-generated code breaks this model. When any contributor can produce a polished implementation for the cost of an afternoon's token budget, the filter disappears. A well-implemented PR is no longer evidence that the contributing organization made a strategic commitment — it may just mean someone had an idea and an API key.

This creates a new problem: the project must now evaluate contributions against strategic intent, not just technical quality. "Done" is no longer evidence that something "should be done." Without an explicit priority mechanism, the project risks accepting well-crafted contributions that warp its shape in ways no stakeholder actually intended.

## Models for priority intake

### Model A: Single central list

All contributors play in one priority list with no special treatment for downstream contributor organizations. Anyone proposes features through the same process — for example, the intent repo's `proposed/` directory described in [intent-representation.md](intent-representation.md). The KGC or an equivalent body authorizes what moves forward.

Downstream contributor PMs and architects have no formal standing in the project. They are contributors like anyone else. Their influence comes from the quality of their proposals, not their employer.

**Strengths:**
- Simple and egalitarian
- Prevents capture by any single downstream contributor
- Consistent with open source norms

**Weaknesses:**
- Ignores the reality that downstream contributors fund the work. A downstream contributor investing heavily in people and infrastructure has legitimate interest in direction. Pretending otherwise may drive downstream contributors to fork or disengage.
- No mechanism for downstream contributors to plan internally against the project roadmap, because they don't control it.

### Model B: Federated priority lists with reconciliation

Each contributing organization maintains its own priority list. A reconciliation process — run by the KGC, a priority council, or a rotating chair — merges these into a project roadmap. Conflicts surface explicitly rather than through informal politics.

**Strengths:**
- Acknowledges that downstream contributors have distinct business needs
- Makes conflicts visible rather than hidden
- Allows downstream contributors to plan internally against their own list while still coordinating

**Weaknesses:**
- Overhead of the reconciliation process
- Risk of gridlock when priorities conflict directly
- Who breaks ties? The largest contributor has the most leverage regardless of formal structure.

### Model C: Downstream contributor priorities as input, project priorities as output

Downstream contributors submit priority requests, but the project maintains its own independent priority list owned by the KGC. Downstream contributor input is one signal among several — community demand, technical debt, security needs, architectural health. An explicit insulating layer separates downstream contributor priorities from project priorities.

The project can say "no" to a downstream contributor priority that would fragment the codebase or conflict with architectural invariants. Downstream contributors accept that their priorities are requests, not directives.

**Strengths:**
- Protects project coherence — the KGC can reject priorities that would fragment the project
- Balances business needs against project health
- Makes the insulating layer explicit rather than pretending it doesn't exist

**Weaknesses:**
- Downstream contributors may feel they lack influence proportional to their investment
- The insulating layer could become a bottleneck or a political arena
- Requires the KGC (or a delegated body) to make judgment calls that will sometimes displease major funders

### Model D: Contribution-weighted influence (historical baseline)

No formal priority mechanism. What gets built is what someone builds. Included here because it describes the default state of most open source projects — and the model that LLM-generated code is disrupting (see previous section).

**Strengths:**
- Zero overhead
- Self-regulating when code is expensive to produce

**Weaknesses:**
- Breaks down when code is cheap — volume of contributions no longer signals organizational commitment
- No protection against project fragmentation through well-implemented but unwanted contributions
- Provides no framework for resolving conflicts between downstream contributors with different visions

## Failure modes

No model eliminates all failure modes. The choice is which failures you structurally prevent and which you tolerate.

### Fragmentation (most dangerous)

Multiple downstream contributors pull the project in incompatible directions. Under Model A, this manifests as competing feature proposals that can't coexist architecturally. Under Model B, reconciliation fails to find common ground and both features get built, creating maintenance burden and confused users. Under Model C, the insulating layer picks winners and losers, and losers may fork.

The KGC's existing ADR authority provides some defense — architectural invariants constrain the design space — but ADRs govern structure, not feature direction. Two features can each be architecturally sound while still being strategically incompatible.

### Capture

The largest contributor dominates regardless of formal structure. Under Model A, they outnumber others in proposals and discussion. Under Model B, their priority list is longest and their reconciliation leverage is greatest. Under Model C, the KGC members are mostly employed by the dominant downstream contributor, and the "insulating layer" insulates in name only.

Capture is the hardest failure mode to prevent structurally because it reflects real power dynamics. Formal rules help, but only if the community is willing to enforce them against its largest funder.

### Gridlock

Requiring multi-lateral consensus stalls decision-making. Most acute under Model B, where reconciliation can deadlock. Model C mitigates this by giving the KGC final authority, but at the cost of downstream contributor buy-in — a downstream contributor that gets overruled repeatedly may stop investing.

### Freeloading

Downstream contributors consume the project without contributing proportionally. Less existential than the other failure modes, but it corrodes contributor morale. Models B and C make contribution levels visible; Models A and D obscure them.

## The agent dimension

### Agents as accelerant

The priority intake problem exists independent of agents. But agents make it more urgent.

When agents can implement a proposed feature in hours rather than weeks, the volume of "proposed and implemented" contributions increases. The project needs a priority mechanism that operates at agent speed without becoming a rubber stamp. This connects to [intent-representation.md](intent-representation.md)'s tiered model — Tier 2+ features need explicit authorization before agents can merge them. But *who proposes and who authorizes* is the downstream contributor priority question this document addresses.

The intent system's `proposed/` to `approved/` workflow assumes someone is filtering proposals. The priority intake model determines who that someone is and what criteria they use.

### Agent resource authority

Agents consume tokens. In a multi-lateral context, token budget is a shared project resource. Who is authorized to direct agent effort?

The options mirror the priority models:

- **Egalitarian** (Model A style) — anyone can assign work to agents. Simple but potentially expensive and chaotic. A downstream contributor could flood the backlog with low-value tasks that consume shared resources.
- **Proportional** (Model D style) — token budget is allocated proportional to contribution. This reintroduces contribution-weighted influence through a different door. It also requires defining what counts as "contribution."
- **Centrally managed** (Model C style) — the KGC controls the token budget as a project resource and allocates it according to project priorities, not downstream contributor priorities.

This connects directly to the backlog/priority agent described in [agent-architecture.md](agent-architecture.md), which "needs access to strategic intent to make good decisions." The priority intake model chosen here determines what that agent's input looks like and whose priorities it serves.

## Relationship to other problem areas

- **[Intent representation](intent-representation.md)** — This document addresses *where* strategic intent originates. Intent representation addresses *how* it gets encoded and enforced. The priority intake model feeds the intent system's `proposed/` directory. Note: intent-representation.md currently references "architects and PM" as approvers — these are downstream contributor roles with no formal standing in the project. The priority intake model must clarify how downstream contributor roles relate to project authority.
- **[Governance](governance.md)** — The KGC's role in priority reconciliation is a governance question. This document may motivate expanding the governance discussion beyond agent policy to include feature direction authority.
- **[Agent architecture](agent-architecture.md)** — The backlog/priority agent's design depends on the priority intake model. Its inputs, its ranking criteria, and its authority to assign work all derive from decisions made here.
- **[Autonomy spectrum](autonomy-spectrum.md)** — If different downstream contributors have different risk tolerances for agent autonomy in repos they care about, the priority model needs to account for that tension.

## Open questions

- Should the KGC's mandate expand to cover feature direction, or does that need a separate body?
- How do you prevent the reconciliation process (in Models B and C) from becoming a political arena that drives downstream contributors away?
- If token budget is allocated by contribution, what counts as "contribution"? Code? Infrastructure? Funding? Community management?
- How does this interact with the existing ADR process — are ADRs a subset of priority decisions, or a parallel track?
- What's the minimum viable priority process for a project with one downstream contributor today that doesn't preclude multi-lateral participation later?
- How do you detect and prevent capture when the dominant downstream contributor also employs most KGC members?
- Should downstream contributors be able to fund agent work on their own priorities outside the shared token budget — essentially a "bring your own tokens" model? Does that undermine project coherence or enable healthy experimentation?
- How does the priority intake model interact with the "try it" pattern from intent-representation.md? Should downstream contributors be able to direct agents to build exploratory draft PRs for their priorities without going through the full authorization process?
