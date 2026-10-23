# Verification rails

Rules for any step that touches a live workspace. They apply to every agent, not only the verifier.

## Before running anything
1. **State the scope:** workspace, target or environment, tables, and the question being answered.
2. **Let the user choose the connection.** List profiles only with `databricks auth profiles`, and warehouses with `databricks warehouses list -p <profile>` once a profile is chosen. Never read `~/.databrickscfg` or other config files directly: they can hold tokens. Ask which to use. Never pick one, and never fall back to a default profile silently.
3. **Production needs its own yes.** If any table or workspace is production, say so explicitly and wait for approval of that specific action.
4. **Show the queries** before running them. Estimate the cost for large tables: use partition filters, `TABLESAMPLE` or `LIMIT` where they give the same answer.

## While running
- Read-only statements only: `SELECT`, `DESCRIBE`, `SHOW`, `EXPLAIN`, and `DESCRIBE HISTORY`.
- Never print secret values, tokens, connection strings or personal data. Aggregate or mask instead.
- If you need a scratch object (a temporary view or table), say so first, create it in a location the user approves, and track it.

## Judging results
- **Compare on keys, not only on totals.** Classify each key as matching, missing, extra or different.
- **Rule out expected differences first,** such as load timing, filters applied by the workload, and time zones.
- **Confirm the comparison data is complete** before counting anything as missing.
- **Two independent checks** before calling something a defect.

## Reporting
Every statement goes in exactly one bucket:
- **Observed:** backed by a query or command you ran. Include it, with the numbers.
- **Inferred:** reasoned from code, names or partial results.
- **Not checked:** in scope but not done, with the reason (no access, too expensive, user declined).

Avoid summary verdicts like "looks fine". List the checks and results instead.

## Afterwards
- Remove only the scratch objects you created, and list them.
- Never remove or change an object that existed before you started, even if it looks unused.
