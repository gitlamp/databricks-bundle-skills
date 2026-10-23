#!/usr/bin/env python3
"""Generic static checks for a Databricks bundle (no Databricks CLI needed).

Rules (see references/review-checks.md):
  L001 risk   UUID literal in a resource definition
  L002 risk   workspace URL literal in a resource definition
  L003 style  literal catalog in a resource of a multi-target bundle
  L004 risk   production target without `mode: production`
  L005 risk   production root_path depends on the deploying user
  L006 risk   variable without default has no value in some target
  L007 style  variable value is a JSON string
  L008 risk   job schedule/trigger can run in a non-prod, non-development target
  L009 risk   path inside one user's or principal's home folder
  L010 risk   Databricks CLI unpinned or pinned inconsistently in CI
  L011 blocker  relative source path (notebook, file, python file) does not exist
  L012 blocker  YAML file with resources/targets that no include glob matches

Exit codes: 0 = no blocker/risk findings, 1 = blocker/risk findings, 2 = error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundle_loader import (  # noqa: E402
    Bundle, BundleError, deep_merge, find_line, load_bundle, rel, resource_sites,
    resources_for_target, walk_strings, yaml,
)

SEVERITY = {
    "L001": "risk", "L002": "risk", "L003": "style", "L004": "risk", "L005": "risk",
    "L006": "risk", "L007": "style", "L008": "risk", "L009": "risk", "L010": "risk",
    "L011": "blocker", "L012": "blocker",
}
SKIP_DIRS = {"node_modules", "__pycache__", "dist", "build"}
SOURCE_KEYS = {"notebook_path", "python_file", "path"}
NOTEBOOK_EXTENSIONS = ("", ".py", ".ipynb", ".sql", ".scala", ".r", ".R")

UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
HOST_RE = re.compile(r"https?://[^\s\"'/]*(?:cloud\.databricks\.com|azuredatabricks\.net|gcp\.databricks\.com)")
HOME_RE = re.compile(r"/Users/(?!\$\{)([^/\s\"']+)")
PROD_NAME_RE = re.compile(r"(^|[-_.])prod(uction)?($|[-_.])", re.IGNORECASE)
# Only catalogs: schema names are commonly identical across targets, while a catalog
# that never changes usually means every target writes to the same place.
LOCATION_FIELDS = {
    "pipelines": ("catalog",),
    "schemas": ("catalog_name",),
    "volumes": ("catalog_name",),
    "registered_models": ("catalog_name",),
}
CI_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml",
            "azure-pipelines*.yml", "Makefile")


class Linter:
    def __init__(self, bundle: Bundle, prod_targets: Optional[Set[str]], ci_root: Path):
        self.bundle = bundle
        self.ci_root = ci_root
        self.findings: List[dict] = []
        self._seen: Set[tuple] = set()
        targets = bundle.targets
        if prod_targets is None:
            prod_targets = {t for t in targets
                            if PROD_NAME_RE.search(t) or bundle.target(t).get("mode") == "production"}
        self.prod = prod_targets

    def add(self, rule: str, path: Optional[Path], line: int, message: str, target: Optional[str] = None,
            resource: Optional[str] = None) -> None:
        key = (rule, str(path), line, message)
        if key in self._seen:
            return
        self._seen.add(key)
        self.findings.append({
            "rule": rule, "severity": SEVERITY[rule], "file": rel(self.bundle, path) if path else "-",
            "line": line, "target": target, "resource": resource, "message": message,
        })

    # Resource-body rules -------------------------------------------------
    def check_resource_literals(self) -> None:
        multi_target = len(self.bundle.targets) > 1
        for path, target, rtype, key, body in resource_sites(self.bundle):
            rid = f"{rtype}.{key}"
            for field_path, value in walk_strings(body):
                self._check_source_path(path, target, rid, key, field_path, value)
                home = HOME_RE.search(value)
                if home and ("@" in home.group(1) or UUID_RE.fullmatch(home.group(1))):
                    self.add("L009", path, find_line(path, home.group(0), key),
                             f"{rid}.{field_path} points into a personal home folder ({home.group(0)})",
                             target, rid)
                    continue
                if UUID_RE.search(value) and "${" not in value:
                    self.add("L001", path, find_line(path, UUID_RE.search(value).group(0), key),
                             f"{rid}.{field_path} contains a literal UUID; use a variable or lookup",
                             target, rid)
                if HOST_RE.search(value):
                    self.add("L002", path, find_line(path, HOST_RE.search(value).group(0), key),
                             f"{rid}.{field_path} contains a workspace URL", target, rid)
            if multi_target and isinstance(body, dict):
                for field_name in LOCATION_FIELDS.get(rtype, ()):
                    value = body.get(field_name)
                    if isinstance(value, str) and "${" not in value:
                        self.add("L003", path, find_line(path, f"{field_name}:", key),
                                 f"{rid}.{field_name} is the literal {value!r} in every target it is attached to",
                                 target, rid)

    def _check_source_path(self, path: Path, target: Optional[str], rid: str, key: str,
                           field_path: str, value: str) -> None:
        """Relative paths are resolved from the YAML file that defines them."""
        leaf = re.split(r"[.\[]", field_path)[-1]
        if leaf not in SOURCE_KEYS or not value.startswith(("./", "../")):
            return
        if "${" in value or any(ch in value for ch in "*?["):
            return
        base = (path.parent / value).resolve()
        if any(Path(str(base) + ext).exists() for ext in NOTEBOOK_EXTENSIONS):
            return
        self.add("L011", path, find_line(path, value, key),
                 f"{rid}.{field_path} points to {value}, which does not exist", target, rid)

    # Target rules --------------------------------------------------------
    def check_targets(self) -> None:
        root_file = self.bundle.files[0]
        for target in self.bundle.targets:
            tdef = self.bundle.target(target)
            tfile = self._target_file(target)
            if target in self.prod and tdef.get("mode") != "production":
                self.add("L004", tfile, find_line(tfile, f"{target}:"),
                         f"production target {target} is not mode: production", target)
            workspace = deep_merge(self.bundle.config.get("workspace") or {}, tdef.get("workspace") or {})
            root_path = workspace.get("root_path")
            if target in self.prod and isinstance(root_path, str) and (
                    "current_user" in root_path or HOME_RE.search(root_path)):
                where = tfile if "root_path" in str(tdef.get("workspace") or {}) else root_file
                self.add("L005", where, find_line(where, "root_path"),
                         f"production target {target} root_path depends on the deploying user: {root_path}",
                         target)
            if target not in self.prod and tdef.get("mode") != "development":
                self._check_schedules(target, tdef)

    def _check_schedules(self, target: str, tdef: dict) -> None:
        if (tdef.get("presets") or {}).get("trigger_pause_status") == "PAUSED":
            return
        jobs = resources_for_target(self.bundle, target).get("jobs") or {}
        for key, job in jobs.items():
            if not isinstance(job, dict):
                continue
            for trigger in ("schedule", "trigger", "continuous"):
                block = job.get(trigger)
                if not isinstance(block, dict):
                    continue
                status = block.get("pause_status")
                if status is None or status == "UNPAUSED":
                    path = self.bundle.origins.get(("jobs", key, None)) or self.bundle.origins.get(
                        ("jobs", key, target))
                    state = "unset (defaults to UNPAUSED)" if status is None else "UNPAUSED"
                    self.add("L008", path, find_line(path, f"{trigger}:", key) if path else 0,
                             f"jobs.{key} {trigger} pause_status is {state} in non-prod target {target}, "
                             f"which is not in development mode", target, f"jobs.{key}")

    def _target_file(self, target: str) -> Path:
        for path, doc in self.bundle.docs.items():
            if target in (doc.get("targets") or doc.get("environments") or {}):
                return path
        return self.bundle.files[0]

    # Variable rules ------------------------------------------------------
    def check_variables(self) -> None:
        declared: Dict[str, dict] = self.bundle.config.get("variables") or {}
        decl_file = next((p for p, d in self.bundle.docs.items() if d.get("variables")), self.bundle.files[0])
        for name, decl in declared.items():
            decl = decl if isinstance(decl, dict) else {"default": decl}
            has_default = "default" in decl or "lookup" in decl
            missing = []
            for target in self.bundle.targets:
                values = self.bundle.target(target).get("variables") or {}
                if name in values:
                    self._check_json_string(name, values[name], self._target_file(target), target)
                elif not has_default:
                    missing.append(target)
            if missing:
                self.add("L006", decl_file, find_line(decl_file, f"{name}:"),
                         f"variable {name} has no default and no value in: {', '.join(missing)} "
                         f"(fine only if CI passes --var or BUNDLE_VAR_{name})")
            if "default" in decl:
                self._check_json_string(name, decl["default"], decl_file, None)

    def _check_json_string(self, name: str, value, path: Path, target: Optional[str]) -> None:
        if isinstance(value, dict) and "default" in value:
            value = value["default"]
        if not isinstance(value, str) or not value.strip()[:1] in ("{", "["):
            return
        try:
            parsed = json.loads(value)
        except ValueError:
            return
        if isinstance(parsed, (dict, list)):
            self.add("L007", path, find_line(path, f"{name}:"),
                     f"variable {name} holds JSON in a string; a complex variable can be validated", target)

    # CI rules --------------------------------------------------------------
    def check_ci(self) -> None:
        versions: Dict[str, List[str]] = {}
        unpinned: List[tuple] = []
        for pattern in CI_GLOBS:
            for path in sorted(self.ci_root.glob(pattern)):
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                for index, line in enumerate(lines):
                    action = re.search(r"databricks/setup-cli@([\w.\-]+)", line)
                    script = re.search(r"databricks/setup-cli/([\w.\-]+)/install\.sh", line)
                    env_pin = re.search(r"DATABRICKS_CLI_VERSION\s*[:=]\s*[\"']?v?([\d.]+)", line)
                    if action:
                        ref = action.group(1)
                        window = "\n".join(lines[index + 1:index + 5])
                        explicit = re.search(r"^\s*version:\s*[\"']?v?([\d.]+)", window, re.MULTILINE)
                        if explicit:
                            versions.setdefault(explicit.group(1), []).append(f"{path.name}:{index + 1}")
                        elif re.fullmatch(r"v?\d+(\.\d+)*", ref):
                            versions.setdefault(ref.lstrip("v"), []).append(f"{path.name}:{index + 1}")
                        else:
                            unpinned.append((path, index + 1, f"setup-cli@{ref}"))
                    elif script:
                        ref = script.group(1)
                        if re.fullmatch(r"v?\d+(\.\d+)*", ref):
                            versions.setdefault(ref.lstrip("v"), []).append(f"{path.name}:{index + 1}")
                        else:
                            unpinned.append((path, index + 1, f"install.sh from {ref}"))
                    elif env_pin:
                        versions.setdefault(env_pin.group(1), []).append(f"{path.name}:{index + 1}")
        for path, line, what in unpinned:
            self.add("L010", path, line, f"Databricks CLI installed without a pinned version ({what})")
        if len(versions) > 1:
            detail = "; ".join(f"{v} at {', '.join(locs)}" for v, locs in sorted(versions.items()))
            self.add("L010", None, 0, f"Databricks CLI pinned to different versions: {detail}")

    # Include rules -----------------------------------------------------------
    def check_unincluded(self) -> None:
        """YAML files that look like bundle config but are not matched by any include glob."""
        included = set(self.bundle.files)
        root = self.bundle.root
        for path in sorted(root.rglob("*")):
            if path.suffix not in (".yml", ".yaml") or path in included or not path.is_file():
                continue
            parts = path.relative_to(root).parts[:-1]
            if any(p.startswith(".") or p in SKIP_DIRS for p in parts):
                continue
            # A nested folder with its own databricks.yml is a separate bundle.
            if any((root.joinpath(*parts[:i]) / name).is_file()
                   for i in range(1, len(parts) + 1) for name in ("databricks.yml", "databricks.yaml")):
                continue
            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (yaml.YAMLError, OSError, UnicodeDecodeError):
                continue
            if isinstance(doc, dict) and ("resources" in doc or "targets" in doc):
                key = "resources" if "resources" in doc else "targets"
                self.add("L012", path, find_line(path, f"{key}:"),
                         f"{rel(self.bundle, path)} defines {key} but no include glob in "
                         f"{self.bundle.files[0].name} matches it, so it is never deployed")

    def run(self, disabled: Set[str]) -> List[dict]:
        self.check_unincluded()
        self.check_resource_literals()
        self.check_targets()
        self.check_variables()
        self.check_ci()
        return [f for f in self.findings if f["rule"] not in disabled]


def find_ci_root(bundle_root: Path) -> Path:
    for candidate in [bundle_root, *bundle_root.parents]:
        if (candidate / ".git").exists() or (candidate / ".github").is_dir():
            return candidate
    return bundle_root


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle", default=".", help="bundle root (folder with databricks.yml)")
    parser.add_argument("--prod-targets", help="comma-separated production targets "
                                               "(default: mode: production or 'prod' in the name)")
    parser.add_argument("--disable", default="", help="comma-separated rule IDs to skip")
    parser.add_argument("--ci-root", help="folder to scan for CI files (default: nearest repo root)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    try:
        bundle = load_bundle(args.bundle)
    except (BundleError, OSError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    prod = set(args.prod_targets.split(",")) if args.prod_targets else None
    ci_root = Path(args.ci_root).resolve() if args.ci_root else find_ci_root(bundle.root)
    disabled = {r.strip() for r in args.disable.split(",") if r.strip()}
    findings = sorted(Linter(bundle, prod, ci_root).run(disabled),
                      key=lambda f: (["blocker", "risk", "style"].index(f["severity"]),
                                     f["file"], f["line"], f["rule"]))

    if args.format == "json":
        print(json.dumps(findings, indent=2))
    elif not findings:
        print("No findings.")
    else:
        for f in findings:
            where = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
            print(f"{f['rule']} {f['severity']:5} {where}  {f['message']}")

    return 1 if any(f["severity"] in ("blocker", "risk") for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
