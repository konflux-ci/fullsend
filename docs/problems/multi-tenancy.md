# Multi-tenancy

Konflux is a multi-tenant system. Agents operating on the Konflux codebase need to understand tenant boundaries — both to avoid introducing multi-tenancy bugs and to maintain the security guarantees Konflux provides to its users.

## Why this matters for the agentic system

### Agents need to understand isolation boundaries

Konflux isolates tenants through a combination of Kubernetes namespaces, RBAC, network policies, and application-level access controls. A change that looks correct in single-tenant testing might break tenant isolation in production. Human reviewers who work on Konflux internalize these boundaries through experience. Agents need them made explicit.

Examples of multi-tenancy-relevant changes that agents need to handle correctly:

- A new API endpoint that queries data — does it filter by tenant? Can a tenant see another tenant's resources?
- A controller reconciling resources — does it use the correct namespace scope? Does it accidentally watch cluster-wide when it should watch tenant-scoped?
- A pipeline task that accesses shared infrastructure — can one tenant's pipeline read another tenant's artifacts, secrets, or build logs?
- A caching optimization — does the cache key include the tenant identifier? Can cache poisoning from one tenant affect another?
- Shared infrastructure components (ingress, DNS, certificate management) — can one tenant's configuration affect another's routing or TLS?

### The dual nature of multi-tenancy in Konflux

Konflux has two distinct multi-tenancy concerns:

1. **Workspace/tenant isolation within Konflux itself** — different teams and organizations use the same Konflux instance, isolated by namespaces and RBAC. Changes to Konflux's controllers, APIs, and services must preserve this isolation.

2. **Build-time isolation** — when Konflux runs builds for different tenants, those builds must be isolated from each other. A malicious or compromised build from tenant A must not be able to affect tenant B's builds, artifacts, or pipelines. This is where Tekton's PipelineRun-level isolation, hermetic builds, and the trusted task model intersect.

Agents reviewing changes need to understand both layers and flag changes that could weaken either.

## Multi-tenancy as a review concern

### Where it fits in the sub-agent model

Multi-tenancy doesn't map cleanly to any single review sub-agent from [code-review.md](code-review.md):

- The **correctness agent** might catch a missing namespace filter, but only if it understands multi-tenancy semantics
- The **platform security agent** should catch RBAC and data exposure issues, but may not recognize tenant boundary violations specifically
- The **content security agent** handles pipeline-level isolation, which is one facet of multi-tenancy

The concern cuts across multiple sub-agents. Options:

1. **Dedicated multi-tenancy sub-agent** — loads tenant boundary definitions, RBAC models, and namespace conventions as context. Reviews every change for isolation violations. Clear responsibility, but another agent in the chain.
2. **Multi-tenancy as context for existing sub-agents** — the platform security and correctness agents each get multi-tenancy rules as part of their context. Avoids adding another agent, but dilutes the responsibility.
3. **Multi-tenancy as an architectural invariant** — define tenant isolation rules in the architecture repo and enforce them through the invariant system (see [architectural-invariants.md](architectural-invariants.md)). Some rules are mechanical (every query must include a namespace scope), some are design-level (this service must never access cross-tenant data).

Option 3 is likely the right foundation — multi-tenancy invariants belong in the architecture repo. But some invariants will be too nuanced for structural tests and will need sub-agent comprehension.

### Common multi-tenancy bug patterns

A review agent focused on multi-tenancy would look for these patterns:

- **Missing namespace scoping** — a `List()` or `Watch()` call without a namespace filter. In a multi-tenant system, cluster-scoped queries are almost always wrong for user-facing data.
- **Cross-namespace references** — a controller in namespace A creating or modifying resources in namespace B. Sometimes legitimate (e.g., system controllers managing tenant namespaces), often a bug or a security issue.
- **Shared state without tenant isolation** — caches, queues, or temporary storage that don't partition by tenant. Can lead to data leakage or cross-tenant interference.
- **Label/annotation-based filtering as the sole isolation mechanism** — labels can be modified by anyone with access to the resource. Namespace-based isolation is stronger because namespace access is controlled by RBAC.
- **Implicit single-tenant assumptions** — code that assumes "there's only one X" when in production there's one X per tenant. Global variables, singletons, or hardcoded resource names that don't include a tenant identifier.
- **Error messages leaking tenant data** — a controller that includes resource details in error messages visible to other tenants (through shared log aggregation, status conditions on shared resources, etc.).

### The testing gap

Multi-tenancy bugs are notoriously hard to test:

- **Unit tests** typically run in single-tenant mode — they test one namespace, one user, one context
- **Integration tests** may set up multiple namespaces but rarely test adversarial cross-tenant scenarios
- **E2E tests** in CI often run with cluster-admin privileges, masking permission issues that would affect real tenants

This means the test coverage numbers from [repo-readiness.md](repo-readiness.md) overstate readiness for multi-tenancy correctness. A repo with 85% test coverage might have 0% of that coverage testing tenant isolation. This is a concern for agent autonomy — agents that rely on "tests pass" as a confidence signal might miss multi-tenancy regressions that no test checks for.

## The namespace model

Konflux's namespace model is defined by ADRs in the architecture repo (ADR-0010, ADR-0012, and others). Key points:

- Each tenant workspace maps to a Kubernetes namespace
- The namespace name format encodes the tenant and workspace identity
- Controllers typically watch specific namespaces, not the whole cluster
- Some system components are cluster-scoped and must carefully handle cross-namespace operations

Agents need to understand this model to review namespace-related changes correctly. A change to the namespace naming convention (ADR-0012) is not a simple refactor — it affects tenant isolation, RBAC policies, and every controller that uses namespace-based scoping.

## Relationship to other problem areas

- **Security threat model** — tenant isolation is a security boundary. Weakening it is a security incident, not just a bug. The platform security agent needs multi-tenancy awareness.
- **Architectural invariants** — tenant isolation rules are architectural invariants that should be enforced both at review time and through periodic drift detection. "Every controller must scope queries to the tenant namespace" is an enforceable invariant.
- **Code review** — multi-tenancy is a cross-cutting review concern that the sub-agent model needs to account for, either through a dedicated sub-agent or through context enrichment of existing sub-agents.
- **Tekton pipeline review** — build-time isolation between tenants is a Tekton-level concern. PipelineRun isolation, workspace isolation, and artifact isolation all matter.
- **Repo readiness** — test coverage for multi-tenancy scenarios is likely a gap across the org. This should be part of the readiness assessment.

## Open questions

- How do we represent tenant isolation rules in a way agents can consume? RBAC policies are in Kubernetes, namespace conventions are in ADRs, isolation expectations are in design docs. There's no single source of truth.
- Should multi-tenancy testing be a prerequisite for agent autonomy? If so, what's the minimum viable multi-tenancy test suite?
- How do we handle the case where a legitimate feature intentionally crosses tenant boundaries (e.g., a system admin viewing all tenants)? How does the review agent distinguish intentional cross-tenant access from a bug?
- Can we build a static analysis tool that detects missing namespace scoping in Go controllers? This would be analogous to the ADR-0046 drift scanner but for multi-tenancy invariants.
- How do we handle shared infrastructure components (ingress controllers, cert-manager, monitoring) where tenant isolation happens at a different layer than namespace scoping?
- How should agents handle the dual multi-tenancy concern (workspace isolation + build-time isolation)? Are these the same review concern or two separate ones?
