---
name: timer
description: Work timer. Never deliver before the timer stops; deliver only when both the user's requirements and the timer condition are met. If requirements are met but time remains, keep reviewing and improving; if the timer is up but requirements are unmet, keep working on the requirements.
---

# Work Timer

**Principle**: Do not deliver work while the timer is running. Deliver only when the user's requirements AND the timer condition are both satisfied. Requirements met but time remains → keep reviewing and improving. Timer elapsed but requirements unmet → keep working on the requirements.

## While the timer is running

- ⛔ **NEVER idle to satisfy the timer**: do not `sleep`, poll, or wait out the clock. The timer is a floor on effort, not a clock to burn down. If it has not stopped, spend the remaining time pushing the work forward.
- ✅ **MUST spend the remaining time on a real review pass** (when requirements are met but time remains). One pass means:
  - **Re-read sentence by sentence**: split the user's request into checkable sub-tasks and confirm each one maps to a finished task.
  - **Re-check the semantics**: does what you built match what the user actually meant, not just what they literally said?
  - **Hunt for bugs**: re-read the diff, re-run the tests, find the case you did not cover.
  - **Probe edge cases and generalization**: does it still hold on a different input, a different environment, a different instance? Is anything hardcoded that should be a parameter?
- 🔄 **While the timer runs: grill → measure → optimize → repeat.**
  - ⛔ **Enumerated prohibitions**: no `sleep`; no background/timer job whose only job is to wait; no ending the turn or stopping the API call to "come back later"; no idling to burn the clock; even a 0 ms `sleep` / `Start-Sleep` token is a violation. No off/reset to dodge the gate. Not knowing the next step is the grill signal — attack an assumption, never wait.
  - 🎯 **Metrics**: if the user gave metrics, turn each into a measurable check + baseline (vague goals → a measurable proxy that still traces to them). If none, decompose the user's original request from first principles into 2–4 measurable proxies (desired outcome, failure boundary, cost) and adopt them. Every metric must trace to the user's request (a direct refinement of a user metric counts); if a proxy improves while the request gets worse, the proxy is wrong.
  - **Loop**: pick the claim most likely to fail a metric (local or global) → write the rejection and the observation that would prove it → observe → re-derive the goal without the current solution's vocabulary and diff → predict the point's metric delta (or which case flips) → implement → measure → keep only a verified gain (checkpoint first; revert else; log claim → evidence → baseline→final).
  - 🔁 **Repeat until `timer.satisfied`**: if a pass moves no metric, tighten the measurement (stricter check, more inputs, adversarial cases) or re-derive the proxy set from the request — never invent a metric the request does not support; once the user's metrics all pass, verifiable hardening is the honest next move. No early stop, no fake pass.
- 🚦 **Delivery gate (overrides any conflict above)**: `timer.satisfied` is true; every kept change has a measured baseline→final delta; no sleep/background-wait/stop-and-resume was used. Deliver the best measured version + the baseline→final metric table + what changed and why.

## Usage

```bash
PY="${PYTHON:-python}"; "$PY" --version >/dev/null 2>&1 || PY="python3"
"$PY" -I "<SKILL_DIR>/scripts/clock.py" now [--json]
"$PY" -I "<SKILL_DIR>/scripts/clock.py" set "<SPEC>" [--json]
"$PY" -I "<SKILL_DIR>/scripts/clock.py" set off
```

⚠️ **WATCH — interpreter**: `python3` is a broken stub in some Windows setups; if the first line above falls through, point `PYTHON` at the real interpreter (`PYTHON=/path/to/python.exe`). Never hardcode a machine-specific absolute path into this file.

| SPEC | Example | Meaning |
|---|---|---|
| Minimum work time | `20m` `1h30m` `90s` | Must work at least this long, starting now |
| Deadline | `until 18:00` `until 18:00 tomorrow` | Must work until this clock time |

`timer.satisfied` in `now --json` reports whether the timer condition is met. State is per-session; `--name` keeps several timers side by side.

State is keyed by the harness session id (`CLAUDE_CODE_SESSION_ID`, `DSH_SESSION_ID`, any `*_SESSION_ID`); without one it falls back to a shared `global` key, so give each task a distinct `--name` there. It lives outside the skill directory (`%LOCALAPPDATA%/dsh-skill-timer`, `$XDG_STATE_HOME/dsh-skill-timer` on POSIX, override with `DSH_TIMER_STATE`) and entries older than 14 days are pruned.
