# Performance and Load Impact Verification

Agents are notorious for writing code that passes unit tests but causes performance disasters in production. How do we catch performance regressions before they ship — especially in an architecture where most code is Kubernetes controller logic that can't be meaningfully benchmarked outside a cluster?

## Why this is an agent-specific problem

Human developers build intuitions about performance over time. A senior engineer working on Konflux knows that adding a Kubernetes API LIST call inside a reconcile loop is dangerous. They recognize that controller reconciliation needs to complete quickly or the work queue backs up. They've debugged the controller that leaked goroutines and they don't want to repeat the experience.

Agents have none of this. They optimize for the objective they're given, and that objective is almost always functional correctness: make the tests pass, satisfy the spec, match the types. Performance is a cross-cutting concern that rarely appears in task descriptions and is almost never verified by unit tests.

This creates a specific failure mode: agent-generated code that is correct, well-tested, passes all CI checks, gets merged — and then degrades the system under real-world load. The code review agents described in [code-review.md](code-review.md) may catch obvious cases, but performance problems are often subtle and context-dependent. They need dedicated detection mechanisms.

## Why Konflux makes this especially hard

Konflux is a Kubernetes-native CI/CD platform. Its components are primarily controllers and operators that reconcile custom resources, coordinate Tekton PipelineRuns across tenant namespaces, and interact heavily with the Kubernetes API server. This architecture creates specific challenges for performance verification that go beyond what a typical web application faces:

- **The "database" is the Kubernetes API server.** There are no SQL queries to analyze. Performance problems manifest as excessive LIST/WATCH calls to the API server, unbounded label selector queries, or controllers that re-list resources they should be watching. Traditional N+1 query detection tooling doesn't apply.
- **Controller logic needs a cluster to test.** Most code can't be meaningfully benchmarked with `testing.B` alone — it's reconciliation logic that needs a real or simulated Kubernetes environment (envtest, a real cluster). Setting up realistic performance tests requires significant infrastructure.
- **Builds and tests are Tekton PipelineRuns.** Pipeline execution time and resource consumption are core performance concerns. A task change that adds 5 minutes to every build pipeline affects every tenant. But pipeline performance depends on cluster scheduling, image pull times, and resource contention — factors that vary between environments.
- **Integration tests are Tekton pipelines too.** They receive a `SNAPSHOT` parameter (JSON containing all component images) and run against the assembled application. There's no simple way to add a "run benchmarks" step that exercises the full system — you'd need a running Konflux instance with realistic tenant workloads.
- **The platform runs its own CI.** Konflux builds and tests itself using Konflux. A performance regression in the platform can slow down the platform's own CI, which delays detection of the regression — a self-referential problem.
- **Multi-tenant resource contention matters.** A controller that works fine with 10 tenants might overwhelm the API server with 1000. Performance testing that doesn't simulate realistic tenant counts misses the most impactful regressions.

## The landscape of performance problems

Performance regressions in the konflux-ci codebase take forms specific to Kubernetes-native systems:

### Controller and API server regressions

- Excessive LIST calls to the Kubernetes API server (the Konflux equivalent of N+1 queries) — listing resources inside reconcile loops instead of using the local cache. (Kubernetes controllers maintain an in-process cache of cluster state, kept up to date via watch streams. Reading from this cache is essentially free; making direct API server calls is not. Agents frequently bypass the cache and make direct calls.)
- Unbounded label selector queries that return far more objects than needed
- Controllers that each set up their own watches on the same resource types instead of sharing a single cached view, multiplying API server load
- Reconcile loops that re-fetch resources already available in the reconcile request
- Missing pagination on API server calls that return unbounded result sets

### Resource regressions

- Memory leaks from unclosed resources, growing caches, or retained references
- Goroutine leaks in Go controllers (a common agent mistake — spawning goroutines without lifecycle management)
- Controllers that hold references to large Kubernetes objects (e.g., entire PipelineRun status) longer than needed
- Unbounded work queues or channel buffers in controller logic

### Concurrency regressions

- Lock contention from overly broad mutexes in shared controller state
- Controllers that serialize work that could be parallelized across independent resources
- Missing rate limiting on fan-out operations (e.g., a controller that reacts to one resource change by updating hundreds of others)

### Pipeline and build regressions

- Tekton task changes that dramatically increase build times across all tenants
- Pipeline modifications that pull unnecessary images or run redundant steps
- Task resource requests (CPU/memory) that waste cluster capacity or cause scheduling delays
- Changes to build-definitions tasks that affect every repo using default pipelines

## Detection approaches

There is no single mechanism that catches all performance regressions. The question is which combination of approaches gives sufficient coverage without making CI prohibitively slow or complex.

### Static analysis for performance anti-patterns

Linters and static analyzers can detect known performance anti-patterns without running the code.

**What it catches:** Kubernetes API calls inside loops, unbounded allocations, missing `defer` for resource cleanup in Go, controllers bypassing the local cache to make direct API calls, known-slow API usage patterns.

