"""`--once` with the dry tier against a small git repo: one metrics row per task, a patch and a
summary per task, and a digest that separates shipped from needs-a-human."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from dispatcher import digest, run
from dispatcher.metrics import Metrics


def _repo(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / "repos" / name
    (repo / ".ds").mkdir(parents=True)
    (repo / "README.md").write_text(f"# {name}\n")
    (repo / ".ds/agent.toml").write_text('[tiers]\nexecute = "cortex:sonnet"\nplan = "cortex:opus"\nreview = "cortex:opus"\n[limits]\nmax_attempts = 2\n')
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@l", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@l", "commit", "-qm", "init"], cwd=repo, check=True)
    return repo


def test_once_dry_tier(tmp_path: Path):
    _repo(tmp_path, "alpha")
    tasks = tmp_path / "TASKS.yaml"
    tasks.write_text(yaml.safe_dump({"tasks": [
        {"id": "a-01", "repo": "alpha", "type": "docs", "text": "Nothing to do; already true.", "accept": "test -f README.md"},
        {"id": "a-02", "repo": "alpha", "type": "tests", "text": "Add a test that cannot exist yet.", "accept": "test -f tests/test_x.py"},
    ]}))
    out = tmp_path / "results"
    rc = run.main(["--once", "--tasks", str(tasks), "--repos", str(tmp_path / "repos"), "--tier", "dry", "--out", str(out)])
    assert rc == 0
    rows = Metrics(out / "metrics.db").rows()
    assert [r["task_id"] for r in rows] == ["a-01", "a-02"]
    assert rows[0]["tests_passed"] == 1 and rows[0]["closed_tier"] == "dry" and rows[0]["local_attempts"] == 1
    assert rows[1]["tests_passed"] == 0 and rows[1]["closed_tier"] is None and rows[1]["local_attempts"] == 2 and rows[1]["escalations"] == 1
    assert (out / "a-01/summary.md").read_text().startswith("Done:")
    assert (out / "a-02/summary.md").read_text().startswith("Needs you:") and "still fails after 2 attempt(s)" in (out / "a-02/summary.md").read_text()
    assert (out / "to_snowflake.sql").exists()
    # worktrees are cleaned, the repo is untouched
    assert not any((out / "work").iterdir())
    text = digest.build(Metrics(out / "metrics.db"), out)
    assert "1 shipped, 1 need a human" in text and "⚠ alpha a-02" in text
