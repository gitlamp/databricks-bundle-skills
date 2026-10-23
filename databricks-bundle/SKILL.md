---
name: databricks-bundle
description: Author, review, migrate and verify Databricks Declarative Automation Bundles (formerly Databricks Asset Bundles) in any project layout, single- or multi-workspace. Learns the project's own conventions first, then routes work to specialist agents - scout (map the bundle), author (write resource YAML), reviewer (find deployment gaps and risky config), migrator (move SQL or notebook jobs to declarative pipelines), verifier (check deployed data). Use when the user works on databricks.yml, bundle targets, variables, jobs, pipelines, schemas or volumes, asks why something did not deploy to a target, wants a bundle review, or wants to check data a bundle produced. Do NOT use for general Spark or SQL tuning, workspace administration, or Terraform-only infrastructure.
license: MIT
---

# Databricks bundle agents

This skill has no built-in conventions. Every project structures its bundle differently, so the project's files and the user's answers decide conventions. Databricks documentation decides field-level facts.

## Files in this skill

| File | Load when |
|---|---|
| `agents/bundle-scout.md` | No project profile exists yet, or the bundle changed since it was written |
| `agents/bundle-author.md` | Creating or changing resources, variables or targets |
| `agents/bundle-reviewer.md` | Reviewing a bundle, a diff or a PR, or asking "why isn't X in target Y" |
| `agents/pipeline-migrator.md` | Moving SQL tasks or notebook jobs to declarative pipelines |
| `agents/data-verifier.md` | Checking the data a deployed workload produced |
| `references/profile-template.md` | Writing or reading the project profile |
| `references/review-checks.md` | Reviewer, and author self-check |
| `references/migration-guide.md` | Migrator |
| `references/verification-rails.md` | Verifier, and before anything that touches a workspace |
| `references/docs-lookup.md` | Any field-level question about bundle configuration |
| `references/bundle-layout.md` | Creating a new bundle, restructuring, or placing files in a project that follows this layout |
| `scripts/target_coverage.py` | Which resources exist in which targets |
| `scripts/lint_bundle.py` | Static checks for risky configuration |
| `references/starter/` | Templates and the answers format for a new bundle |
| `scripts/scaffold_bundle.py` | Rendering a new bundle in the reference layout from interview answers |

Paths are relative to this skill's folder, written `<skill-dir>` in commands. Load files only when the task needs them. The scripts need Python 3.9+ and PyYAML, but not the Databricks CLI.

## Step 1: Project profile

1. Look for `.databricks-bundle-profile.md` at the bundle root (the folder holding `databricks.yml`). **If there is no `databricks.yml` at all,** run the scout in interview mode instead, then the author's scaffolding procedure. If a bundle exists and the user asks for a new one, don't scaffold over it. Offer to restructure it, or to scaffold into a new empty folder.
2. If it exists, read it. If `databricks.yml`, the target files or the CI files changed since its `Last checked` date, run the scout in refresh mode.
3. If it does not exist, run the scout. The scout proposes answers from the files, but **you ask the user** to confirm or correct them:
   - environments, regions or workspaces, and which targets are production
   - the CLI profile or auth method per workspace (never pick one yourself)
   - how data reaches other workspaces, if it does
   - the project's own table and naming standards, if it has any
4. **Ask only what the task needs.** A coverage question needs little; adding a resource needs targets and production; a data check needs the connection. Mark everything else unknown and ask when it matters. Facts the user has already stated count as confirmed.
5. **One round of questions.** Combine the scout's questions with the routed agent's own questions (for example the author's "which targets") in a single message.
6. Offer to save the confirmed answers as `.databricks-bundle-profile.md`. Write it only if the user says yes. If they decline, keep the profile in the conversation. For a new bundle, make this offer only after scaffolding (author scaffolding step 4).

Never assume regions, environments, catalogs or identities.

## Step 2: Route

| Request | Agent(s) |
|---|---|
| "Add / change a job, pipeline, model, schema, volume, variable, target" | author, then reviewer on the result |
| "Start a new bundle" in a folder with no bundle | scout (interview mode), then author (scaffolding a new bundle), then reviewer. Load the author's scaffolding section before the interview, so its plan-mode note goes in the same message as the questions. |
| "Restructure this bundle" | scout, then author with `references/bundle-layout.md` as the first option |
| "Review this bundle / PR", "is this safe to deploy" | reviewer |
| "Why didn't X deploy to Y", "what runs where" | reviewer (coverage only) |
| "Convert this SQL job / notebook to a pipeline" | migrator, then reviewer |
| "Is the data right / complete / fresh" | verifier |
| "Explain how this bundle works" | scout summary |
| Several of the above | chain them in that order and keep one profile for all |

If the request is ambiguous, ask which outcome the user wants before starting an agent.

## Step 3: Dispatch

**With a subagent tool (for example Claude Code):**
- Run **read-only** agents (scout, reviewer) as subagents. The exception is the scout's interview mode, which can run inline. The prompt includes the full text of the agent file, the profile, the task, and the bundle root path. A large review can be split across subagents by area, such as resources, targets and CI, and run in parallel. Merge the reports afterwards.
- Run agents that **edit files or query a workspace** (author, migrator, verifier) in the main conversation, because they must confirm steps with the user.

**Without a subagent tool (for example claude.ai):** read the agent file and act in that role. Announce each switch ("Reviewer: …"), and finish one role's report before starting the next.

## Report contract (every agent)

```
## <Agent> report
Scope: what was looked at (files, targets, tables)
Changes: files written or edited, or "none (read-only)"
Findings: one line each - severity | file:line or object | what | why it matters | suggested fix
Evidence:
  Observed - seen directly in files, command output or query results
  Inferred - reasoned from code or naming, not checked against reality
  Not checked - in scope but not examined, and why
Open questions: anything the user must decide
```

Severity: `blocker` (will deploy the wrong thing or nothing), `risk` (works today but fragile or unsafe), `style` (the project decides; never fix without asking).

## Global rules

- **Existing structure wins.** The reference layout (`references/bundle-layout.md`) is a default for new or unstructured bundles, not a rule. Never move files to match it unless the user asks.
- **Match the project; verify fields.** Copy patterns from the closest existing resource in the project. For which fields exist and what they do, check the current docs (`references/docs-lookup.md`) rather than memory. If the docs and the project disagree, say so and let the user decide.
- **Show before writing.** Describe planned edits and get a yes before changing files, unless the user already asked for that exact change.
- **Never deploy, run jobs, or query production without an explicit yes** for that specific action. `bundle validate` and `bundle summary` are fine to suggest. `bundle deploy`, `bundle run` and `bundle destroy` always need approval.
- **Never read or print secret values.** Refer to secrets by scope and key only.
- **Work without the CLI.** If the `databricks` CLI is missing or not authenticated, work from files alone and say which checks therefore became "Not checked".
- **Clean up only what you created** (temporary files, scratch tables, spaces), and list what you removed.
