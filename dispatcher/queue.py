"""Task sources. The local file is the bench's schema; GitLab issues labeled `agent` are the
production source and `ds task` creates one. The adapter below is the interface only."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Task:
    id: str
    repo: str
    text: str
    accept: str
    type: str = "task"
    tags: list[str] = field(default_factory=list)


class LocalQueue:
    def __init__(self, path: Path):
        data = yaml.safe_load(Path(path).read_text()) or {}
        self._tasks = [Task(id=t["id"], repo=t["repo"], text=t["text"], accept=t["accept"],
                            type=t.get("type", "task"), tags=list(t.get("tags", []))) for t in data.get("tasks", [])]

    def pop_all(self) -> list[Task]:
        tasks, self._tasks = self._tasks, []
        return tasks


class GitLabQueue:
    """Issues labeled `agent` in the repository's project. TODO: needs GITLAB_HOST and a token
    from the environment; poll `GET /projects/:id/issues?labels=agent&state=opened`, map title+body
    to Task (accept from the body's `accept:` line or the repo's AGENTS.md test command), and
    comment the result or the MR link back on the issue."""

    def __init__(self, project: str):
        self.project = project

    def pop_all(self) -> list[Task]:
        raise NotImplementedError("GitLab queue: set GITLAB_HOST and GITLAB_TOKEN; not implemented in this skeleton")

    def comment(self, task: Task, text: str) -> None:
        raise NotImplementedError
