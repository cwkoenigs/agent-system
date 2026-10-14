"""`python -m dispatcher.run --once`: process the queue once.

For each task: worktree, ladder, acceptance, metrics row, and the deliverable: a patch and a
one-paragraph summary a person can read in ten seconds. Opening the MR is the GitLab adapter's
job and is a stub here; the summary is what it would carry.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from . import ladder, worktree
from .metrics import Metrics
from .queue import LocalQueue, Task


def summary(task: Task, out: ladder.Outcome, diff_text: str) -> str:
    changed = sum(1 for l in diff_text.splitlines() if l.startswith("+++ "))
    if out.tests_passed:
        head = (f"Done: {task.text} Closed at tier `{out.closed_tier}` after {out.attempts} attempt(s)"
                f"{' and an escalation' if out.escalations else ''}; `{task.accept}` passes; {changed} file(s) changed.")
        if out.review_verdict:
            head += f" Review: {out.review_verdict}"
    else:
        head = f"Needs you: {task.text} {out.needs_human}"
    return head + "\n"


def process(task: Task, repo: Path, work: Path, out_dir: Path, metrics: Metrics, tier: str | None) -> ladder.Outcome:
    t0 = time.time()
    wt = worktree.create(repo, task.id, work)
    try:
        cfg = ladder.load_agent_config(repo)
        outcome = ladder.run_ladder(task, wt, cfg, tier_override=tier, diff_fn=worktree.diff)
        diff_text = worktree.diff(wt)
    finally:
        worktree.clean(repo, wt)
    d = out_dir / task.id
    d.mkdir(parents=True, exist_ok=True)
    (d / "diff.patch").write_text(diff_text)
    (d / "summary.md").write_text(summary(task, outcome, diff_text))
    tier_tokens = outcome.tokens
    metrics.record(task_id=task.id, repo=repo.name, task_type=task.type, closed_tier=outcome.closed_tier,
                   local_attempts=outcome.attempts, escalations=outcome.escalations,
                   tokens_t0=0, tokens_t1=tier_tokens.get("execute", 0),
                   tokens_t2=tier_tokens.get("plan", 0) + tier_tokens.get("review", 0) + tier_tokens.get("escalate", 0),
                   calls_canon=0, calls_graph=0, calls_lsp=0, calls_search=0, calls_file_read=0,
                   tests_passed=int(outcome.tests_passed), gate_confidence=outcome.gate_confidence,
                   review_verdict=outcome.review_verdict, human_review_minutes=0.0, wall_seconds=round(time.time() - t0, 1))
    return outcome


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="process the queue once and exit")
    ap.add_argument("--tasks", type=Path, required=True, help="TASKS.yaml")
    ap.add_argument("--repos", type=Path, required=True, help="directory holding the repositories")
    ap.add_argument("--repo-suffix", default="", help="appended to the task's repo name to find its directory")
    ap.add_argument("--tier", default=None, help="override every tier, e.g. dry")
    ap.add_argument("--out", type=Path, default=Path("results"))
    ap.add_argument("--db", type=Path, default=None, help="metrics SQLite (default: <out>/metrics.db)")
    args = ap.parse_args(argv)
    if not args.once:
        ap.error("only --once is implemented; cron it")
    metrics = Metrics(args.db or args.out / "metrics.db")
    work = args.out / "work"
    work.mkdir(parents=True, exist_ok=True)
    tasks = LocalQueue(args.tasks).pop_all()
    done = 0
    for task in tasks:
        repo = args.repos / f"{task.repo}{args.repo_suffix}"
        if not (repo / ".git").exists():
            print(f"{task.id}: repo not found at {repo}; skipped")
            continue
        outcome = process(task, repo, work, args.out, metrics, args.tier)
        done += 1
        print(f"{task.id:8} {task.repo:22} {'passed' if outcome.tests_passed else 'needs human':12} tier={outcome.closed_tier or '-'} attempts={outcome.attempts} escalations={outcome.escalations}")
    print(f"{done} task(s) processed; metrics in {metrics.path}; results in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