**What it misses:** Context-dependent performance issues, problems that only manifest at scale or under multi-tenant load, algorithmic complexity that requires understanding the data shape.

**Trade-offs:** Fast, cheap, low false-negative rate for known patterns. But the known-pattern set is finite — novel performance problems slip through. For Go specifically, tools like `ineffassign`, `prealloc`, and custom lint rules could catch agent-common mistakes. The question is whether maintaining performance-specific lint rules is worth the effort versus other approaches.

**Agent relevance:** Static analysis is especially valuable for agents because the anti-patterns agents produce tend to be repetitive. Once you identify that agents commonly make direct API server calls inside reconcile loops instead of using the local cache, a lint rule catches it every time.

### Benchmark suites

Dedicated benchmarks that measure the performance of critical paths, run in CI, with regressions flagged automatically.

**What it catches:** Performance regressions in benchmarked code paths. Go's built-in `testing.B` benchmarks work for pure logic, but most Konflux controller code interacts with the Kubernetes API, so benchmarks either need envtest (which simulates a real API server) or must be limited to self-contained helper functions.

**What it misses:** Anything not benchmarked. Benchmark coverage tends to be sparse — teams write benchmarks for known hot paths but not for code that "shouldn't be" performance-sensitive (until an agent makes it so). More fundamentally, benchmarking a controller's reconcile loop in envtest doesn't capture real-world API server latency, etcd performance, or multi-tenant contention.

**Trade-offs:** Benchmarks add CI time. Since Konflux CI runs as Tekton PipelineRuns, benchmark tasks add to pipeline execution time for every build. Benchmark results are noisy — performance varies between runs due to pod scheduling, node load, and resource contention in the shared cluster. Statistical approaches (running multiple iterations, comparing distributions) help but add more pipeline time and cluster cost.

**Agent relevance:** Agents are unlikely to write benchmarks on their own unless explicitly asked. The benchmark suite needs to be maintained by humans (or by agents specifically tasked with benchmark coverage as a goal).

### Load and integration testing

Running the platform under realistic multi-tenant load and measuring controller reconciliation times, API server load, pipeline throughput, and resource consumption.

**What it catches:** System-level performance issues that unit benchmarks miss — interaction effects between controllers, API server contention under tenant load, pipeline scheduling bottlenecks, resource exhaustion patterns.

**What it misses:** Problems that only manifest at full production scale or with production tenant distributions.

**Trade-offs:** Extremely expensive for Konflux specifically. "Realistic load" means a Kubernetes cluster running the full set of Konflux controllers, with simulated tenants creating Components, triggering PipelineRuns, running IntegrationTestScenarios against Snapshots, and executing release pipelines. This is a complex multi-service system where performance depends on the interactions between controllers, the API server, etcd, Tekton, and cluster scheduling. Standing up a representative environment is a significant infrastructure investment.

Integration tests in Konflux are themselves Tekton pipelines that receive a `SNAPSHOT` parameter and run against the assembled application. Adding performance verification means either extending these existing integration test pipelines (which are already expensive to run) or creating a separate performance test infrastructure.

Options for when to run load tests:

- **On every PR:** Not feasible — the infrastructure cost and pipeline time are prohibitive
- **Nightly on main:** Catches regressions within a day, but doesn't tell you which PR caused it. Requires a dedicated cluster running a sustained simulated workload
- **On PRs that touch performance-sensitive paths:** Requires maintaining a list of what counts as "performance-sensitive" — which is exactly the kind of judgment agents are bad at
- **On-demand, triggered by review agents:** A review agent flags a PR as "performance-relevant" and triggers a load test run. Depends on the review agent's judgment

### Profiling gates

Automated profiling (CPU, memory, allocations) integrated into CI, with comparison against a baseline.

**What it catches:** Changes in allocation rates, CPU hotspots, memory growth patterns.

**What it misses:** Problems that only appear under concurrent load or multi-tenant contention. Profiling a single controller reconciliation won't show lock contention or API server pressure from many controllers reconciling simultaneously.

**Trade-offs:** Go's `pprof` tooling makes this relatively easy for the Go controllers. But profiling controller code meaningfully requires it to be reconciling real (or realistic) resources — profiling in envtest captures different characteristics than profiling under production API server latency. Comparing profiles programmatically is harder — tools exist but they tend to produce noisy results. Flame graph diffs are informative for humans but hard for an automated gate to act on.

### Performance budgets

Define explicit budgets (reconcile loop < 10 seconds, memory per controller pod < 512MB, default build pipeline < 30 minutes, API server request rate per controller < N/sec) and enforce them in CI or staging.

**What it catches:** Any regression that pushes a metric past its budget, regardless of the cause.

**What it misses:** Gradual degradation that stays within budget (death by a thousand cuts). Budgets need periodic review and tightening.

**Trade-offs:** Budgets are simple and clear — they give both agents and humans an unambiguous target. But setting good budgets requires understanding what "good" looks like, which requires baseline measurement across a representative cluster. For Tekton pipeline budgets specifically, execution time depends on cluster conditions (scheduling, image caching, node resources) that vary between environments — a budget set on one cluster may not transfer to another.

