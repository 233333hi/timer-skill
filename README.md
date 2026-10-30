<div align="center">

# ⏱️ Timer Skill

**给 AI 一个「时间下限」，而不是一个「时间上限」。**

任务开始时记下你要求的时间长度（或截止时刻），干活期间随时可查，**只有达标才允许交付**。

简体中文 | [English](README.en.md)

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-yellow)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
[![CI](https://github.com/233333hi/timer-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/233333hi/timer-skill/actions/workflows/ci.yml)

</div>

---

> 🧭 **一句话定位**：它不是调度器，不触发任何东西。它只做两件事——把「必须干满多久 / 干到几点」变成**可查询的状态**，把「达标才交付」变成**硬闸门**。

> 📌 术语符号（全文统一）：
> ⛔ **NEVER** = 禁止 · ✅ **MUST** = 必须 · 🟡 **DEFAULT** = 默认值 · ⚠️ **WATCH** = 常见坑 · 🔁 **CHECK** = 判断标准

---

## 😣 它解决的痛点

你说「给我干两个小时」，它 8 分钟就交活。这不是偷懒，**终止条件写在语言模型的基因里**：一旦找到能跑通的答案，概率分布就指向「结束」。而你的时间要求只是一句话，活在上下文里——被压缩一次、被摘要一次、被新任务挤一次，就等于没说过。

Timer 改变的不是模型，是**验收条件**：把「干了多久」从口头约定，变成一个查得到、能拒绝交付的硬状态。

| 🔥 真实翻车现象 | 🧠 根因 | ✅ Timer 的做法 |
|---|---|---|
| 「给你 2 小时」→ 8 分钟交一个勉强能跑的版本 | 模型的最优策略是「最小充分解」 | 未达标 → 明确禁止交付，只能继续推进 |
| 时间要求散落在上下文，压缩后就蒸发 | 上下文是有损的 | 状态落磁盘，跨轮次、跨压缩、跨重启存活 |
| 「硬熬时钟」：`sleep 500 && 查一下进度` | 误以为「等够时间」=「干够时间」 | ⛔ 明令禁止 sleep / 轮询 / 挂后台等钟点，剩下的时间必须用在真实复查上 |
| 「干到 18:00」碰上跨天、时区、已经过点 | 时间语义天生有歧义 | 本地时区解析，过点自动顺延到次日，输出 UTC 偏移 |
| 一个会话跑两个任务，时间要求互相覆盖 | 计时器是单例的 | 每个会话 + 每个 `--name` 独立计时 |
| 只剩多少全靠感觉估 | 没有观测点 | `now --json` 给出 elapsed / remaining / satisfied |
| 上下文没了，一个未完成的任务被静默交付 | 没有闸门 | `timer.satisfied` 为 false 时，交付 = 违规 |

> 📊 **本机实测**：本地会话数据库里，「`sleep … && clock.py now`」这种硬熬时钟的调用出现过 **47 次，分布在 10 个会话**。这不是模型笨，而是**没有护栏时的默认行为**——所以这个 skill 的核心不是「计时」，是**把反模式写成明令禁止**。

---

## 🚀 使用方式

### 1️⃣ 安装

把 `timer/` 目录放进你所用 harness 的 skills 目录即可（任何会加载 `SKILL.md` 的框架都适用）：

```bash
# Claude Code / 兼容 SKILL.md 的 harness
~/.claude/skills/timer/
# ZCode
~/.zcode/skills/timer/
# 共享技能目录（多 harness 共用）
~/.agents/skills/timer/
```

✅ **MUST** 保持 `SKILL.md` 与 `scripts/clock.py` 的相对位置不变。

### 2️⃣ 设定时间要求

```bash
# 最短工时：从现在起必须干满这么久
python -I scripts/clock.py set 45m
python -I scripts/clock.py set 2h
python -I scripts/clock.py set 1h30m

# 截止时刻：必须干到这个钟点（已过点会自动顺延到次日）
python -I scripts/clock.py set "until 18:00"
python -I scripts/clock.py set "until 09:00 tomorrow"
```

### 3️⃣ 干活期间随时查

```bash
python -I scripts/clock.py now          # 人读：还剩 27分13秒 | ⏳ 未达标，继续干
python -I scripts/clock.py now --json   # 机读：elapsed_seconds / remaining_seconds / satisfied
```

`now --json` 里最关键的一个字段是 **`satisfied`**：

- `false` → ⛔ **禁止交付**，继续推进工作（复查、修 bug、补边界、做泛化）
- `true` → ✅ 交付闸门打开

### 4️⃣ 取消 / 并行

```bash
python -I scripts/clock.py set off                  # 取消默认计时器
python -I scripts/clock.py set off --name review    # 取消指定计时器

# 同时跑多个任务，各计各的
python -I scripts/clock.py set 30m --name refactor
python -I scripts/clock.py set "until 22:00" --name review
python -I scripts/clock.py now --name refactor --json
```

---

## 📖 SPEC 语法表

| 写法 | 例子 | 含义 |
|---|---|---|
| **最短工时** | `20m` `90s` `1h30m` `in 20m` | 从现在起必须干满这么久 |
| **截止时刻** | `until 18:00` `by 18:00` `到 18:00` | 必须干到这个本地钟点；已过点自动顺延次日 |
| **次日截止** | `until 18:00 tomorrow` `until 09:00 +1d` | 显式指定明天的钟点 |
| **取消** | `off` `clear` `取消` | 删除该计时器（返回是否真的删掉了） |

- ✅ 支持 `s / m / h / d` 四种单位自由组合
- ⚠️ 纯时长和截止时刻不能混写（`2h until 18:00` 会被拒绝），语义二选一
- 🟡 全部按**本地时区**解析，输出里带 `utc_offset` 便于核对

---

## 🚦 交付闸门（这个 skill 的灵魂）

| 状态 | 允许做什么 |
|---|---|
| ⛔ `satisfied == false` | **禁止交付**。剩余时间只能用在：逐句复查 / 修 bug / 补边界 / 泛化 / 更严的测量 |
| ✅ `satisfied == true` | 交付最佳版本 + 度量表（baseline → final）+ 改了什么、为什么 |

三条硬规则，写死在 `SKILL.md` 里：

- ⛔ **NEVER** 空转等钟点：不许 `sleep`、不许轮询、不许挂个后台任务只为了等时间、不许结束这一轮说"等会儿再来"。时间是对**工作量**的下限，不是要烧掉的倒计时。
- ✅ **MUST** 用真实复查填满剩余时间：重新逐句读需求、重读 diff、重跑测试、找没覆盖的分支、换一个输入/环境再验一遍。
- 🔁 **CHECK** 每轮问自己：这轮改动让哪个指标动了？没动就加大测量强度（更严的检查、更多输入、对抗样例），而不是原地空转。

⚠️ **WATCH** 常见误解：以为"计时器到点 = 自动结束"或"到点 = 可以摸鱼"。两条都错——早到不早交，晚到不收工。

---

## 🗂️ 状态、隔离与生命周期

| 维度 | 行为 |
|---|---|
| **存储位置** | 技能目录**之外**：Windows `%LOCALAPPDATA%\dsh-skill-timer`；macOS/Linux `$XDG_STATE_HOME/dsh-skill-timer`（回退 `~/.local/state/…`） |
| **覆盖路径** | `DSH_TIMER_STATE=/your/dir` |
| **会话隔离** | 自动读取 `*_SESSION_ID`（Claude Code / ZCode / Codex / OpenCode / Gemini / Cursor / Copilot / Qwen 等）；没有就落到共享的 `global` |
| **多计时器** | `--name`，默认 `default` |
| **原子写入** | 先写 `.tmp` 再 `os.replace`，进程被杀不会留下半个计时器 |
| **自动清理** | 14 天未更新的状态文件自动删除；崩溃残留的 `.tmp` 一天后清理 |
| **旧状态迁移** | 早期版本写在技能目录里的 `state/`，启动时自动搬走并删目录 |

✅ 所有状态文件都是**纯 JSON**，损坏时按"没有计时器"处理，不会让任务崩掉。

---

## 🧪 真实案例：12 小时，从一道 NAND 门造一台计算机

> 这是本机真实跑过的会话，不是编的。数据来自 `session` / `part` 表与最终交付物。

**🧑 用户原话（2026-10-25 20:56）**

```text
[$timer] 12h
自己花 tokens 去干一些有意义有价值的东西，不要想着我怎么想，
你自己认为有价值就行，我现在 tokens 很多，但要过期了，尽情用
```

这是一个**只有下限、没有内容**的委托：给 12 小时，题目自拟。

**🤖 发生了什么**

| 观察项 | 数据 |
|---|---|
| 计时器 | `set 12h`；08:56:38 到点，`satisfied` 转 `true`，08:58 交付 |
| 实际跨度 | 20:56 → 08:58，**12 小时 02 分** |
| 工具调用 | **633 次** |
| 交付方式 | 计时器达标后才交付，中间每一轮都在推进而非空转 |

**📦 12 小时造出来的东西（SPARK · 火种）**

从唯一原语 `nand(a, b)` 出发，自底向上搭出一台能跑自编译程序的 16 位计算机，每一层都有独立的参考实现互相对拍：

- ✅ **97/97 测试全绿**（发布时重跑确认：`node --test` → 97 通过 / 0 失败，5.0 秒）：布尔门 → 加法器/ALU → 寄存器/RAM/PC → CPU/整机 → 汇编器 → 栈式 VM → 编译器 → 自举 OS → 端到端
- ✅ **约 11,000 个随机程序**走「编译→汇编→整机」与「解释器直跑」双路径对拍，零失败（交付记录；发布时抽查 300 个，同样零失败）
- ✅ 两个演示跑通：七段数码管记分的弹球游戏、64×64×10 代的康威生命游戏
- ✅ 十章书稿《从 NAND 到操作系统》，如实记录开发中抓出的 **8 个真 bug**（含 ±32768 比较器溢出、`let a[i]=a[n]` 指针别名、除法回绕死循环）
- ✅ 五个交互实验室（NAND / 加法器 / ALU / CPU 单步 / 弹球）

**🔁 这个案例说明了什么**

1. **没有计时器**，这个委托会在"跑通一个演示"的时候就结束——那大概值 40 分钟。
2. **有了计时器**，12 小时变成了**可验收的下限**：每一轮都要回答"这轮让哪个指标动了"，于是压力从"快点交"变成"别停在没有证据的地方"。
3. **代价是可见的**：633 次工具调用、97 个测试、11,000 个随机程序、8 个真 bug——这些都不是"再想想"能凭空长出来的，是时间被真实填满的结果。

---

## 🧩 与相邻工具的区别

| | 它是什么 | 什么时候用 |
|---|---|---|
| ⏱️ **Timer（本 skill）** | 时间要求的**状态机** | "必须干满 X / 干到 Y 才收工" |
| ⏰ Cron / 定时任务 | **触发器**，到点唤醒 agent | "每 20 分钟起来看一次" |
| 📋 Todo / 计划 | **任务分解** | "先做什么后做什么" |
| 🧪 测试 / CI | **正确性闸门** | "这个改动有没有破坏什么" |

它们互补：Timer 管**够不够久**，Cron 管**什么时候开始**，Todo 管**做哪些**，测试管**对不对**。

---

## ❓ FAQ

**Q：它会不会让 agent 白等 12 小时？**
不会。`SKILL.md` 明确禁止 sleep / 轮询 / 挂后台等钟点——那是最容易犯、也最没价值的作弊。时间只能花在真实工作上，否则等于违规。

**Q：早干完了怎么办？**
早到不早交。剩余时间用来复查、找 bug、做泛化、加更严的测量；这也是它和"倒计时"的根本区别。

**Q：跨平台吗？有依赖吗？**
纯标准库 Python 3.10+，Windows / macOS / Linux 都跑。⚠️ 某些 Windows 环境下 `python3` 是坏掉的 stub，用 `python` 或指定解释器绝对路径。

**Q：CLI 输出是中文，换到英文系统会乱码吗？**
人类可读的提示是中文；机器可读的字段名是英文，`--json` 可以直接接脚本。旧版 Windows 控制台若显示乱码，先 `chcp 65001` 切到 UTF-8（脚本本身已强制以 UTF-8 写 stdout，CI 里 6 个平台组合都在验证这一点）。

**Q：多个 harness 同时用会打架吗？**
不会。状态按 `*_SESSION_ID` 隔离；同一会话内用 `--name` 区分任务。没有 session id 的环境会落到 `global`，记得给每个任务起不同 `--name`。

**Q：状态文件会越积越多吗？**
不会。14 天未更新的自动清理，崩溃残留的临时文件一天后清理。

**Q：这算不算"硬凑时长"？**
不算。它约束的是**交付时机**，不是**产出质量**；质量靠你自己的验收标准和测试，二者叠加才有效。

---

## 📁 仓库结构

```text
timer-skill/
├── README.md            # 中文说明（你正在看）
├── README.en.md         # English
├── SKILL.md             # 给模型读的行为规范（交付闸门写在这里）
├── scripts/
│   └── clock.py         # 计时器实现，纯标准库，无依赖
├── tests/
│   └── test_clock.py    # 14 个可移植测试（子进程 + 隔离状态目录）
├── .github/workflows/
│   └── ci.yml           # Ubuntu / macOS / Windows × Python 3.10 / 3.13
└── LICENSE              # MIT
```

## ✅ 自测

```bash
python -m unittest discover -s tests -v
```

测试全部跑在 `DSH_TIMER_STATE` 指向的临时目录里，不碰你正在用的计时器，也不依赖机器的时钟或路径。

---

## 📄 License

[MIT](LICENSE) © 2026 wayleon li (233333hi)

<div align="center">

**⏱️ 时间是对努力的下限，不是对耐心的考验。**

</div>
