# Where to check facts

Bundle fields, resource types and CLI behaviour change often. For anything field-level, fetch the current page instead of relying on memory. If the docs and the project's files disagree, tell the user and let them decide. Don't silently "correct" the project.

The docs are published per cloud. Replace `aws` with `azure` or `gcp` in the URLs below to match the user's cloud. If a URL has moved, search docs.databricks.com for the topic name.

| Question | Page |
|---|---|
| What bundles are, and the current product name | https://docs.databricks.com/aws/en/dev-tools/bundles/ |
| Top-level keys (`bundle`, `include`, `targets`, `variables`, `artifacts`, `sync`, `presets`, ...) | https://docs.databricks.com/aws/en/dev-tools/bundles/settings |
| Full configuration reference (every field) | https://docs.databricks.com/aws/en/dev-tools/bundles/reference |
| Resource types and their fields | https://docs.databricks.com/aws/en/dev-tools/bundles/resources |
| Variables, complex variables and lookups | https://docs.databricks.com/aws/en/dev-tools/bundles/variables |
| `mode: development` / `production`, and presets | https://docs.databricks.com/aws/en/dev-tools/bundles/deployment-modes |
| `run_as` | https://docs.databricks.com/aws/en/dev-tools/bundles/run-as |
| Permissions | https://docs.databricks.com/aws/en/dev-tools/bundles/permissions |
| Example configurations | https://docs.databricks.com/aws/en/dev-tools/bundles/examples |
| Deployment engine (direct vs. Terraform) and migration | search "bundles direct deployment engine" |
| CLI `bundle` commands (`validate`, `summary`, `deploy`, `run`, `destroy`) | https://docs.databricks.com/aws/en/dev-tools/cli/bundle-commands |
| Declarative pipelines: SQL and Python syntax, expectations, CDC flows | search "Lakeflow Declarative Pipelines" |
| Machine-readable schema | `databricks bundle schema` (if the CLI is available) |

When you rely on a page, include its link in the report so the user can check it.
