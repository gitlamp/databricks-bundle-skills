"""Run both scripts against the fixture bundles. No Databricks CLI or workspace is used."""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "databricks-bundle" / "scripts"
FIXTURES = REPO / "tests" / "fixtures"


def run(script, *args):
    proc = subprocess.run([sys.executable, str(SCRIPTS / script), *args, "--format", "json"],
                          capture_output=True, text=True)
    assert proc.returncode in (0, 1), proc.stderr
    return proc.returncode, json.loads(proc.stdout)


def lint(fixture, *extra):
    root = FIXTURES / fixture
    return run("lint_bundle.py", "--bundle", str(root), "--ci-root", str(root), *extra)


# ---- coverage -----------------------------------------------------------

def test_single_workspace_has_no_gaps():
    code, out = run("target_coverage.py", "--bundle", str(FIXTURES / "single-workspace"))
    assert code == 0
    assert out["gaps"] == [] and out["unattached"] == []
    assert set(out["resources"]) == {"jobs.daily_report", "pipelines.sales_pipeline", "schemas.sales_schema"}


def test_multi_workspace_gap_with_allow_list():
    root = FIXTURES / "multi-workspace"
    code, out = run("target_coverage.py", "--bundle", str(root), "--allow", str(root / "allow.yml"))
    assert code == 1
    assert [(g["resource"], g["missing_from"]) for g in out["gaps"]] == [("jobs.orders_sync", ["prod-b"])]


def test_multi_workspace_without_allow_list_reports_intended_gap_too():
    code, out = run("target_coverage.py", "--bundle", str(FIXTURES / "multi-workspace"))
    assert {g["resource"] for g in out["gaps"]} == {"jobs.orders_sync", "jobs.local_export"}


def test_multi_workspace_target_override_does_not_create_resource():
    # prod-b only overrides configuration of a top-level pipeline; it must stay one resource.
    _, out = run("target_coverage.py", "--bundle", str(FIXTURES / "multi-workspace"))
    assert out["resources"]["pipelines.catalog_pipeline"] == ["dev-a", "dev-b", "prod-a", "prod-b"]


def test_anchor_style_gap_and_unattached():
    code, out = run("target_coverage.py", "--bundle", str(FIXTURES / "anchor-style"))
    assert code == 1
    assert [(g["resource"], g["missing_from"]) for g in out["gaps"]] == [("pipelines.clean_pipeline", ["prod"])]
    assert [u["key"] for u in out["unattached"]] == ["orphan_job"]


def test_allow_entry_flag_matches_allow_file():
    code, out = run("target_coverage.py", "--bundle", str(FIXTURES / "multi-workspace"),
                    "--allow-entry", "jobs.local_export=dev-b,prod-b")
    assert [g["resource"] for g in out["gaps"]] == ["jobs.orders_sync"]
    _, out = run("target_coverage.py", "--bundle", str(FIXTURES / "multi-workspace"),
                 "--allow-entry", "jobs.local_export=*", "--allow-entry", "jobs.orders_sync=prod-b")
    assert out["gaps"] == []


def test_reference_layout_model_only_in_region_a():
    root = str(FIXTURES / "reference-layout")
    _, out = run("target_coverage.py", "--bundle", root)
    assert {g["resource"] for g in out["gaps"]} == {"jobs.churn_train", "registered_models.churn_model"}
    assert out["resources"]["jobs.orders_ingest"] == ["dev-A", "dev-B", "prod-A", "prod-B"]
    code, out = run("target_coverage.py", "--bundle", root,
                    "--allow-entry", "jobs.churn_train=dev-B,prod-B",
                    "--allow-entry", "registered_models.churn_model=dev-B,prod-B")
    assert code == 0 and out["gaps"] == [] and out["unattached"] == []


def test_target_subset():
    code, out = run("target_coverage.py", "--bundle", str(FIXTURES / "anchor-style"), "--targets", "dev,staging")
    assert code == 1  # orphan_job is still unattached
    assert out["gaps"] == []


def test_from_validate_json():
    v = FIXTURES / "validate-json"
    code, out = run("target_coverage.py", "--bundle", str(FIXTURES / "single-workspace"),
                    "--from-validate-json", f"dev={v / 'dev.json'}",
                    "--from-validate-json", f"prod={v / 'prod.json'}")
    assert code == 1
    assert [(g["resource"], g["missing_from"]) for g in out["gaps"]] == [("jobs.daily_report", ["prod"])]


def test_unknown_target_is_an_error():
    proc = subprocess.run([sys.executable, str(SCRIPTS / "target_coverage.py"),
                           "--bundle", str(FIXTURES / "single-workspace"), "--targets", "nope"],
                          capture_output=True, text=True)
    assert proc.returncode == 2


# ---- lint -----------------------------------------------------------------

@pytest.mark.parametrize("fixture, expected", [
    ("single-workspace", {"L001": 1, "L003": 1, "L005": 1, "L006": 1}),
    ("multi-workspace", {"L002": 1, "L004": 1, "L007": 1, "L010": 2}),
    ("anchor-style", {"L008": 1, "L009": 1, "L011": 1}),
    ("reference-layout", {"L012": 1}),
])
def test_lint_finds_exactly_the_planted_defects(fixture, expected):
    code, findings = lint(fixture)
    assert Counter(f["rule"] for f in findings) == expected
    assert code == 1


def test_lint_points_at_the_right_lines():
    _, findings = lint("single-workspace")
    by_rule = {f["rule"]: f for f in findings}
    text = (FIXTURES / "single-workspace" / "databricks.yml").read_text().splitlines()
    assert "root_path" in text[by_rule["L005"]["line"] - 1]
    assert "warehouse_id" in text[by_rule["L006"]["line"] - 1]
    jobs = (FIXTURES / "single-workspace" / "resources" / "jobs.yml").read_text().splitlines()
    assert "service_principal_name" in jobs[by_rule["L001"]["line"] - 1]


def test_disable_and_prod_override():
    _, findings = lint("multi-workspace", "--disable", "L010,L002", "--prod-targets", "prod-a")
    assert Counter(f["rule"] for f in findings) == {"L007": 1}


def test_style_only_findings_exit_zero():
    code, findings = lint("single-workspace", "--disable", "L001,L005,L006")
    assert [f["rule"] for f in findings] == ["L003"]
    assert code == 0
