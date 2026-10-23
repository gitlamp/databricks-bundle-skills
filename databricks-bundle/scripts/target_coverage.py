#!/usr/bin/env python3
"""Show which bundle resources exist in which targets, and flag the gaps.

Works offline from the bundle's YAML (needs PyYAML, not the Databricks CLI).
Optionally reads saved `databricks bundle validate -o json -t <target>` output
for exact results.

Exit codes: 0 = no gaps, 1 = gaps or unattached definitions found, 2 = error.

Examples:
  python3 target_coverage.py --bundle .
  python3 target_coverage.py --bundle . --targets dev,prod --allow gaps.yml
  python3 target_coverage.py --bundle . --allow-entry jobs.export=dev-b,prod-b
  python3 target_coverage.py --bundle . --from-validate-json prod=prod.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundle_loader import (  # noqa: E402
    BundleError, load_bundle, origin_of, rel, resource_ids, resources_for_target,
    unattached_definitions, yaml,
)


def load_allow(path: str | None, entries: List[str]) -> Dict[str, Set[str]]:
    """Intended gaps: `<type>.<key>` -> targets it is intentionally absent from, or {"*"}.

    From a YAML file (`jobs.x: [dev, prod]` or `jobs.x: "*"`) and/or
    `--allow-entry jobs.x=dev,prod` flags.
    """
    allow: Dict[str, Set[str]] = {}
    if path:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        for rid, targets in data.items():
            allow.setdefault(rid, set()).update({"*"} if targets == "*" else set(targets or []))
    for entry in entries:
        if "=" not in entry:
            raise BundleError(f"--allow-entry expects <type>.<key>=<targets|*>, got {entry!r}")
        rid, targets = entry.split("=", 1)
        allow.setdefault(rid.strip(), set()).update(t.strip() for t in targets.split(",") if t.strip())
    return allow


def load_validate_json(specs: List[str]) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for spec in specs:
        if "=" not in spec:
            raise BundleError(f"--from-validate-json expects <target>=<file>, got {spec!r}")
        target, file = spec.split("=", 1)
        with open(file, encoding="utf-8") as fh:
            data = json.load(fh)
        result[target] = resource_ids(data.get("resources") or {})
    return result


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle", default=".", help="bundle root (folder with databricks.yml)")
    parser.add_argument("--targets", help="comma-separated targets to compare (default: all)")
    parser.add_argument("--allow", help="YAML allow-list of intended gaps")
    parser.add_argument("--allow-entry", action="append", default=[], metavar="TYPE.KEY=TARGETS",
                        help="intended gap without a file, e.g. jobs.export=dev-b,prod-b or jobs.export=* "
                             "(repeatable)")
    parser.add_argument("--from-validate-json", action="append", default=[], metavar="TARGET=FILE",
                        help="use saved `bundle validate -o json` output for a target (repeatable)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    try:
        bundle = load_bundle(args.bundle)
        from_json = load_validate_json(args.from_validate_json)
        allow = load_allow(args.allow, args.allow_entry)
    except (BundleError, OSError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    targets = args.targets.split(",") if args.targets else (bundle.targets or list(from_json))
    unknown = [t for t in targets if t not in bundle.targets and t not in from_json]
    if unknown:
        sys.stderr.write(f"error: unknown target(s): {', '.join(unknown)}\n")
        return 2

    presence: Dict[str, Set[str]] = {}
    for target in targets:
        ids = from_json[target] if target in from_json else resource_ids(resources_for_target(bundle, target))
        for rid in ids:
            presence.setdefault(rid, set()).add(target)

    gaps = []
    for rid in sorted(presence):
        missing = [t for t in targets if t not in presence[rid]]
        allowed = allow.get(rid, set())
        missing = [t for t in missing if "*" not in allowed and t not in allowed]
        if missing:
            rtype, key = rid.split(".", 1)
            gaps.append({
                "resource": rid,
                "present_in": [t for t in targets if t in presence[rid]],
                "missing_from": missing,
                "file": rel(bundle, origin_of(bundle, rtype, key)),
            })

    unattached = [{"file": rel(bundle, path), "key": key} for path, key in unattached_definitions(bundle)]

    if args.format == "json":
        print(json.dumps({
            "targets": targets,
            "resources": {rid: sorted(ts) for rid, ts in sorted(presence.items())},
            "gaps": gaps,
            "unattached": unattached,
        }, indent=2))
    else:
        width = max([len(r) for r in presence] + [8])
        print("resource".ljust(width), *targets, sep="  ")
        for rid in sorted(presence):
            cells = [("x" if t in presence[rid] else "-").center(len(t)) for t in targets]
            print(rid.ljust(width), *cells, sep="  ")
        print()
        if gaps:
            print(f"{len(gaps)} resource(s) missing from some targets:")
            for gap in gaps:
                print(f"  {gap['resource']} ({gap['file']}): missing from {', '.join(gap['missing_from'])}")
        if unattached:
            print(f"{len(unattached)} top-level definition(s) never attached as a resource:")
            for item in unattached:
                print(f"  {item['key']} ({item['file']})")
        if not gaps and not unattached:
            print("No gaps.")

    return 1 if gaps or unattached else 0


if __name__ == "__main__":
    sys.exit(main())
