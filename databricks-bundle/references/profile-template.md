# Project profile template

The scout drafts this, the user confirms it, and it is saved (with the user's OK) as `.databricks-bundle-profile.md` at the bundle root. Mark every value `observed`, `inferred`, `confirmed` (by the user) or `unknown`.

Never put hosts, tokens, service principal IDs, warehouse IDs or email addresses in this file. CLI profile names are fine. Write "set in target `<name>`" or "variable `<name>`" instead.

```markdown
# Databricks bundle profile
Last checked: <YYYY-MM-DD>
Bundle root: <path>
Bundle name: <name>

## Always ask the user
- Environments: <e.g. dev, test, prod>                                [confirmed]
- Workspaces / regions: <one, or a list with what differs between them> [confirmed]
- Production targets: <list>                                          [confirmed]
- Auth per workspace: <CLI profile name / env vars in CI / OAuth M2M>  [confirmed]
- Cross-workspace data: <none, or how and where it is managed> [confirmed]
- Table and naming standards: <link or summary, or "none">            [confirmed]

## Targets
| Target | Env | Workspace | Mode | Default | Host source | Notes |
|---|---|---|---|---|---|---|
| | | | | | profile / env var / in YAML | |

Target naming pattern: <pattern, or "no single pattern">

## Layout
- Follows references/bundle-layout.md: <yes / partly (list differences) / no, own structure>
- Resource layout: <top-level resources / per-target attachment / anchors / mixed>
- Where resources live: <glob(s)>
- Where source code lives relative to resources: <path pattern>
- Variables declared in: <file>; values set in: <files>

## Conventions (facts, not advice)
- Catalog / schema naming: <how they are chosen per target>
- Compute: <serverless / job clusters / shared clusters>
- Libraries and artifacts: <how built, where referenced from>
- Identity: <run_as approach; who deploys in CI vs locally>
- Schedules and pausing: <how non-prod avoids running on schedule>
- Notifications: <per target?>
- Tags and naming: <required tags, key naming>

## Review settings
- Intended target gaps (resources deliberately absent from some targets):
  ```yaml
  # used as --allow for target_coverage.py
  jobs.<key>: [<target>, ...]
  ```
- Disabled lint rules: <ids, each with the reason>
- Extra project checks: <anything the team always wants reviewed>

## CI / tooling
- Validate runs on: <event, targets>
- Deploy runs on: <event, targets>
- CLI install and version pin: <where, which version>
```
