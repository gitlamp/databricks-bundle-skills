# Migrating jobs to declarative pipelines

A generic method for moving SQL tasks, notebook tasks or scripts into Lakeflow Declarative Pipelines, defined in a bundle. Check current syntax in the docs (`docs-lookup.md`). The method below is about *what* to change, not exact syntax.

## 1. Inventory
For each task, record:
- the code it runs (file, query or notebook)
- objects read and written, with full names
- how object names are built (literal, parameterized, or computed at run time)
- write mode: overwrite, append, merge, or create-or-replace
- schedule, trigger, retries and dependencies

## 2. Choose dataset types
| Legacy pattern | Usual replacement |
|---|---|
| Full rebuild of a table on every run | Materialized view |
| Incremental append from files or a stream | Streaming table |
| `MERGE` for change data | Streaming table with change-data-capture flow (`AUTO CDC` / `APPLY CHANGES`, depending on the version) |
| A view used only inside the job | Temporary or private view in the pipeline |
| Side effects (API calls, notifications, file moves) | Keep them as job tasks. They don't belong in a pipeline. |

## 3. Rewrite principles
- **The pipeline owns the lifecycle.** Statements that only set context, create tables up front or trigger refreshes are replaced by the pipeline's settings and dataset definitions. Check the docs for what the current pipeline syntax supports.
- **References:**
  - Datasets in the same pipeline: refer to them by name.
  - Objects outside the pipeline: use names that resolve per target through pipeline configuration, following the project's convention. Don't hardcode one environment's names.
- **Parameters:** parameters that only built object names become configuration or disappear. Business parameters become configuration values.
- **Metadata and quality rules** move into the dataset definitions. Decide with the user what each quality rule should do when it fails.
- **Types:** if you declare a schema, it must match what the query produces. Confirm the types on a non-production run rather than guessing.
- **Non-deterministic logic** can behave differently under incremental refresh. Call it out.

## 4. Bundle changes
- Add the pipeline resource in the project's style, attached to the same targets as the job it replaces.
- Pass target-specific names through `configuration` with `${var...}` or `${resources...}` references, following the project's convention.
- Replace the old tasks with one `pipeline_task` in the existing job (keeping schedule and notifications), or remove the job if the pipeline has its own trigger.
- List files, objects and parameters that are no longer used. Delete them only after the user approves.

## 5. Result comparison (before cutover)
1. Deploy to a non-production target, and run both the old job and the new pipeline on the same inputs.
2. Compare each output pair:
   - row counts
   - key sets (missing and extra keys)
   - a checksum per column (for example `SUM(hash(col))`) or `EXCEPT` both ways on a sample
3. Explain every difference before cutover. Differences from fixed bugs must be listed and agreed.
4. Cutover: switch schedules, monitor one or two runs, then remove the legacy objects as a separate, approved change.