**Agent relevance:** Performance budgets are particularly useful for agents because they're concrete and testable. An agent can understand "reconcile must complete in under 10 seconds" in a way it can't understand "don't make things slower."

### Runtime anomaly detection

Monitor production systems for performance anomalies and correlate them with recent deployments.

**What it catches:** Regressions that all pre-production mechanisms missed. The last line of defense.

**What it misses:** This isn't prevention — the regression is already in production. The goal is fast detection and rollback, not prevention.

**Trade-offs:** Requires mature observability infrastructure. Konflux already generates platform execution signals (PipelineRun failure rates, scheduling latency, task execution times) that could serve as anomaly detection inputs — see the pipeline execution feedback discussion in PR #8. Requires automated rollback capability or fast human response. The lag between deployment and detection means some tenants experience the regression.

## Agent-specific anti-patterns to watch for

Based on observed behavior across agentic coding tools, agents commonly produce these performance mistakes:

- **The "make it work" reconcile body:** Agents solving a failing test will add whatever logic is needed inside the reconcile loop, including direct API server calls that should use the local cache, creating O(n) API calls per reconciliation where a cached lookup would suffice.
- **The redundant fetch:** Agents don't naturally use the local cache or pass fetched objects between functions. They'll re-GET the same Kubernetes resource multiple times within a single reconciliation, or LIST resources that are already available from the cache.
- **The kitchen-sink import:** Agents import heavy dependencies to use a single function, adding initialization cost, binary size, and container image size — the last of which affects pipeline execution time across every tenant pulling that image.
- **The unbounded retry:** Agents implement retry logic in controllers without backoff, jitter, or circuit breaking, creating thundering herd potential against the API server during partial outages.
- **The goroutine leak:** Agents spawn goroutines in controller logic without proper lifecycle management — no context cancellation, no shutdown signaling — creating goroutines that outlive the reconciliation that started them.

These patterns are detectable by static analysis if codified into rules. The challenge is maintaining the rule set as new anti-patterns emerge.

## Interaction with other problem areas

- **[Code Review](code-review.md):** A performance-focused review sub-agent could be added to the review decomposition. It would evaluate diffs for performance implications using codebase context (is this a controller reconcile loop? does this code path make API server calls?). This is complementary to automated detection — the review agent catches what the linters miss, and the linters catch what the review agent misses.
- **[Repo Readiness](repo-readiness.md):** Benchmark coverage and performance test infrastructure could be added to the readiness criteria. A repo without performance baselines is harder to protect from agent-introduced regressions. For controller repos, this might mean envtest-based benchmarks of reconciliation paths.
- **[Architectural Invariants](architectural-invariants.md):** Some performance requirements are architectural invariants ("the reconcile loop must complete in under 10 seconds," "controllers must read from the local cache, not make direct API calls"). These should be enforceable by the invariant system.
- **[Codebase Context](codebase-context.md):** Performance context — which reconcile paths are hot, which controllers have tight latency requirements, where the known API server bottlenecks are — could be included in agent context files. This helps agents avoid performance mistakes in the first place rather than catching them after the fact.

## Open questions

- Which detection mechanisms are worth investing in first for konflux-ci? Static analysis is cheapest but narrowest. Load testing is most thorough but most expensive — and in Konflux's case, requires a dedicated multi-tenant cluster. Where's the right starting point?
- How do we benchmark controller logic that depends on the Kubernetes API server? Envtest provides a real API server but not realistic latency or contention. Real clusters are expensive and noisy. Is there a middle ground?
- Should there be a dedicated performance review sub-agent, or should performance concerns be folded into the existing correctness agent? Controller performance patterns are specialized enough that a general-purpose reviewer may miss them.
- How do we set meaningful performance budgets for controllers that have never had them? What baseline measurement process makes sense when performance depends on cluster conditions and tenant count?
- Can agents be taught to proactively use the local cache, respect API server rate limits, and manage goroutine lifecycles? Or is reactive detection (catching regressions after they're written) the more practical path?
- How do we handle the tension between CI speed and performance testing thoroughness? CI runs as Tekton PipelineRuns — every benchmark task added to the pipeline increases build time for every PR.
- What role should production monitoring play? If we have good runtime anomaly detection (e.g., via the pipeline execution feedback signals described in PR #8) with fast rollback, does that reduce the need for pre-merge performance verification?
- How do we prevent performance budgets from becoming stale? Controller workload profiles change as the platform gains tenants and features. Who reviews and updates budgets?
- Are there konflux-ci-specific performance invariants that should be documented immediately (e.g., reconcile loop time limits, maximum API server request rates per controller, default pipeline execution time ceilings)?
- How do we performance-test changes to build-definitions tasks that affect every tenant's build pipeline? A 30-second regression in a shared task multiplied across all tenants is a major impact, but testing it requires running real pipelines.
