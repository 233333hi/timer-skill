<div align="center">

# ⏱️ Timer Skill

**Give your agent a floor on effort, not a ceiling on patience.**

Set the amount of time (or the deadline) at the start of a task, check it while working, and **only ship when it is satisfied**.

[简体中文](README.md) | English

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-yellow)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
[![CI](https://github.com/233333hi/timer-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/233333hi/timer-skill/actions/workflows/ci.yml)

</div>

---

> 🧭 **In one line**: it is not a scheduler and it triggers nothing. It does exactly two things — turn "work for N minutes / until 18:00" into **queryable state**, and turn "ship only when satisfied" into a **hard gate**.

> 📌 Symbols used throughout:
> ⛔ **NEVER** · ✅ **MUST** · 🟡 **DEFAULT** · ⚠️ **WATCH** · 🔁 **CHECK**

---

## 😣 The pain it solves

You say "work on this for two hours". It ships in eight minutes. That is not laziness — **the stop condition is baked into the model**: once a working answer exists, the probability mass points at "done". Your time requirement is just one sentence of context, and context is lossy — compressed once, summarized once, pushed out by the next turn, and it never happened.

The timer does not change the model. It changes the **acceptance condition**: "how long did you work" stops being a verbal agreement and becomes state that can be queried and that can refuse a delivery.

| 🔥 What actually goes wrong | 🧠 Why | ✅ What the timer does |
|---|---|---|
| "2 hours" → a barely-working version after 8 minutes | The model optimizes for the minimum sufficient solution | Below target → delivery is explicitly forbidden, keep pushing |
| The requirement evaporates after compaction | Context is lossy | State lives on disk, survives turns, compaction and restarts |
| Clock-burning: `sleep 500 && check progress` | Confusing "waited long enough" with "worked long enough" | ⛔ Sleep / polling / background waits are banned; remaining time must go into a real review pass |
| "Until 18:00" hits midnight, a timezone, or a past time | Time semantics are ambiguous | Local-time parsing, auto-rolls to the next day, reports the UTC offset |
| Two tasks in one session overwrite each other | Single global timer | One timer per session, plus `--name` for parallel tasks |
| "How much longer?" is a guess | Nothing to observe | `now --json` returns elapsed / remaining / satisfied |
| Context is gone and unfinished work ships silently | No gate | `satisfied: false` makes delivery a violation |

> 📊 **Measured locally**: in this machine's session database, the `sleep … && clock.py now` anti-pattern appears **47 times across 10 sessions**. That is not a dumb model — it is the default behaviour when there is no guardrail, which is why this skill's core is not "counting time" but **writing the anti-patterns down as prohibitions**.

---

## 🚀 Usage

### 1️⃣ Install

Drop the `timer/` folder into your harness's skills directory (anything that loads a `SKILL.md` works):

```bash
# Claude Code / any SKILL.md-compatible harness
~/.claude/skills/timer/
# ZCode
~/.zcode/skills/timer/
# Shared skills directory (multiple harnesses)
~/.agents/skills/timer/
```

✅ **MUST** keep the relative layout of `SKILL.md` and `scripts/clock.py`.

### 2️⃣ Set the requirement

```bash
# Minimum work time: must work at least this long, starting now
python -I scripts/clock.py set 45m
python -I scripts/clock.py set 2h
python -I scripts/clock.py set 1h30m

# Deadline: must work until this clock time (rolls to tomorrow if already past)
python -I scripts/clock.py set "until 18:00"
python -I scripts/clock.py set "until 09:00 tomorrow"
```

### 3️⃣ Check it while working

```bash
python -I scripts/clock.py now          # human: 剩 27分13秒 | ⏳ 未达标，继续干
python -I scripts/clock.py now --json   # machine: elapsed_seconds / remaining_seconds / satisfied
```

The field that matters in `now --json` is **`satisfied`**:

- `false` → ⛔ **do not ship**; keep working (review, fix bugs, cover edges, generalize)
- `true` → ✅ the delivery gate opens

### 4️⃣ Cancel / run several

```bash
python -I scripts/clock.py set off                  # cancel the default timer
python -I scripts/clock.py set off --name review    # cancel a named timer

# Parallel tasks, independent timers
python -I scripts/clock.py set 30m --name refactor
python -I scripts/clock.py set "until 22:00" --name review
python -I scripts/clock.py now --name refactor --json
```

---

## 📖 SPEC syntax

| Form | Example | Meaning |
|---|---|---|
| **Minimum work time** | `20m` `90s` `1h30m` `in 20m` | Must work at least this long, starting now |
| **Deadline** | `until 18:00` `by 18:00` | Work until this local clock time; auto-rolls to tomorrow if past |
| **Next-day deadline** | `until 18:00 tomorrow` `until 09:00 +1d` | Explicitly tomorrow |
| **Cancel** | `off` `clear` | Remove that timer (reports whether one existed) |

- ✅ Units `s / m / h / d`, freely combined
- ⚠️ A duration and a deadline cannot be combined (`2h until 18:00` is rejected) — pick one semantic
- 🟡 Everything is parsed in **local time**; output carries `utc_offset` so you can verify

---

## 🚦 The delivery gate (the point of this skill)

```
┌─────────────────────────────────────────────┐
│  timer.satisfied == false                   │
│     ⛔ Do not deliver                        │
│     ✅ Spend remaining time on: line-by-line │
│        re-read / bug hunt / edge cases /     │
│        generalization / stricter measurement │
├─────────────────────────────────────────────┤
│  timer.satisfied == true                    │
│     ✅ Deliver the best version + metrics +   │
│        what changed and why                  │
└─────────────────────────────────────────────┘
```

Three hard rules, written into `SKILL.md`:

- ⛔ **NEVER** idle to satisfy the timer: no `sleep`, no polling, no background job whose only job is to wait, no ending the turn to "come back later". Time is a floor on **effort**, not a countdown to burn.
- ✅ **MUST** fill the remaining time with a real review pass: re-read the request sentence by sentence, re-read the diff, re-run the tests, find the branch you did not cover, try a different input or environment.
- 🔁 **CHECK** every pass: which metric moved? If none did, tighten the measurement (stricter check, more inputs, adversarial cases) instead of spinning.

⚠️ **WATCH** two common misreadings: "the timer ending = I stop" and "the timer running = I can idle". Both are wrong — finishing early does not mean shipping early, and the timer running out does not mean stopping early.

---

## 🗂️ State, isolation, lifecycle

| Aspect | Behaviour |
|---|---|
| **Location** | **Outside** the skill directory: Windows `%LOCALAPPDATA%\dsh-skill-timer`; macOS/Linux `$XDG_STATE_HOME/dsh-skill-timer` (fallback `~/.local/state/…`) |
| **Override** | `DSH_TIMER_STATE=/your/dir` |
| **Session isolation** | Reads any `*_SESSION_ID` (Claude Code, ZCode, Codex, OpenCode, Gemini, Cursor, Copilot, Qwen, …); falls back to a shared `global` key |
| **Multiple timers** | `--name`, default `default` |
| **Atomic writes** | Write `.tmp`, then `os.replace` — a killed process never leaves half a timer |
| **Auto-prune** | State untouched for 14 days is deleted; crash-leftover `.tmp` files after one day |
| **Legacy migration** | Timers written by older versions inside the skill dir are moved out on first run |

✅ State is plain JSON. A corrupt file is treated as "no timer" and never crashes the task.

---

## 🧪 Real case: 12 hours, from one NAND gate to a working computer

> A real session from this machine, not a constructed example. Numbers come from the `session` / `part` tables and the delivered artifacts.

**🧑 The request (2026-10-25 20:56)**

```text
[$timer] 12h
Spend the tokens on something meaningful and valuable. Don't think about what
I want — decide for yourself. I have plenty of tokens and they expire soon,
use them freely.
```

A delegation with **a floor and no brief**: 12 hours, choose your own problem.

**🤖 What happened**

| Observation | Value |
|---|---|
| Timer | `set 12h`; `satisfied` flipped to `true` at 08:58 |
| Wall clock | 20:56 → 08:58, **12 h 02 m** |
| Tool calls | **633** |
| Delivery | Only after the gate opened; every pass moved work forward instead of waiting |

**📦 What 12 hours produced (SPARK)**

Starting from the single primitive `nand(a, b)`, a 16-bit computer was built bottom-up that runs a self-compiled program, with an independent reference implementation cross-checking every layer:

- ✅ **97/97 tests green**: boolean gates → adder/ALU → registers/RAM/PC → CPU → assembler → stack VM → compiler → self-hosted OS → end-to-end
- ✅ **~11,000 random programs** cross-checked through two paths (compile→assemble→machine vs. direct interpreter), zero failures
- ✅ Two demos running for real: a Pong game scoring on a seven-segment display, and Conway's Life at 64×64 for 10 generations
- ✅ A ten-chapter book, *From NAND to an Operating System*, documenting **8 real bugs** found along the way (±32768 comparator overflow, `let a[i]=a[n]` pointer aliasing, a division-wraparound infinite loop)
- ✅ Five interactive labs (NAND / adder / ALU / CPU single-step / Pong)

**🔁 Why this case is representative**

1. **Without the timer** the task ends as soon as one demo works — roughly 40 minutes of work.
2. **With the timer**, 12 hours becomes an **acceptable floor**: every pass has to answer "which metric moved", so the pressure shifts from "ship sooner" to "don't stop where the evidence stops".
3. **The cost is visible**: 633 tool calls, 97 tests, ~11,000 randomized programs, 8 real bugs. None of that appears from "thinking harder" — it appears because the time was actually filled.

---

## 🧩 How it differs from neighbours

| | What it is | When to use it |
|---|---|---|
| ⏱️ **Timer (this skill)** | A **state machine** for a time requirement | "Work at least X / until Y before wrapping up" |
| ⏰ Cron / scheduled tasks | A **trigger** that wakes the agent | "Check in every 20 minutes" |
| 📋 Todo / plan | **Task decomposition** | "What to do, in which order" |
| 🧪 Tests / CI | **Correctness gate** | "Did this change break anything" |

They compose: the timer owns *how long*, cron owns *when to start*, todo owns *what*, tests own *whether it is right*.

---

## ❓ FAQ

**Does it make the agent idle for 12 hours?**
No. `SKILL.md` bans sleep / polling / background waits outright — that is the easiest and least valuable cheat. Time may only be spent on real work.

**What if the work is finished early?**
Finishing early does not mean shipping early. The remainder goes into review, bug hunting, generalization and stricter measurement — that is what separates this from a countdown.

**Any dependencies? Cross-platform?**
Standard library only, Python 3.8+, Windows / macOS / Linux. ⚠️ On some Windows setups `python3` is a broken stub — use `python` or an absolute interpreter path.

**Will several harnesses clash?**
No. State is keyed by `*_SESSION_ID`; inside one session use `--name`. Environments without a session id fall back to `global`, so give each task a distinct `--name` there.

**Will state files pile up?**
No. Files untouched for 14 days are pruned, and crash-leftover temp files after one day.

**Is this just padding the clock?**
No. It constrains **when to deliver**, not **how good the output is**; quality still comes from your acceptance criteria and tests. The two together are what work.

---

## 📁 Repository layout

```text
timer-skill/
├── README.md            # 中文说明
├── README.en.md         # English (this file)
├── SKILL.md             # Behaviour spec read by the model (the gate lives here)
├── scripts/
│   └── clock.py         # The timer, stdlib only, no dependencies
├── tests/
│   └── test_clock.py    # 10 portable tests (subprocess + isolated state dir)
├── .github/workflows/
│   └── ci.yml           # Ubuntu / macOS / Windows × Python 3.9 / 3.13
└── LICENSE              # MIT
```

## ✅ Tests

```bash
python -m unittest discover -s tests -v
```

Every test runs against a temporary `DSH_TIMER_STATE` directory, so it never touches your live timers and never depends on the machine's clock or paths.

---

## 📄 License

[MIT](LICENSE) © 2026 wayleon li (233333hi)

<div align="center">

**⏱️ Time is a floor on effort, not a test of patience.**

</div>
