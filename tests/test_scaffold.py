"""Render new bundles from the starter templates and check that both scripts come back clean.

No Databricks CLI or workspace is used.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "databricks-bundle" / "scripts"
STARTER = REPO / "databricks-bundle" / "references" / "starter"

VARIANTS = {
    "example-answers": yaml.safe_load((STARTER / "answers.example.yml").read_text()),
    "single-workspace-with-ci": {
        "bundle_name": "solo",
        "target_pattern": "{env}",
        "regions": [{"name": "main"}],
        "environments": [
            {"name": "dev", "kind": "development", "catalog": "dev_cat"},
            {"name": "staging", "kind": "test", "catalog": "stg_cat"},
            {"name": "prod", "kind": "production", "catalog": "prod_cat"},
        ],
        "example_workload": "orders",
        "ci": "github-actions",
        "cli_version": "1.20.0",
    },
    "three-regions-no-example": {
        "bundle_name": "fleet",
        "target_pattern": "{region}_{env}",
        "regions": [{"name": "a", "host": "https://example.invalid"}, {"name": "b"}, {"name": "c"}],
        "environments": [
            {"name": "dev", "kind": "development", "catalog": "dev"},
            {"name": "prod", "kind": "production", "catalog": "prod"},
        ],
        "catalog_overrides": {"c": {"prod": "prod_c"}},
        "example_workload": None,
    },
}


def scaffold(answers, out, *extra):
    return subprocess.run([sys.executable, str(SCRIPTS / "scaffold_bundle.py"), "--answers", "-",
                           "--out", str(out), *extra],
                          input=yaml.safe_dump(answers), capture_output=True, text=True)


def run_json(script, *args):
    proc = subprocess.run([sys.executable, str(SCRIPTS / script), *args, "--format", "json"],
                          capture_output=True, text=True)
    return proc.returncode, json.loads(proc.stdout)


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_fresh_scaffold_is_clean(name, tmp_path):
    out = tmp_path / "bundle"
    proc = scaffold(VARIANTS[name], out)
    assert proc.returncode == 0, proc.stderr

    code, coverage = run_json("target_coverage.py", "--bundle", str(out))
    assert code == 0 and coverage["gaps"] == [] and coverage["unattached"] == []

    code, findings = run_json("lint_bundle.py", "--bundle", str(out), "--ci-root", str(out))
    assert findings == [] and code == 0

    for path in out.rglob("*"):
        if path.is_file():
            assert not re.search(r"\{\{\w+\}\}", path.read_text()), f"unrendered placeholder in {path}"


def test_targets_follow_answers(tmp_path):
    out = tmp_path / "bundle"
    scaffold(VARIANTS["three-regions-no-example"], out)
    _, coverage = run_json("target_coverage.py", "--bundle", str(out))
    assert coverage["targets"] == ["a_dev", "a_prod", "b_dev", "b_prod", "c_dev", "c_prod"]
    c = yaml.safe_load((out / "targets" / "region-c.yml").read_text())
    assert c["targets"]["c_prod"]["variables"]["catalog"] == "prod_c"
    assert c["targets"]["c_prod"]["mode"] == "production"
    a = yaml.safe_load((out / "targets" / "region-a.yml").read_text())
    assert a["targets"]["a_dev"]["default"] is True
    defaults = [t for f in (out / "targets").glob("*.yml")
                for t, d in yaml.safe_load(f.read_text())["targets"].items() if d.get("default")]
    assert defaults == ["a_dev"]


def test_ci_is_pinned_and_split_by_kind(tmp_path):
    out = tmp_path / "bundle"
    scaffold(VARIANTS["single-workspace-with-ci"], out)
    workflow = yaml.safe_load((out / ".github" / "workflows" / "bundle.yml").read_text())
    assert workflow["jobs"]["validate"]["strategy"]["matrix"]["target"] == ["dev", "staging"]
    assert workflow["jobs"]["deploy"]["strategy"]["matrix"]["target"] == ["prod"]
    assert "databricks/setup-cli@v1.20.0" in (out / ".github" / "workflows" / "bundle.yml").read_text()


def test_dry_run_writes_nothing(tmp_path):
    out = tmp_path / "bundle"
    proc = scaffold(VARIANTS["example-answers"], out, "--dry-run")
    assert proc.returncode == 0
    assert "would create databricks.yml" in proc.stdout
    assert not out.exists()


def test_refuses_existing_bundle_and_non_empty_folder(tmp_path):
    out = tmp_path / "bundle"
    assert scaffold(VARIANTS["example-answers"], out).returncode == 0
    again = scaffold(VARIANTS["example-answers"], out, "--allow-non-empty")
    assert again.returncode == 2 and "already contains a bundle" in again.stderr

    other = tmp_path / "other"
    other.mkdir()
    (other / "notes.txt").write_text("keep me")
    assert scaffold(VARIANTS["example-answers"], other).returncode == 2
    assert scaffold(VARIANTS["example-answers"], other, "--allow-non-empty").returncode == 0
    assert (other / "notes.txt").read_text() == "keep me"


@pytest.mark.parametrize("change, message", [
    ({"target_pattern": "{env}"}, "must contain {region}"),
    ({"environments": [{"name": "dev", "kind": "sandbox", "catalog": "x"}]}, "kind must be one of"),
    ({"bundle_name": "bad name"}, "bundle_name"),
    ({"ci": "github-actions", "cli_version": None}, "cli_version is required"),
])
def test_invalid_answers_are_rejected(change, message, tmp_path):
    answers = dict(VARIANTS["example-answers"], **change)
    proc = scaffold(answers, tmp_path / "bundle")
    assert proc.returncode == 2 and message in proc.stderr
    assert not (tmp_path / "bundle").exists()


def test_profile_with_ci_warns(tmp_path):
    answers = dict(VARIANTS["example-answers"], ci="github-actions", cli_version="1.20.0")
    proc = scaffold(answers, tmp_path / "bundle")
    assert proc.returncode == 0 and "workspace.profile" in proc.stderr
