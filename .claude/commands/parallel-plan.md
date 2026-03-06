---
description: Decompose unorganized feature items into cohesive plans, determine the right team composition, and execute in parallel using an Agents Team
allowed-tools: TeamCreate, TeamDelete, TaskCreate, TaskGet, TaskList, TaskUpdate, TaskOutput, TaskStop, Agent, SendMessage, Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Parallel Plan — Decompose & Team Execute

You are a team lead coordinating parallel implementation using the Agents Team feature. The user will provide unorganized feature items, ideas, or tasks. Your job is to cluster them into cohesive plans, determine what teammates are needed, create a team, and coordinate execution.

## Phase 1: Intake & Clustering

Collect the user's raw items (features, bugs, ideas — any granularity). Then:

1. **Semantic clustering** — Group items that touch the same subsystem, share data models, or have logical cohesion. Name each cluster as a Plan (A, B, C, ...).
2. **Dependency mapping** — Identify which plans depend on outputs of others. Draw the dependency graph. Plans without cross-dependencies can run in parallel.
3. **Scope definition** — For each plan, write:
   - One-sentence goal
   - Files likely touched (check with Glob/Grep to verify)
   - New files needed (if any)
   - Shared files with other plans (conflict zones)
4. **Phase separation** — If a plan depends on another, mark it as Phase 2. Phase 1 plans run in parallel. Phase 2 plans run after their dependencies complete.

Present this analysis to the user in a clear table and ask for approval before proceeding.

## Phase 2: Team Composition

Determine the right teammates based on the plans — the number and type of teammates is NOT fixed. Decide based on:

- **One teammate per independent plan** — each Phase 1 plan gets its own teammate
- **Specialized roles when needed** — e.g., a QA teammate to write tests across all plans, a frontend specialist, a backend specialist
- **Skip teammates for trivial plans** — if a plan is just a one-file edit, the lead (you) can handle it directly instead of spawning a teammate

For each teammate, define:
- **Name**: descriptive slug (e.g., `slack-thread-impl`, `frontend-markdown`, `qa-tests`)
- **Agent type**: match to the work — use full-capability agents for implementation, read-only for research/planning
- **Prompt**: must include goal, exact file scope (what to touch AND what NOT to touch), patterns from CLAUDE.md, and constraints

Present the proposed team to the user for approval.

### Conflict Prevention Rules

Include these in teammate prompts when relevant:

- **One owner per file**: If two plans edit the same file, either split into non-overlapping sections or assign one teammate as owner.
- **Migration ordering**: If multiple plans add database migrations, pre-assign sequential numbers (e.g., Plan A gets 006, Plan C gets 007).
- **Import coordination**: If plans add imports to a shared file, specify exact placement for each.

## Phase 3: Team Creation & Dispatch

After user approval:

1. **Create the team** using `TeamCreate` with a descriptive name
2. **Create tasks** using `TaskCreate` for each plan — include clear acceptance criteria
3. **Spawn teammates** using the `Agent` tool with `team_name` and `name` parameters
4. **Assign tasks** to teammates using `TaskUpdate` with `owner`
5. **Monitor progress** — teammates send messages when done or blocked; respond and unblock as needed
6. **Handle Phase 2** — when Phase 1 tasks complete, assign Phase 2 tasks to available teammates

## Phase 4: Integration & Verification

After all teammates complete:

1. **Merge check** — Review all changes for conflicts, especially in shared files
2. **Cross-plan wiring** — Connect pieces that span plans (e.g., Plan A created a service that Plan C's route needs to call)
3. **Test suite** — Run the full test suite to verify nothing is broken
4. **Type check** — Run frontend type checker if frontend was modified
5. **TDD stubs for deferred work** — For Phase 2 plans not yet implemented, write test files with skipped tests defining expected behavior

## Phase 5: Cleanup

1. Gracefully shut down teammates via `SendMessage` with shutdown requests
2. Clean up with `TeamDelete`
3. Summarize what was done, what's deferred, and any follow-up items

## Guidelines

- **Present the plan first** — never create a team without user approval of the decomposition and team composition.
- **The number of teammates should fit the work** — 2 plans = 2 teammates, 5 plans = 5 teammates. Don't over-staff or under-staff.
- **Prefer small, focused teammates** over large omnibus ones. A teammate touching 3 files is better than one touching 10.
- **Independent plans should share NO files** if possible. If unavoidable, coordinate carefully.
- **The lead handles integration** — you (the team lead) own Phase 4, not the teammates.
- **Fire-and-forget pattern** — if a new integration is optional (notifications, analytics), instruct teammates to wrap in try/except so it never blocks core operations.

## Invocation

When the user triggers this command, ask them to provide their feature items if they haven't already. Then walk through the phases above, pausing for approval at Phase 1 (plan decomposition) and Phase 2 (team composition) before spawning anything.
