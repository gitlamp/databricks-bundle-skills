"""Load a Databricks bundle from YAML files without the Databricks CLI.

Resolves `include` globs, merges included files, and computes the resources
each target ends up with (top-level `resources` deep-merged with
`targets.<name>.resources`). YAML anchors and merge keys are handled by PyYAML
within each file, which matches how the CLI reads them.

This is an approximation of what the CLI does. For exact results, feed
`databricks bundle validate -o json` output to the scripts instead.
"""
from __future__ import annotations

import copy
import glob
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("PyYAML is required: pip install pyyaml\n")
    sys.exit(2)

ROOT_FILE_NAMES = ("databricks.yml", "databricks.yaml", "bundle.yml", "bundle.yaml")

# Top-level keys the bundle schema knows. Anything else at the top of a file
# is treated as a scratch definition (for example an anchor holder).
KNOWN_TOP_LEVEL_KEYS = {
    "bundle", "include", "workspace", "artifacts", "variables", "resources",
    "targets", "environments", "sync", "permissions", "run_as", "presets",
    "experimental", "scripts", "python",
}


class BundleError(Exception):
    pass


@dataclass
class Bundle:
    root: Path
    files: List[Path]
    docs: Dict[Path, dict]
    config: dict
    # (resource_type, key, target_or_None) -> file that defines it
    origins: Dict[Tuple[str, str, Optional[str]], Path] = field(default_factory=dict)

    @property
    def targets(self) -> List[str]:
        return list((self.config.get("targets") or {}).keys())

    def target(self, name: str) -> dict:
        return (self.config.get("targets") or {}).get(name) or {}


def find_root_file(root: Path) -> Path:
    for name in ROOT_FILE_NAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    raise BundleError(f"no databricks.yml found in {root}")


def read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise BundleError(f"{path}: top level is not a mapping")
    return data


def deep_merge(base: Any, override: Any) -> Any:
    """Merge override into a copy of base. Mappings merge, everything else is replaced."""
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = deep_merge(base[key], value) if key in base else copy.deepcopy(value)
        return merged
    return copy.deepcopy(override)


def load_bundle(root: str | os.PathLike) -> Bundle:
    root_path = Path(root).resolve()
    root_file = find_root_file(root_path)
    root_doc = read_yaml(root_file)

    files = [root_file]
    for pattern in root_doc.get("include") or []:
        matches = sorted(glob.glob(str(root_path / pattern), recursive=True))
        for match in matches:
            path = Path(match).resolve()
            if path.is_file() and path not in files:
                files.append(path)

    docs: Dict[Path, dict] = {}
    config: dict = {}
    origins: Dict[Tuple[str, str, Optional[str]], Path] = {}
    for path in files:
        doc = read_yaml(path)
        docs[path] = doc
        # Legacy name for targets.
        if "environments" in doc and "targets" not in doc:
            doc = dict(doc)
            doc["targets"] = doc.pop("environments")
        for rtype, items in (doc.get("resources") or {}).items():
            for key in (items or {}):
                origins.setdefault((rtype, key, None), path)
        for tname, tdef in (doc.get("targets") or {}).items():
            for rtype, items in ((tdef or {}).get("resources") or {}).items():
                for key in (items or {}):
                    origins.setdefault((rtype, key, tname), path)
        config = deep_merge(config, {k: v for k, v in doc.items() if k in KNOWN_TOP_LEVEL_KEYS})

    return Bundle(root=root_path, files=files, docs=docs, config=config, origins=origins)


def resources_for_target(bundle: Bundle, target: str) -> Dict[str, Dict[str, dict]]:
    """Effective resources for one target: top-level merged with the target's own."""
    top = bundle.config.get("resources") or {}
    own = bundle.target(target).get("resources") or {}
    merged = deep_merge(top, own)
    return {rtype: dict(items or {}) for rtype, items in merged.items()}


def resource_ids(resources: Dict[str, Dict[str, dict]]) -> List[str]:
    return sorted(f"{rtype}.{key}" for rtype, items in resources.items() for key in items)


def origin_of(bundle: Bundle, rtype: str, key: str) -> Optional[Path]:
    if (rtype, key, None) in bundle.origins:
        return bundle.origins[(rtype, key, None)]
    for (t, k, _), path in bundle.origins.items():
        if t == rtype and k == key:
            return path
    return None


def resource_sites(bundle: Bundle) -> Iterator[Tuple[Path, Optional[str], str, str, Any]]:
    """Every place a resource body is written, per file: (file, target, type, key, body)."""
    for path, doc in bundle.docs.items():
        targets = doc.get("targets") or doc.get("environments") or {}
        for rtype, items in (doc.get("resources") or {}).items():
            for key, body in (items or {}).items():
                yield path, None, rtype, key, body
        for tname, tdef in targets.items():
            for rtype, items in ((tdef or {}).get("resources") or {}).items():
                for key, body in (items or {}).items():
                    yield path, tname, rtype, key, body


def unattached_definitions(bundle: Bundle) -> List[Tuple[Path, str]]:
    """Top-level scratch keys (for example anchor holders) that never become a resource."""
    used_keys = {key for (_, key, _) in bundle.origins}
    found = []
    for path, doc in bundle.docs.items():
        for key, value in doc.items():
            if key in KNOWN_TOP_LEVEL_KEYS or not isinstance(value, dict):
                continue
            if key not in used_keys:
                found.append((path, key))
    return found


def walk_strings(node: Any, path: str = "") -> Iterator[Tuple[str, str]]:
    """Yield (dotted_path, value) for every string leaf."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk_strings(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk_strings(value, f"{path}[{index}]")
    elif isinstance(node, str):
        yield path, node


def find_line(path: Path, needle: str, start_hint: str | None = None) -> int:
    """1-based line of the first occurrence of needle (after start_hint if given), else 1."""
    try:
        raw = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 1
    # Ignore comments so a needle mentioned in a comment doesn't win.
    lines = ["" if line.lstrip().startswith("#") else re.sub(r"\s+#.*$", "", line) for line in raw]
    begin = 0
    if start_hint:
        pattern = re.compile(rf"^\s*{re.escape(start_hint)}\s*:")
        for index, line in enumerate(lines):
            if pattern.search(line):
                begin = index
                break
    for index in range(begin, len(lines)):
        if needle in lines[index]:
            return index + 1
    for index, line in enumerate(lines):
        if needle in line:
            return index + 1
    return begin + 1 if start_hint else 1


def rel(bundle: Bundle, path: Optional[Path]) -> str:
    if path is None:
        return "?"
    try:
        return str(path.relative_to(bundle.root))
    except ValueError:
        return str(path)
