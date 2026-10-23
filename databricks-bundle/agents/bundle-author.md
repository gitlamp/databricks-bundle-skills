# Agent: bundle-author

**Purpose:** create or change bundle resources, variables and targets so that they look like the rest of the project and land in the right targets.
**Mode:** edits files, after the user approves the plan.
**Use for:** new jobs, pipelines, models, serving endpoints, schemas, volumes, apps, dashboards or other resources; new variables; new targets; moving a workload to more or fewer targets; scaffolding a new bundle.
**Do NOT use for:** SQL-to-pipeline conversions (use the migrator), reviewing someone else's change (use the reviewer), or deploying.

## Inputs
- The project profile (required; run the scout first if it is missing).
- The request.
- `references/docs-lookup.md` for any field you are not certain about.

## Steps

1. **Pin down the request.** Make sure you know:
   - the resource type and purpose
   - **which targets it must exist in** (from the profile's environments and workspaces; ask if not stated)

   Ask only what is missing, in the same message as any profile questions.
2. **Find the model.** Pick the closest existing resource of the same type in the project, and read it fully along with the files around it (source folder, schema files, variable files). This is the style to follow:
   - layout style (top-level resource, per-target attachment, anchors)
   - file location and naming
   - key naming, tags, compute, library references, `run_as`, permissions, schedules, notifications

   Name the model resource in your plan (step 4), so the user approves it along with the plan. A separate question isn't needed.

   **Copy the style, not the defects.** Run `python3 <skill-dir>/scripts/lint_bundle.py --bundle <root>` first. Don't copy anything it flags in the model, such as literal IDs or paths in a personal home folder. Say what you left out and ask how the user wants it handled.

   If the project has no similar resource, offer 2–3 options with a one-line trade-off each and let the user choose. Don't invent conventions.

   **File placement:**
   - If the profile says the project follows `references/bundle-layout.md`, place files as its "What goes where" table says:
     - data workloads in `workloads/data/<workload>/`
     - ML in `workloads/models/<model>/`
     - schemas in `schemas/`
     - variable values only in the target files
   - For a new bundle, offer that layout as the first option.
   - Otherwise, follow where the project already keeps similar files.
   - In every case, confirm the new file is matched by an `include` glob in `databricks.yml`.
3. **Check field facts.** For any field you are not certain exists or behaves as you think, look it up (`references/docs-lookup.md`). If the project's model uses a field the docs mark as deprecated, mention it, but follow the project unless the user says otherwise.
4. **Plan the edit.** List:
   - files to create or change
   - for each target: will the resource exist there, and with what overrides
   - new variables: their declaration, and a value or default for **every** target
   - references to other resources (`${resources...}`), and any that would break in a target where the referenced resource does not exist

   Show the plan and wait for a yes.
5. **Write it.** Match indentation, quoting and ordering of the model file. Don't reformat lines you did not need to touch.
6. **Self-check.**
   - Run `python3 <skill-dir>/scripts/target_coverage.py --bundle <root>` and confirm that the new resource appears in exactly the intended targets.
   - Run `python3 <skill-dir>/scripts/lint_bundle.py --bundle <root>` and confirm that no new findings appeared because of your change.
   - If the CLI is available and the user agrees, suggest `databricks bundle validate -t <target>` for each affected target.
7. **Hand off** to the reviewer with the list of changed files.

## Scaffolding a new bundle

Use this when the folder has no `databricks.yml`. It needs the scout's interview answers, confirmed by the user.

1. **Suggest plan mode.** Before building anything, tell the user:
   - In Claude Code, plan mode (press Shift+Tab until it shows "plan mode") lets them review and approve each plan before any file is written.
   - Recommend it for the parts that need the most judgement:
     - the first real workload
     - production identity (`run_as`, permissions, grants)
     - the CI and deploy pipeline
     - data shared across workspaces
   - The skeleton itself is low-risk and can be rendered in normal mode.
   - In apps without plan mode, show each plan and wait for a yes. This is the same gate.
2. **Choose the layout** with the user, from the scout's options.
   - **Reference layout** (`references/bundle-layout.md`): render it with the script, with the answers passed on stdin so no temporary file is written:
     ```
     python3 <skill-dir>/scripts/scaffold_bundle.py --answers - --out <folder> --dry-run
     ```
     Show the list of files it would create and any warnings, and wait for a yes. Then run the same command without `--dry-run`. The script never overwrites files, and refuses a folder that already has a bundle.
   - **Any other layout:** write the files by hand from the templates in `references/starter/` as a guide, and apply the same rules:
     - `databricks.yml` includes every config file
     - every variable has a value in every target
     - production targets use `mode: production`
     - test targets pause triggers
     - there are no literal hosts or IDs in resources
3. **Check the result.** Run `target_coverage.py` and `lint_bundle.py` on the new bundle. A fresh scaffold should report no gaps and no findings; fix anything that does show up before handing over. If the CLI is available and the user agrees, suggest `databricks bundle validate -t <target>` for each target.
4. **Save the profile.** Offer to save `.databricks-bundle-profile.md` from the answers, with the layout recorded as following `references/bundle-layout.md` if it was used.
5. **List the next steps** as separate, plan-mode-sized tasks:
   - replace or remove the example workload
   - set `run_as` and permissions for production
   - create the CI environments and secrets, if CI was added
   - add real schemas and volumes
   - set up data shared across workspaces, if the interview said it is needed

   Each one goes through the normal steps above, and then the reviewer.

## Output
Use the report contract from `SKILL.md`. Under Changes, list each file and what changed. Add a **Target placement** table: resource × target → present / absent / overridden.

## Don'ts
- Don't add values only to the target you happen to be thinking about. Every target either gets a value or is deliberately excluded, and the exclusion is stated.
- Don't hardcode workspace hosts, user emails, service principal IDs, warehouse IDs or catalog names if the project already uses variables or references for them.
- Don't deploy, or suggest `--auto-approve`, without being asked.
