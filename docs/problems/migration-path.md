# Migration Path

How do we get from today's human-driven development workflow to agent-driven development? The vision doc says "start anywhere, learn everywhere" — but in practice, the first steps matter. A bad first experience will kill adoption. A good one builds momentum.

## The current state

Today, development across konflux-ci looks roughly like this:

1. Humans triage issues and prioritize work
2. Humans (sometimes with coding agents) implement changes and open PRs
3. Humans review PRs, sometimes with CI checks (linters, unit tests, integration tests)
4. Humans approve and merge
5. CI/CD pipelines build, test, and deploy

There's no unified review tooling. Some repos have thorough CI; others have minimal checks. CODEOWNERS files exist in some repos but not all. Test coverage varies wildly (see [repo-readiness.md](repo-readiness.md)). The process is informal and relies heavily on individual maintainer knowledge.

The gap between this and "fully autonomous agents handling routine development" is large. Bridging it requires incremental steps that deliver value at each stage, not a big-bang rollout.

## The sequencing problem

Multiple problem areas need to be solved, and they have dependencies:

- **Agents can't review well** without understanding intent → need the intent system
- **The intent system** needs governance to define tiers → need governance decisions
- **Governance** needs experimentation data to make good decisions → need agents running somewhere
- **Agents running somewhere** need repos to be ready → need readiness improvements
- **Readiness improvements** could be done by agents → need agents to be trusted first

This is circular. The way out is to start with the lowest-risk, highest-signal activities and iterate.

## Proposed phases

### Phase 0: Observation (now → weeks)

**Goal:** Understand what actually happens today. Build the data foundation for later decisions.

