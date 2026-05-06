---
date: 2026-05-05 11:35 AEST
session: hibernation-checkpoint
---

# Current Active Project: ThumbTack

**ThumbTack** is the primary active project.
- Local URL: http://10.0.0.53:3456
- Repo: github.com/JohnColling/thumbtack
- Location: ~/github/johncolling/thumbtack
- Port: 3456 (systemd user service: `--user thumbtack.service`)

**Recent session activity (this session):**
- `top_spenders.html` dashboard created (sortable table, dark theme, jinja2 include). Ready for wiring to live data.
- TWG Azure environment files merged into single canonical note: `Resources/TWG Azure Tenants.md`
- Memory trimmed to 93% and re-saved.

**Known issues from previous session (pre-`/new`):**
- `task_decomposer.py` — LLM timeouts at ~60s on CPU-only hardware. Template/kw fallback was added, capped to 6 subtasks max. (Commit `ca7505f` pushed to GitHub)
- `worker_pool.py` — `claude -p` stdin EOF added (was missing), BrokenPipeError guard added.
- `agent_output` — `ORDER BY id` added for deterministic output ordering.

**Top open tasks:**
1. Wire `top_spenders.html` to real data (GET endpoint + JS fetch or server-render)
2. Restart ThumbTack service to apply latest commits (was running old code in previous session).
3. Test end-to-end auto-decomposition + worker pool dispatch on task #18 or #20.
4. Design external API webhook (task on Things to Do.md)
