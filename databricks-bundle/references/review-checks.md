# Review checks

Generic checks for any bundle. Script IDs (`L0xx`) mean that `scripts/lint_bundle.py` finds the issue automatically. The rest need reading. Any check can be turned off in the profile. A pattern the profile records as the project's choice is not a finding.

## 1. Deployment coverage
| Check | How | Default severity |
|---|---|---|
| A resource is missing from a target where it should exist | `target_coverage.py` | blocker |
| A definition (for example an anchor holder) is never attached as a resource | `target_coverage.py` (`unattached`) | blocker if it was meant to deploy |
| A relative source path (notebook, file, python file) doesn't exist, resolved from the YAML file that defines it | L011 | blocker |
| A YAML file with `resources:` or `targets:` that no `include` glob matches, so it never deploys | L012 | blocker |
| Placement differs from `bundle-layout.md` (only if the profile says the project follows it): a resource outside its workload folder, or variable values in `variables.yml` | read | style |
| A `${resources.<type>.<key>...}` reference points to a resource that does not exist in some target | read references and compare with coverage | blocker |
| A target defined in YAML is never deployed by CI, or CI deploys a target that doesn't exist | compare targets with CI files | risk |
| `default: true` is on a production target, or on more than one target | read targets | risk |

## 2. Targets and environments
| Check | How | Default severity |
|---|---|---|
| A production target is not `mode: production` | L004 | risk |
| A production `root_path` depends on who deploys (`current_user`) | L005 | risk |
| Non-production, non-development targets have jobs with a literal `UNPAUSED` schedule or trigger | L008 | risk |
| The workspace host is not pinned per target and nothing else (profile, CI env) guarantees the right host | read targets and CI | risk |
| Production deploys run without an approval gate or protected environment | read CI | risk |

## 3. Variables
| Check | How | Default severity |
|---|---|---|
| A variable with no default has no value in some target | L006 | risk (CI may pass it with `--var` or `BUNDLE_VAR_*`; check before calling it a blocker) |
| A variable value is a JSON string the bundle can't validate | L007 | style |
| A declared variable is never used, or a used variable is never declared | grep `${var.` | risk if used and undeclared, style if unused |

## 4. Literals that should vary per target
| Check | How | Default severity |
|---|---|---|
| A UUID literal in a resource definition (`run_as`, permissions, grants, IDs) | L001 | risk |
| A workspace URL literal in a resource definition | L002 | risk |
| A literal catalog in a resource of a multi-target bundle, so every target writes to the same catalog | L003 | style (it may be intended; ask) |
| A path under one person's or principal's home folder (`/Users/<name>/`, `/Workspace/Users/<name>/`) | L009 | risk |

## 5. Identity and permissions
- Jobs and pipelines in production run as a service principal, not as whoever deployed them, unless the project chose otherwise.
- Permissions and grants are set for every target where the resource exists, not just one.
- Nobody is granted more in non-production than in production without a reason.

## 6. Artifacts and libraries
- Built artifacts are referenced in a way that resolves per target and per deployer, rather than through a fixed personal path.
- Artifact versioning lets you tell which code a run used.
- Dependency versions are pinned.

## 7. CI and CLI
| Check | How | Default severity |
|---|---|---|
| The Databricks CLI is unpinned in CI, or different files pin different versions | L010 | risk |
| `bundle validate` runs for every target CI deploys | read CI | risk |
| Deploy uses `--auto-approve` on production without an approval gate | read CI | risk |
| `bundle.databricks_cli_version` is not set, so local and CI CLIs may differ | read `databricks.yml` | style |

## 8. Data isolation
- Non-production targets can't write to production catalogs or schemas. Look for literals or variables that resolve to production names in non-production targets.
- Overrides marked as temporary are listed, with where they are.

## 9. Freshness of facts
- Fields or features the current docs mark as deprecated or renamed (see `docs-lookup.md`). Check against live docs; don't rely on memory.
