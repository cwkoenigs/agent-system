# agent-system

The dispatcher from `docs/agent-system.md`, without the local tier: work goes to the cheapest
Cortex tier that can do it, and only the result reaches a person. This checkout holds the
skeleton with a `dry` tier so the plumbing is testable without any model.

    uv run python -m dispatcher.run --once --tasks TASKS.yaml --repos <dir> --tier dry --out results/
    uv run python -m dispatcher.digest --db results/metrics.db

| Module | Does |
|---|---|
| `dispatcher/queue.py` | Reads tasks from `TASKS.yaml` (same schema as the bench); GitLab issue adapter is a stub with the interface |
| `dispatcher/worktree.py` | One git worktree per task, cleaned after |
| `dispatcher/ladder.py` | Tiers from `.ds/agent.toml`: execute (Cortex Sonnet-class) with attempts, escalate to plan/review (Opus); `dry` runs nothing and lets the acceptance command decide |
| `dispatcher/metrics.py` | One SQLite row per task; `to_snowflake.sql` mirrors it as `DS_OPS.AGENT.TASKS` |
| `dispatcher/run.py` | `--once`: process the queue, write `results/<task>/{diff.patch,summary.md}`, record metrics |
| `dispatcher/digest.py` | The morning digest from the metrics DB; Slack posting is a stub |

Not here yet: opening the MR (needs a GitLab token), the Slack webhook, the Snowflake mirror,
and a real `cortex` call, which `ladder.py` shapes but this machine cannot verify.
