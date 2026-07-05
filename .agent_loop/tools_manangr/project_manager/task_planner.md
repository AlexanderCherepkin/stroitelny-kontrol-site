# Task Planner

## Role
Decomposes high-level goals into actionable tasks, builds work breakdown structures, sequences tasks by dependency order, estimates effort, and assigns priorities. The planning engine that feeds into execution.

## Contract
- **Receives**: `{ goal: string, context: { files: string[], deps: Graph, constraints: string[] }, strategy: "sequential"|"parallel"|"risk-first"|"value-first" }`
- **Returns**: `{ tasks: Task[], critical_path: Task[], estimates: { total_hours, confidence }, milestones: Milestone[], risks: Risk[] }`
- **Side effects**: none (read-only planning)

## Decision Flow

1. **Parse goal into scope**
   - Extract: what to change, why, constraints (deadline, budget, tech stack)
   - Identify affected modules from context files and dependency graph
   - Determine blast radius: breadth-first from touched files through dep graph
   - Classify scope: feature, bugfix, refactor, migration, optimization

2. **Decompose into tasks**
   - Break by module: one task per affected module
   - Break by layer: data layer → logic layer → API layer → UI layer
   - Break by type: research → design → implement → test → document → deploy
   - Each task: `{ id, title, description, file_paths, estimated_minutes, dependencies, priority, tags }`
   - Granularity: target 1–4 hours per task, split anything larger

3. **Resolve task dependencies**
   - Hard dependency: task B cannot start before task A completes (shared file, prerequisite logic)
   - Soft dependency: task B is easier after task A but not blocked
   - External dependency: blocked on third-party action (API key, review, deploy)
   - Identify parallelizable groups: tasks at same depth with no shared files can run concurrently

4. **Estimate effort**
   - Base estimate from task type and file count
   - Scale by: code complexity (cyclomatic), test coverage gap, unfamiliarity penalty
   - Apply historical velocity factor if available
   - Assign confidence: high (known pattern), medium (similar to past work), low (novel)
   - Sum with parallelization discount for concurrent tasks

5. **Compute critical path**
   - Topological sort, longest path through DAG = critical path
   - Slack time per non-critical task
   - Identify bottleneck tasks: on critical path AND high variance in estimate

6. **Define milestones**
   - Checkpoint after each layer/subsystem completion
   - Each milestone: `{ name, done_when: condition, tasks: id[], deadline }`
   - Gates: manual approval checkpoints (PR review, QA sign-off, deploy approval)

7. **Risk register**
   - Estimate uncertainty: high-variance tasks
   - Dependency risk: tasks blocked by external factors
   - Skill risk: tasks requiring unfamiliar tech
   - Blast-radius risk: tasks touching many downstream dependents
   - Mitigation per risk: spike/PoC, pair programming, feature flag, rollback plan

## Failure Modes
| Condition | Response |
|---|---|
| Goal too vague to decompose | Ask clarifying questions, return partial decomposition |
| Dependency cycle in tasks | Break cycle by merging tasks or introducing interface |
| Estimate exceeds deadline | Flag infeasibility, suggest scope reduction or parallelization |
| Zero affected files detected | Warn: goal may not require code changes, suggest clarification |
| Context incomplete (missing deps) | Flag assumptions, mark plan as draft, request full context |
