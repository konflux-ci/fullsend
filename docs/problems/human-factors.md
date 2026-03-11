# Human Factors

What happens to the people when agents take over the routine work?

The other problem documents focus on making the agentic system work correctly and securely. This one asks whether the people involved will *want* to participate alongside it, and whether the system inadvertently degrades the things that make contributing to open-source projects rewarding.

## Domain ownership and expertise

Today, people build deep knowledge of specific subsystems. "Ask Sarah about the build pipeline" or "James knows the reconciler inside out." This expertise is valuable in itself and is also a source of professional identity and satisfaction.

In a fully autonomous model, agents don't develop relationships with code the way people do. If an agent can implement, review, and merge changes to the reconciler without James, what is James's role? He may still be listed in CODEOWNERS for guarded paths, but if his main interaction is approving changes he didn't write, didn't review, and didn't design, his relationship to the subsystem changes fundamentally.

**Tensions:**

- Domain experts are exactly the people whose approval is most valuable on guarded paths. But if the only work left for them is approving agent-driven changes, the role shrinks.
- Expertise atrophies without practice. If agents do all the implementation, the domain expert's knowledge gradually becomes stale.
- Onboarding new domain experts becomes harder if the path to expertise (writing code, making mistakes, understanding consequences) is removed.

## Role shift: from author to supervisor

The vision document says "humans set direction, agents execute." For many contributors, this describes a less satisfying way to participate. Writing code, debugging, and shipping are core to why people contribute to open-source projects. Supervising agents is a fundamentally different activity.

**What changes:**

- **Creative work decreases.** Design and architecture remain human, but the hands-on problem-solving that many contributors enjoy moves to agents.
- **The feedback loop changes.** Instead of "I wrote this, I tested it, it works," the loop becomes "I described what I wanted, the agent built it, tests pass." The sense of ownership is weaker.
- **The primary output becomes intent, not code.** As described in [intent-representation.md](intent-representation.md), humans express what they want and agents implement it. The contributor's work shifts from writing Go or Rust to writing Markdown — intent documents, acceptance criteria, architectural constraints. Even "code review" isn't really code review: it's reviewing how well the agent interpreted and refined the intent. Contributors who built deep language expertise find that their daily tool is now prose.
- **The skill that matters changes.** Being effective stops meaning "writes excellent Go" and starts meaning "writes unambiguous intent documents that agents can execute correctly." This is a real skill, but it's a different one, and not necessarily what drew people to the project.

## Review fatigue

Agents handle code review (see [code-review.md](code-review.md)), so humans aren't reviewing PRs line by line. But humans still review — they review intent. On guarded paths, they approve changes to security-critical or architecturally significant areas. And they review how well agents interpreted and refined their intent documents.

This is still fatiguing, in different ways:

- **Volume.** Agents can generate and process changes faster than humans can evaluate whether the results match what they wanted. The bottleneck moves from "review this diff" to "verify this outcome aligns with what I meant."
- **Abstraction gap.** Reviewing intent alignment is harder than reviewing code. With code, you can trace logic. With intent, you're asking "did the agent understand what I meant?" — a fuzzier question that requires holding both the intent document and the implementation in mind.
- **Vigilance problem.** If agents correctly interpret intent 95% of the time, the remaining 5% becomes harder to catch. This is well-studied in automation research — humans are poor monitors of mostly-correct automated systems. The shift from code review to intent review doesn't fix this; it may make it worse, since intent misalignment is subtler than a logic bug.

## Contributor motivation in open source

Konflux-ci is an open-source project. Contributors participate for reasons beyond a paycheck — learning, building reputation, solving interesting problems, and being part of a community.

If agents handle routine contributions, what's left for human contributors?

- **High-value contributions become the only contributions.** This could raise the barrier to entry — new contributors often start with small fixes and build up to larger work.
- **Community dynamics change.** If most PRs are from agents, the social fabric of the project (review conversations, mentorship through PR feedback, shared ownership) thins out.
- **Recognition shifts.** In open-source, your commit history is your CV. If agents write most of the code, how do contributors demonstrate their value?

## Job security and professional value

Most konflux-ci contributors are paid engineers. For them, the concerns above have an additional dimension:

- If agents can do the routine 80% of the work, organizations need fewer engineers for the same output. The remaining engineers need to be the ones capable of the hard 20%.
- The transition period is particularly uncomfortable — people are being asked to help build a system that may reduce the need for their role.
- "Humans set direction" is reassuring until you realize that direction-setting is a smaller team than implementation.

This doesn't mean autonomous agents are wrong. But pretending this concern doesn't exist will generate resistance that looks like technical objections but is actually about something deeper.

## What might help

These aren't solutions — they're directions worth exploring:

- **Guarded paths as meaningful ownership.** CODEOWNERS isn't just a security mechanism — it preserves genuine human ownership of the areas that matter most.
- **Agents as force multipliers, not replacements.** Design workflows where agents handle toil so humans can focus on harder, more interesting problems. But verify that this actually happens in practice — it's easy for "focus on harder problems" to quietly become "there are no problems left for you."
- **Rotation and growth.** If domain experts risk skill atrophy, create deliberate opportunities for hands-on work — spikes, experiments, prototypes that agents don't touch.
- **Transparent metrics.** Track not just agent effectiveness but human engagement. If humans are rubber-stamping intent approvals on guarded paths, the system is failing even if the code is correct.
- **Contributor pathways.** Explicitly design how new contributors enter the project when agents handle the easy on-ramps. Mentorship, pairing, or reserved "human-first" areas could help.
- **Honest communication.** Be open about the tensions. If the scope of human work is genuinely changing, say so — people will engage more constructively with a clear picture than with vague reassurances.

## Relationship to other problem areas

- **Governance** decides who controls the system, but human factors determine whether people *engage* with that control or quietly disengage.
- **Autonomy spectrum** defines what agents can do. Human factors asks what the experience is like for the humans on the other side of that boundary.
- **Code review** designs the agent review process. Human factors asks what it's like for humans when code review — traditionally a core engineering activity — is no longer something they do.

## Open questions

- How do we measure whether the contributor experience is healthy? What signals indicate disengagement before people quietly stop participating?
- Is there a natural limit to agent autonomy that preserves meaningful human involvement, or does the logic of automation always push toward full autonomy?
- How do we avoid a two-tier system where a small number of "architect" humans set direction while everyone else writes intent documents? Is that even avoidable?
- What skills should contributors be building to stay effective in a heavily agentic workflow?
- How do we handle the fact that different people will feel differently about this? Some engineers will welcome agent autonomy; others will experience it as loss. One-size-fits-all approaches won't work.
- Can agents themselves help with the human factors — for example, by surfacing "this area hasn't had human-authored changes in 6 months" as a signal worth attention?
