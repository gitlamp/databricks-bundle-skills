"""Check the skill folder is well-formed and importable as a single skill."""
import io
import json
import re
import zipfile
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parents[1] / "databricks-bundle"
SKILL_MD = SKILL / "SKILL.md"


def frontmatter():
    text = SKILL_MD.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with YAML frontmatter"
    return yaml.safe_load(match.group(1)), text[match.end():]


def test_frontmatter_fields():
    meta, _ = frontmatter()
    assert {"name", "description"} <= set(meta) <= {"name", "description", "license"}
    assert meta.get("license") == "MIT"
    assert re.fullmatch(r"[a-z0-9-]{1,64}", meta["name"])
    assert meta["name"] == SKILL.name
    assert 0 < len(meta["description"]) <= 1024
    assert "claude" not in meta["name"] and "anthropic" not in meta["name"]


def test_skill_license_matches_repo_license():
    # The skill folder is often copied or zipped alone, so it carries its own copy.
    assert (SKILL / "LICENSE.txt").read_bytes() == (SKILL.parent / "LICENSE").read_bytes()


def test_skill_md_stays_short():
    assert len(SKILL_MD.read_text(encoding="utf-8").splitlines()) <= 150


def test_every_referenced_file_exists():
    pattern = re.compile(r"`((?:agents|references|scripts)/[\w./-]+\.(?:md|py))`")
    for md in [SKILL_MD, *SKILL.glob("agents/*.md"), *SKILL.glob("references/*.md")]:
        for ref in pattern.findall(md.read_text(encoding="utf-8")):
            assert (SKILL / ref).is_file(), f"{md.name} references missing {ref}"


def test_every_agent_is_routed_and_has_sections():
    body = SKILL_MD.read_text(encoding="utf-8")
    for agent in SKILL.glob("agents/*.md"):
        assert f"agents/{agent.name}" in body, f"{agent.name} is not listed in SKILL.md"
        text = agent.read_text(encoding="utf-8")
        for section in ("**Purpose:**", "**Use for:**", "**Do NOT use for:**", "## Steps", "## Output", "## Don'ts"):
            assert section in text, f"{agent.name} lacks {section}"


def test_evals_cover_every_agent():
    evals = json.loads((SKILL / "evals" / "evals.json").read_text(encoding="utf-8"))
    covered = {e["expected_agent"] for e in evals["evals"]}
    assert covered >= {p.stem for p in SKILL.glob("agents/*.md")}


def test_zip_is_small_and_self_contained():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in SKILL.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                zf.write(path, Path(SKILL.name) / path.relative_to(SKILL))
    assert buf.tell() < 1_000_000
    names = zipfile.ZipFile(buf).namelist()
    assert f"{SKILL.name}/SKILL.md" in names
