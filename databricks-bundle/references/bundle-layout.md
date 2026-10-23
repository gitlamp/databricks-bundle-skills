# Reference bundle layout

A suggested folder structure for one bundle that deploys to several workspaces or regions, and that covers both data workloads and ML. Use it:
- when **creating a new bundle**, or a project with no clear structure yet: offer it as the first option
- when the user **asks to restructure**
- as the placement guide, if the profile records that the project follows it

**Never** move or rename files in an existing project to match this layout unless the user asks. A project with its own consistent structure keeps it, and that is not a finding.

```
bundle/
├── databricks.yml          # name + include globs only
├── variables.yml           # declarations, no values
├── targets/
│   ├── region-A.yml        # dev-A, prod-A
│   └── region-B.yml        # dev-B, prod-B
├── workloads/
│   ├── data/<workload>/
│   │   ├── resources/      # *.job.yml, *.pipeline.yml
│   │   └── src/            # notebooks, SQL, Python
│   ├── features/<domain>/  # shared feature tables
│   └── models/<model>/
│       ├── resources/      # model, train/deploy/inference jobs, endpoint
│       └── src/            # training, validation, inference code
├── schemas/                # catalogs, schemas, grants (+ ML schemas)
├── volumes/
└── libraries/              # shared code, built as wheels (+ ML utils)
```

Region names, environments and the number of target files come from the user. `region-A`/`dev-A` are placeholders. A single-workspace project has one target file, or keeps its targets in `databricks.yml`.

## What goes where

| Item | Location | Notes |
|---|---|---|
| Bundle name, `include` globs | `databricks.yml` | Kept minimal; globs pick up new files automatically |
| Variable declarations | `variables.yml` | Description and type only. Values live in target files, so every target must set every variable. Lint rule L006 catches gaps. |
| Targets | `targets/<region>.yml` | One file per workspace or region, holding that region's environments, variable values, host or profile, mode, presets and permissions |
| Jobs and pipelines for a data workload | `workloads/data/<workload>/resources/<name>.job.yml`, `<name>.pipeline.yml` | One folder per workload |
| Code for a data workload | `workloads/data/<workload>/src/` | Referenced from resources as `../src/...` |
| Shared feature tables | `workloads/features/<domain>/` | Same `resources/` + `src/` split as data workloads (confirm with the user) |
| Registered model, training/deploy/inference jobs, serving endpoint | `workloads/models/<model>/resources/` | For example `<model>.model.yml`, `train.job.yml`, `inference.job.yml`, `<model>.endpoint.yml` |
| Training, validation and inference code | `workloads/models/<model>/src/` | |
| Catalogs, schemas, grants (including ML schemas) | `schemas/<domain>.yml` | The single place a schema is defined. Other resources reference it with `${resources.schemas.<key>...}`. |
| Volumes | `volumes/<name>.yml` | |
| Shared code and ML utilities | `libraries/<package>/` | Built as wheels through the bundle's `artifacts` block |

`scripts/scaffold_bundle.py` renders this layout from interview answers, using the templates in `starter/`.

## Matching `include` globs

```yaml
bundle:
  name: <bundle-name>

include:
  - variables.yml
  - targets/*.yml
  - workloads/**/resources/*.yml
  - schemas/*.yml
  - volumes/*.yml
```

If features use a different structure, add a glob for it. A resource file that no glob matches is never deployed and causes no error. `lint_bundle.py` flags it as L012.

## Why this shape
- **Each workload is self-contained,** so changes to one workload stay in its own folder.
- **Region differences sit in one file per region.** Reviewing what differs between regions means reading the target files, not every resource.
- **Data and ML workloads share a pattern** (`resources/` + `src/`), so the same review and coverage checks apply to both.
- **Schemas are defined once** and referenced, so catalog and schema names per target live in one place.

## Trade-offs to mention when offering it
- One bundle for every region means one deploy pipeline. A mistake in a shared file (`variables.yml`, a target file) affects every workload.
- Very large organizations, or teams with separate release cycles, may prefer one bundle per domain or per team, with the same internal layout.
