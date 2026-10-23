#!/usr/bin/env python3
"""Render a new bundle from references/starter/ templates and interview answers.

The layout follows references/bundle-layout.md. The answers format is documented
in references/starter/answers.example.yml.

Examples:
  python3 scaffold_bundle.py --answers answers.yml --out ./bundle --dry-run
  cat answers.yml | python3 scaffold_bundle.py --answers - --out ./bundle

Writes nothing with --dry-run. Refuses to write into a folder that already
contains a databricks.yml, or that is not empty, unless --allow-non-empty is set
(existing files are never overwritten either way).

Exit codes: 0 = ok, 2 = invalid answers or refused.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundle_loader import yaml  # noqa: E402

STARTER = Path(__file__).resolve().parent.parent / "references" / "starter"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
KINDS = ("development", "test", "production")
SHARED_ROOT = "/Workspace/Shared/.bundle/${bundle.name}/${bundle.target}"


class AnswersError(Exception):
    pass


def render(template: str, values: Dict[str, str]) -> str:
    def sub(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            raise AnswersError(f"template placeholder {{{{{key}}}}} has no value")
        return values[key]
    return PLACEHOLDER_RE.sub(sub, template)


def read_template(name: str) -> str:
    return (STARTER / name).read_text(encoding="utf-8")


def validate(answers: dict) -> None:
    def need(cond: bool, message: str) -> None:
        if not cond:
            raise AnswersError(message)

    need(isinstance(answers, dict), "answers must be a mapping")
    need(NAME_RE.match(str(answers.get("bundle_name", ""))) is not None,
         "bundle_name is required (letters, digits, _ and -)")
    regions = answers.get("regions") or []
    envs = answers.get("environments") or []
    need(len(regions) >= 1, "at least one entry in regions is required")
    need(len(envs) >= 1, "at least one entry in environments is required")
    for region in regions:
        need(NAME_RE.match(str(region.get("name", ""))) is not None, f"invalid region name: {region!r}")
        need(not (region.get("profile") and region.get("host")),
             f"region {region['name']}: set profile or host, not both")
    for env in envs:
        need(NAME_RE.match(str(env.get("name", ""))) is not None, f"invalid environment name: {env!r}")
        need(env.get("kind") in KINDS, f"environment {env.get('name')}: kind must be one of {', '.join(KINDS)}")
        need(bool(env.get("catalog")), f"environment {env.get('name')}: catalog is required")
    pattern = answers.get("target_pattern") or "{env}-{region}"
    need("{env}" in pattern, "target_pattern must contain {env}")
    need(len(regions) == 1 or "{region}" in pattern,
         "target_pattern must contain {region} when there is more than one region")
    workload = answers.get("example_workload")
    need(workload is None or NAME_RE.match(str(workload)) is not None, "invalid example_workload name")
    ci = answers.get("ci") or "none"
    need(ci in ("none", "github-actions"), "ci must be none or github-actions")
    need(ci == "none" or bool(answers.get("cli_version")), "cli_version is required when ci is set")


def plan_files(answers: dict) -> Tuple[Dict[str, str], List[str]]:
    """Return ({relative path: content}, warnings)."""
    validate(answers)
    warnings: List[str] = []
    pattern = answers.get("target_pattern") or "{env}-{region}"
    regions = answers["regions"]
    envs = answers["environments"]
    overrides = answers.get("catalog_overrides") or {}

    files: Dict[str, str] = {
        "databricks.yml": render(read_template("databricks.yml.tmpl"), {"bundle_name": answers["bundle_name"]}),
        "variables.yml": read_template("variables.yml.tmpl"),
    }

    default_env = next((e for e in envs if e["kind"] == "development"),
                       next((e for e in envs if e["kind"] != "production"), None))
    all_targets: List[Tuple[str, str]] = []  # (target, kind)
    for r_index, region in enumerate(regions):
        blocks = []
        for env in envs:
            target = pattern.replace("{env}", env["name"]).replace("{region}", region["name"])
            if not NAME_RE.match(target):
                raise AnswersError(f"target name {target!r} built from target_pattern is invalid")
            if any(t == target for t, _ in all_targets):
                raise AnswersError(f"duplicate target name {target!r}; adjust target_pattern")
            all_targets.append((target, env["kind"]))
            workspace_lines = []
            if region.get("profile"):
                workspace_lines.append(f"      profile: {region['profile']}")
            if region.get("host"):
                workspace_lines.append(f"      host: {region['host']}")
            if env["kind"] != "development":
                workspace_lines.append(f"      root_path: {SHARED_ROOT}")
            workspace_block = ("\n    workspace:\n" + "\n".join(workspace_lines)) if workspace_lines else ""
            is_default = r_index == 0 and default_env is not None and env is default_env
            catalog = (overrides.get(region["name"]) or {}).get(env["name"], env["catalog"])
            blocks.append(render(read_template(f"targets/{env['kind']}.yml.tmpl"), {
                "target": target,
                "default_line": "\n    default: true" if is_default else "",
                "workspace_block": workspace_block,
                "catalog": str(catalog),
            }))
        files[f"targets/region-{region['name']}.yml"] = "targets:\n" + "".join(blocks)

    workload = answers.get("example_workload")
    if workload:
        values = {"workload": workload}
        base = f"workloads/data/{workload}"
        files[f"schemas/{workload}.yml"] = render(read_template("workload/schema.yml.tmpl"), values)
        files[f"{base}/resources/{workload}.job.yml"] = render(read_template("workload/job.yml.tmpl"), values)
        files[f"{base}/resources/{workload}.pipeline.yml"] = render(
            read_template("workload/pipeline.yml.tmpl"), values)
        files[f"{base}/src/ingest.py"] = render(read_template("workload/ingest.py.tmpl"), values)
        files[f"{base}/src/transform.sql"] = render(read_template("workload/transform.sql.tmpl"), values)
    else:
        files["schemas/.gitkeep"] = ""
        files["workloads/data/.gitkeep"] = ""
    files["volumes/.gitkeep"] = ""
    files["libraries/.gitkeep"] = ""

    if (answers.get("ci") or "none") == "github-actions":
        nonprod = [t for t, kind in all_targets if kind != "production"]
        prod = [t for t, kind in all_targets if kind == "production"]
        if not prod:
            warnings.append("no production environment, so the CI deploy job has no targets")
        if any(r.get("profile") for r in regions):
            warnings.append("targets set workspace.profile, which CI runners usually lack; "
                            "prefer host, or no workspace setting, when deploying from CI")
        files[".github/workflows/bundle.yml"] = render(read_template("ci/github-actions.yml.tmpl"), {
            "nonprod_targets": ", ".join(nonprod),
            "prod_targets": ", ".join(prod),
            "cli_version": str(answers["cli_version"]).lstrip("v"),
        })

    if not any(kind == "production" for _, kind in all_targets):
        warnings.append("no environment has kind: production")
    return files, warnings


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers", required=True, help="answers YAML file, or - for stdin")
    parser.add_argument("--out", required=True, help="folder to create the bundle in")
    parser.add_argument("--dry-run", action="store_true", help="list the files without writing them")
    parser.add_argument("--allow-non-empty", action="store_true",
                        help="allow a non-empty folder (still never overwrites files)")
    args = parser.parse_args(argv)

    try:
        text = sys.stdin.read() if args.answers == "-" else Path(args.answers).read_text(encoding="utf-8")
        files, warnings = plan_files(yaml.safe_load(text) or {})
    except (AnswersError, OSError, yaml.YAMLError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    out = Path(args.out)
    if (out / "databricks.yml").exists():
        sys.stderr.write(f"error: {out} already contains a bundle. To add to it, use the author agent; "
                         "to restructure it, run the scout then the author; "
                         "or pass an empty --out folder for a new bundle\n")
        return 2
    if out.exists() and any(out.iterdir()) and not args.allow_non_empty:
        sys.stderr.write(f"error: {out} is not empty (use --allow-non-empty to add files next to existing ones)\n")
        return 2
    clashes = [p for p in files if (out / p).exists()]
    if clashes:
        sys.stderr.write(f"error: would overwrite existing files: {', '.join(clashes)}\n")
        return 2

    for warning in warnings:
        sys.stderr.write(f"warning: {warning}\n")
    verb = "would create" if args.dry_run else "created"
    for rel_path, content in sorted(files.items()):
        if not args.dry_run:
            target = out / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        print(f"{verb} {rel_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
