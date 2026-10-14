"""The morning digest: what shipped overnight, what needs a human, one line each.
Slack posting is a stub; the text is what it would send."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .metrics import Metrics


def build(metrics: Metrics, results: Path | None = None) -> str:
    rows = metrics.rows()
    shipped = [r for r in rows if r["tests_passed"]]
    needs = [r for r in rows if not r["tests_passed"]]
    lines = [f"Agent digest {date.today().isoformat()}: {len(shipped)} shipped, {len(needs)} need a human.", ""]
    for r in shipped:
        lines.append(f"✓ {r['repo']} {r['task_id']}: closed at {r['closed_tier']}, {r['local_attempts']} attempt(s), {r['wall_seconds']}s")
    for r in needs:
        why = ""
        if results and (results / r["task_id"] / "summary.md").exists():
            why = (results / r["task_id"] / "summary.md").read_text().strip().split("\n")[0][:160]
        lines.append(f"⚠ {r['repo']} {r['task_id']}: {why or 'see results'}")
    return "\n".join(lines) + "\n"


def post_slack(text: str, webhook: str | None) -> None:
    """TODO: POST {"text": text} to the webhook from the environment (SLACK_WEBHOOK). Stub."""
    raise NotImplementedError("Slack posting is not wired; set SLACK_WEBHOOK and implement post_slack")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--results", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None, help="write the digest here as well as printing it")
    args = ap.parse_args(argv)
    text = build(Metrics(args.db), args.results)
    print(text)
    if args.out:
        args.out.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
