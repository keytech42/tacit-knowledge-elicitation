# Development Workflow

## Test-First for Behavior Changes

Before implementing any behavior change:

1. **Find all affected tests**: Grep for every test file that asserts on the behavior being changed. Include backend unit tests, E2E tests, and frontend type checks.
2. **Trace all callers**: For modified functions, components, or props — check every call site. A prop change in `UserPicker` means checking every file that renders `<UserPicker>`.
3. **Update tests first**: Modify assertions to expect the new behavior. Mark as `xfail` or `skip` where the implementation doesn't exist yet. Write new tests for new behavior.
4. **Implement**: Write the feature code. Watch xfails flip to pass.
5. **Run the full relevant test suite** before considering the work done.

## Self-Review Checklist

After implementation, before declaring "done", verify:

- Every test file touching changed behavior has been reviewed and updated
- All callers of modified interfaces (functions, components, props, API contracts) are consistent
- E2E tests covering affected UI paths still pass with the new behavior
- No stale assumptions in test assertions (e.g., exclusion lists, expected counts, hardcoded IDs)
- Settings/config changes are tested in both enabled and disabled states (try/finally restore)

## PR Preparation

When creating a PR:

1. Write a clear title (<70 chars) and summary with test plan
2. After creation, consider supplementary PR comments for:
   - Design rationale (why this approach over alternatives)
   - Maintenance notes (what to watch for when modifying this code later)
   - Migration steps (if applicable)
   - Testing instructions (manual test flows)
3. Only add comments if they provide value beyond the PR body
