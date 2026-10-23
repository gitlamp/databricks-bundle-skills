# databricks-bundle-skills

A skill that helps an AI coding agent work on **Databricks Declarative Automation Bundles** (formerly Databricks Asset Bundles). You install it as one skill, and it routes work to five specialist agents:

| Agent | What it does | Edits files? |
|---|---|---|
| **bundle-scout** | Maps your bundle, then asks you about environments, workspaces, production targets and auth to build a project profile. In an empty folder, it interviews you for a new bundle instead. | no |
| **bundle-author** | Writes jobs, pipelines, schemas, variables and targets in *your* project's style, in exactly the targets you intend. Can scaffold a new bundle from your answers. | yes, after you approve |
| **bundle-reviewer** | Finds resources missing from targets, risky literals, production settings and CI pinning problems | no |
| **pipeline-migrator** | Moves SQL or notebook jobs to Lakeflow Declarative Pipelines, with a result comparison before cutover | yes, after you approve |
| **data-verifier** | Checks deployed data (freshness, completeness, key-level reconciliation) with strict safety rules | no (read-only queries, after you approve) |

The skill ships **no built-in conventions**. It learns your conventions from your files and your answers, and checks field-level facts against the current Databricks docs.

## Install

**Claude Code** (agents run as subagents):
```bash
cp -r databricks-bundle /path/to/your/repo/.claude/skills/
```
or, for every project, copy it to `~/.claude/skills/`.

**Claude apps** (agents run as modes in one conversation): zip the `databricks-bundle` folder and upload it under Settings → Capabilities → Skills.
```bash
zip -r databricks-bundle.zip databricks-bundle -x '*/__pycache__/*'
```

## Usage

There are two ways to start the skill. Both go through the same orchestrator, which picks the agent for you.

**Describe what you want.** Claude loads the skill when your request matches it:
```text
review my bundle before we deploy
add a pipeline to the dev and prod targets
why isn't the orders job in prod?
```

**Call it directly in Claude Code** with the skill name, followed by your request:
```text
/databricks-bundle review my bundle
/databricks-bundle create a new bundle in this folder
/databricks-bundle check that the orders table in dev is fresh
```

The five agents are parts of one skill, not separate commands. `/bundle-reviewer` and similar commands don't exist. To reach a specific agent, say what you want done, for example "review", "add a job", "convert this SQL job" or "check the data", and the orchestrator routes it:

| You ask for | Agent that runs |
|---|---|
| explain or map the bundle; a new bundle in an empty folder | bundle-scout |
| add or change jobs, pipelines, models, schemas, variables or targets; scaffold a new bundle | bundle-author, then bundle-reviewer |
| review, pre-deploy check, "why isn't X in target Y" | bundle-reviewer |
| convert a SQL or notebook job to a declarative pipeline | pipeline-migrator, then bundle-reviewer |
| check freshness, completeness or quality of deployed data | data-verifier |

The first time, the scout asks a few questions about your setup, such as environments, which targets are production and how you connect to each workspace. It offers to save the answers as `.databricks-bundle-profile.md`, so it doesn't ask again.

**Starting from scratch:** in an empty folder, ask "create a new bundle". The scout asks about your workspaces, environments, catalogs, layout and CI. The author shows the files it will create, then writes them after you approve. For the parts that need more judgement, such as the first real workload, production identity and CI, it suggests using plan mode (Shift+Tab in Claude Code) so you can review each plan before files change.

## Scripts you can use without an agent

To render a new bundle in the [reference layout](databricks-bundle/references/bundle-layout.md), copy and edit [answers.example.yml](databricks-bundle/references/starter/answers.example.yml), then run:
```bash
python3 databricks-bundle/scripts/scaffold_bundle.py --answers my-answers.yml --out path/to/new-bundle --dry-run
```
Drop `--dry-run` to write the files. The script never overwrites files and refuses a folder that already has a bundle.

The two check scripts read the bundle YAML directly. They need Python 3.9+ and PyYAML, but not the Databricks CLI. They exit non-zero when they find problems, so they work as CI checks.

```bash
python3 databricks-bundle/scripts/target_coverage.py --bundle path/to/bundle
```
```bash
python3 databricks-bundle/scripts/lint_bundle.py --bundle path/to/bundle --prod-targets prod
```

- `target_coverage.py` prints a resource × target matrix and flags resources missing from some targets, plus definitions that are never attached. Intended gaps go in an allow-list (`--allow gaps.yml`) or inline (`--allow-entry jobs.export=dev-b,prod-b`). For exact results, pass saved `databricks bundle validate -o json` output with `--from-validate-json <target>=<file>`.
- `lint_bundle.py` runs the generic checks `L001`–`L012` described in [review-checks.md](databricks-bundle/references/review-checks.md). Turn rules off with `--disable`.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install pyyaml pytest
```
```bash
.venv/bin/python -m pytest
```

The tests run the scripts against fixture bundles in `tests/fixtures/` (four layout styles, including the reference layout, with planted defects) and check the skill's structure. No workspace is needed. [`evals/evals.json`](databricks-bundle/evals/evals.json) lists behaviour checks to run by hand with an agent against the same fixtures.

## Limits
- YAML parsing approximates what the CLI resolves. Use `--from-validate-json` when exactness matters.
- The scripts don't evaluate `${...}` interpolation. A variable that resolves to the same catalog in every target is not detected.