**Actions:**
- Run [agentready](https://github.com/ambient-code/agentready) assessments across all repos in the org to get a baseline readiness score
- Extend the coverage dashboard with additional readiness signals: CODEOWNERS presence, CI job reliability (flaky test rate), linter enforcement, `CLAUDE.md` or equivalent presence
- Catalog the content types per repo (Go, Tekton YAML, shell, React, Python) to understand the heterogeneity agents will face
- Identify 2-3 candidate repos for Phase 1 based on: high test coverage, reliable CI, active maintainers willing to participate, and manageable scope

**Delivers:** A clear picture of where we are and which repos are closest to ready. No agents touching production yet.

### Phase 1: Shadow review (weeks → months)

**Goal:** Run review agents in parallel with human reviewers. Compare agent decisions to human decisions. Build confidence (or learn where agents fail).

**Actions:**
- Deploy review agents on candidate repos in comment-only mode — agents post review comments but cannot approve or block
- Start with a single review concern (e.g., correctness only) rather than all 6 sub-agents at once. This reduces noise and makes it easier to evaluate agent quality.
- Track metrics: agreement rate between agent and human reviewers, false positive rate (agent flags something human wouldn't), false negative rate (human catches something agent missed), review latency
- Collect feedback from human reviewers: are the agent's comments useful? Distracting? Wrong?
- Iterate on agent prompts, context loading, and sub-agent decomposition based on real data

**Delivers:** Data on agent review quality. Human reviewers get a second opinion. No risk — agents can't approve or merge anything.

**Key decision point:** Do agent reviews add value? If the false positive rate is too high, humans will ignore them (and then ignore real findings). If the agreement rate is too low, the agents aren't ready for autonomy.

### Phase 2: Assisted review (months)

**Goal:** Agents become required reviewers but humans retain merge authority.

**Actions:**
- Add agent review as a required status check on candidate repos — PRs can't merge without agent review completing, but a human still approves
- Expand to multiple review sub-agents (correctness + security, then intent alignment)
- Introduce the pre-PR review pattern: developers using coding agents run the review sub-agents locally before opening a PR
- Begin CODEOWNERS cleanup: ensure guarded paths are properly configured on candidate repos
- Start filing issues from drift detection agents (like the ADR-0046 scanner) — agents identify problems, humans decide what to do

**Delivers:** Faster review cycles (agent provides immediate first-pass feedback). Quality baseline from agent reviews. CODEOWNERS infrastructure ready for Phase 3.

### Phase 3: Conditional autonomy (months → ongoing)

**Goal:** Agents can auto-merge specific categories of changes on graduated repos.

**Actions:**
- Start with Tier 0 changes only: dependency updates that pass CI, linter fixes, documentation typo fixes. These are the lowest-risk changes with the clearest intent ("we always want these").
- Implement the minimal intent verification needed: for Tier 0, the intent is implicit ("this is a category we always approve"). The agent verifies the change actually falls in this category.
- Require all review sub-agents to pass before auto-merge (unanimous approval for the initial rollout — loosen later based on data)
- Monitor closely: any bad merge triggers automatic revert to Phase 2 for that repo
- Gradually expand the set of auto-mergeable change types as confidence grows

**Delivers:** Actual autonomous merges for the safest change categories. Real-world data on the autonomy model. A mechanism for expanding autonomy incrementally.

### Phase 4: Full autonomy for graduated repos

**Goal:** Agents handle Tier 0 and Tier 1 changes autonomously. Tier 2+ still requires human authorization.

**Actions:**
- Implement the intent system (git-based ledger or equivalent) for Tier 2+ changes
- Agents can implement and merge tactical changes (bug fixes with linked issues) autonomously
- Human-guarded paths via CODEOWNERS remain inviolable
- Periodic human audits of agent-merged changes (weekly? monthly?) to catch drift

**Delivers:** The vision for routine changes. Humans focus on strategic decisions and guarded paths.

## Which repos first?

Based on the [repo-readiness](repo-readiness.md) data and practical considerations:

**Strong candidates for Phase 1:**
- **release-service** (87.5% coverage) — well-tested Go service with active maintenance
- **notification-service** (85.0% coverage) — smaller scope, high coverage, less security-critical
- **repository-validator** (82.4% coverage) — focused scope, good coverage

**Interesting but harder:**
- **build-definitions** — the most critical repo, but it's Tekton YAML, not Go. Needs the Tekton-specific review capability from [tekton-pipeline-review.md](tekton-pipeline-review.md) before agents can review effectively.
- **integration-service** (68.4% coverage) — central to the system but coverage could be higher

**Not yet:**
- Repos with <50% coverage
- Repos with no coverage data
- Security-critical infrastructure repos (regardless of coverage)

## The bootstrap problem

Several pieces of infrastructure need to exist before agents can operate:

- **Agent GitHub identity** — bot accounts or GitHub App installations that agents use to post comments and status checks. These need to be set up, permissioned, and secured.
- **Agent execution environment** — where do agents run? Local developer machines (for pre-PR review)? CI infrastructure (for PR-level review)? Dedicated agent infrastructure?
- **Agent configuration** — CLAUDE.md files, system prompts, context loading configuration per repo. Who writes the initial version? How is it tested?
- **Monitoring and alerting** — dashboards for agent activity, alert on anomalies, mechanism to revoke agent authority in an emergency

Each of these needs to be solved before Phase 1 can start, but none of them need to be solved perfectly. Start simple and iterate.

## Anti-patterns to avoid

- **Big-bang rollout** — don't try to enable agents on all repos simultaneously. The failure modes are different per repo and need individual attention.
- **Skipping shadow mode** — the temptation is to go straight to agent autonomy on "easy" repos. Shadow mode builds the data and trust foundation that makes autonomy defensible.
- **Optimizing for speed over safety** — the goal is not "agents merge as fast as possible." The goal is "agents merge correctly." Speed is a bonus of correctness, not a substitute for it.
- **Ignoring the human experience** — if human reviewers find agent comments noisy, unhelpful, or annoying, they'll disable or ignore them. Agent output quality matters more than agent output volume.
- **Assuming homogeneity** — what works for a Go controller repo won't work for build-definitions. The migration path per repo depends on the repo's content type, test infrastructure, and maintainer culture.

## Relationship to other problem areas

- **Repo readiness** — determines which repos are candidates for each phase
- **Autonomy spectrum** — Phase 3-4 implement the graduated autonomy model
- **Governance** — who decides when a repo moves between phases? Who can revert a repo to a lower phase?
- **Code review** — Phases 1-2 are specifically about validating the review sub-agent model
- **Intent representation** — needed by Phase 4, but the simpler phases can proceed without it

## Open questions

- What's the minimum viable shadow mode? Can we run a single review agent on a single repo as a GitHub Action and start collecting data this week?
- How do we handle the organizational change management? Developers need to understand what the agents are doing, why, and how to give feedback. What's the communication plan?
- How do we handle repos where the maintainers don't want agent involvement? Is participation mandatory at the org level, or opt-in per repo?
- What metrics define success at each phase? What's the threshold for moving to the next phase?
- How do we handle the cost? Running multiple LLM-powered review agents on every PR across 30+ repos is expensive. What's the cost model and who pays?
- Can Phase 0 and Phase 1 run concurrently on different repos, or do we need Phase 0 data before starting Phase 1?
