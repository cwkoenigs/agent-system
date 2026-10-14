"""One git worktree per task, on its own branch, removed when the task is done."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def create(repo: Path, task_id: str, work: Path) -> Path:
    path = work / f"{repo.name}--{task_id}"
    if path.exists():
        clean(repo, path)
    branch = f"agent/{task_id}"
    _git(repo, "branch", "-D", branch)
    r = _git(repo, "worktree", "add", "-q", "-b", branch, str(path), "HEAD")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return path


def diff(path: Path) -> str:
    _git(path, "add", "-A")
    return _git(path, "diff", "--cached").stdout


def clean(repo: Path, path: Path) -> None:
    _git(repo, "worktree", "remove", "--force", str(path))
    shutil.rmtree(path, ignore_errors=True)
    _git(repo, "worktree", "prune")
