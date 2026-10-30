#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clock.py — 工时计时器（Claude Code 技能 timer）

用途：给一个任务设定「时间要求」，干活期间随时查还剩多少，**达标了才交付**。
这不是调度器：它不触发任何东西，只是把「必须干满多长时间 / 干到几点」变成可查的状态。

两个动作:
  now [--json] [--name N]        查看当前时间 + 当前任务的时间进度
  set <SPEC> [--json] [--name N] 设定本次任务的时间要求

SPEC（本地时区）:
  最短工时  20m | 1h30m | 90s | 45m      —— 从现在起必须干满这么久
  截止时刻  until 18:00 | by 18:00       —— 必须干到这个钟点
            until 18:00 tomorrow | until 09:00 +1d

状态按会话隔离（CLAUDE_CODE_SESSION_ID / DSH_SESSION_ID / 其他 *_SESSION_ID），默认名 "default"；--name 可并存多个计时器。
状态文件不在技能目录内：%LOCALAPPDATA%/dsh-skill-timer（可用 DSH_TIMER_STATE 覆盖），超过 14 天的旧文件自动清理。
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_DUR_TOKEN = re.compile(r"(\d+)\s*([smhd])", re.I)
_CLOCK_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
_DAY_OFFSET = re.compile(r"^\+(\d+)d$", re.I)

_LEGACY_STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "state")


def _state_dir():
    """Timer state lives OUTSIDE the skill directory (a per-user cache dir)."""
    override = os.environ.get("DSH_TIMER_STATE")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "dsh-skill-timer")
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "dsh-skill-timer")


_STATE_DIR = _state_dir()
_STALE_DAYS = 14


def _migrate_legacy():
    """Move timers written by older versions out of the skill directory, then drop it."""
    if not os.path.isdir(_LEGACY_STATE_DIR):
        return
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        for fn in os.listdir(_LEGACY_STATE_DIR):
            if not fn.endswith(".json"):
                continue
            src = os.path.join(_LEGACY_STATE_DIR, fn)
            dst = os.path.join(_STATE_DIR, fn)
            if os.path.exists(dst):
                continue
            try:
                os.replace(src, dst)
            except OSError:
                pass
        for fn in os.listdir(_LEGACY_STATE_DIR):    # leftovers: never keep state in the skill dir
            try:
                os.remove(os.path.join(_LEGACY_STATE_DIR, fn))
            except OSError:
                pass
        try:
            os.rmdir(_LEGACY_STATE_DIR)
        except OSError:
            pass
    except OSError:
        pass


def _prune_stale():
    """Delete timers untouched for _STALE_DAYS so state never accumulates."""
    try:
        cutoff = time.time() - _STALE_DAYS * 86400
        tmp_cutoff = time.time() - 86400
        for fn in os.listdir(_STATE_DIR):
            p = os.path.join(_STATE_DIR, fn)
            if fn.endswith(".tmp"):
                try:
                    if os.path.getmtime(p) < tmp_cutoff:    # crash leftovers, not live writes
                        os.remove(p)
                except OSError:
                    pass
                continue
            if not fn.endswith(".json"):
                continue
            try:
                if os.path.getmtime(p) < cutoff:
                    os.remove(p)
            except OSError:
                pass
    except OSError:
        pass

def _fail(msg):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(2)


# ---------------------------------------------------------------- 解析

def parse_duration(text):
    """'20m' / '1h30m' / 'in 20m' -> 秒；失败 None。"""
    body = text.strip().lower()
    if body.startswith("in "):
        body = body[3:].strip()
    if not body:
        return None
    if _DUR_TOKEN.sub("", body).strip():      # 有剩余字符 -> 不是纯时长
        return None
    total, matched = 0, 0
    for num, unit in _DUR_TOKEN.findall(body):
        total += int(num) * _UNIT_SECONDS[unit.lower()]
        matched += 1
    return total if matched else None


def parse_clock_time(text):
    m = _CLOCK_TIME.match(text.strip())
    if not m:
        return None
    h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if not (0 <= h <= 23 and 0 <= mi <= 59 and 0 <= s <= 59):
        return None
    return h, mi, s


def spec_to_target(spec, now):
    """把规格解析为 (target_datetime, kind, 说明)。"""
    text = spec.strip()
    low = text.lower()

    # ---- 截止时刻
    m = re.match(r"^(until|by|till|到|截至)\s+(.+)$", low)
    if m:
        rest = m.group(2).strip().split()
        hms = parse_clock_time(rest[0])
        if hms is None:
            _fail("无法解析截止时刻: %r" % rest[0])
        target = now.replace(hour=hms[0], minute=hms[1], second=hms[2],
                             microsecond=0)
        day_kw = rest[1].lower() if len(rest) > 1 else None
        auto_rolled = False
        try:
            if day_kw == "tomorrow":
                target += timedelta(days=1)
            elif day_kw:
                mo = _DAY_OFFSET.match(day_kw)
                if not mo:
                    _fail("无法识别的日修饰: %r" % day_kw)
                target += timedelta(days=int(mo.group(1)))
            while target <= now:             # 过点/顺延后再校验
                target += timedelta(days=1)
                auto_rolled = True
        except OverflowError:
            _fail("时间超出可表示范围: %r" % spec)
        return target, "deadline", ("已顺延到次日" if auto_rolled else "")

    # ---- 最短工时
    secs = parse_duration(text)
    if secs is not None:
        if secs <= 0:
            _fail("工时必须大于 0: %r" % spec)
        try:
            return now + timedelta(seconds=secs), "duration", ""
        except OverflowError:                # e.g. '999999999d' overflows datetime
            _fail("时间超出可表示范围: %r" % spec)

    _fail("无法解析: %r（支持 '20m' 或 'until 18:00'）" % spec)


# ---------------------------------------------------------------- 状态

# Session identity: every harness exports its own id. Without one, all sessions
# share the "global" key and can read/overwrite each other's timers.
_SESSION_ENV = (
    "CLAUDE_CODE_SESSION_ID",   # Claude Code
    "DSH_SESSION_ID",           # DeepSeek Harness
    "CODEX_THREAD_ID",          # Codex CLI
    "CODEX_SESSION_ID",
    "OPENCODE_SESSION_ID",
    "GEMINI_SESSION_ID",
    "CURSOR_SESSION_ID",
    "COPILOT_SESSION_ID",
    "QWEN_SESSION_ID",
)


def _session_key():
    for var in _SESSION_ENV:
        val = os.environ.get(var)
        if val:
            return val
    for key, val in os.environ.items():     # any other harness: <X>_SESSION_ID
        if key.endswith("_SESSION_ID") and val:
            return val
    return "global"


def _state_path(name):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", "%s__%s" % (_session_key(), name))
    return os.path.join(_STATE_DIR, safe + ".json")


def _parse_stamp(text):
    """Parse a stored timestamp; a naive one (pre-upgrade state) is read as local."""
    stamp = datetime.fromisoformat(text)
    return stamp if stamp.tzinfo else stamp.astimezone()


def _load(name):
    p = _state_path(name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        _parse_stamp(data["start"])
        _parse_stamp(data["target"])
        data["spec"], data["kind"]          # required fields; a corrupt file reads as "no timer"
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _save(name, data):
    path = _state_path(name)
    tmp = path + ".tmp"
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)               # atomic: a killed process never leaves half a timer
    except OSError as exc:
        try:
            os.remove(tmp)
        except OSError:
            pass
        _fail("无法写入计时器状态（%s）: %s" % (_STATE_DIR, exc))


def _clear(name):
    p = _state_path(name)
    if os.path.exists(p):
        os.remove(p)
        return True
    return False


def _human(secs):
    secs = int(secs)
    sign = "-" if secs < 0 else ""
    secs = abs(secs)
    parts = []
    for unit, size in (("天", 86400), ("小时", 3600), ("分", 60), ("秒", 1)):
        if secs >= size:
            n, secs = divmod(secs, size)
            parts.append("%d%s" % (n, unit))
    return sign + ("".join(parts) or "0秒")


def _progress(timer, now):
    start = _parse_stamp(timer["start"])
    target = _parse_stamp(timer["target"])
    elapsed = (now - start).total_seconds()
    remaining = (target - now).total_seconds()
    return {
        "name": timer.get("name", "default"),
        "spec": timer["spec"],
        "kind": timer["kind"],
        "start": start.isoformat(timespec="seconds"),
        "target": target.isoformat(timespec="seconds"),
        "elapsed_seconds": int(elapsed),
        "elapsed": _human(elapsed),
        "remaining_seconds": int(remaining),
        "remaining": _human(remaining),
        "satisfied": remaining <= 0,
    }


# ---------------------------------------------------------------- 动作

def _now_dt():
    return datetime.now().astimezone()


def action_now(name, as_json):
    now = _now_dt()
    timer = _load(name)
    info = {
        "now": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
        "utc_offset": now.strftime("%z"),
        "session": _session_key(),
        "state_dir": _STATE_DIR,
    }
    if timer:
        info["timer"] = _progress(timer, now)

    if as_json:
        print(json.dumps(info, ensure_ascii=False, indent=1))
        return

    print("现在：%s %s (%s, UTC%s)"
          % (info["date"], info["time"], info["weekday"], info["utc_offset"]))
    if not timer:
        print("计时器：未设定")
        return
    t = info["timer"]
    state = "✅ 已达标，可以交付" if t["satisfied"] else "⏳ 未达标，继续干"
    print("计时器：%s | 要求 %s | 已用 %s | 剩 %s | %s"
          % (t["spec"], "截止 " + t["target"] if t["kind"] == "deadline"
             else "工时 " + _human(t["remaining_seconds"] + t["elapsed_seconds"]),
             t["elapsed"], t["remaining"], state))


def action_set(spec, name, as_json):
    if name == "off" or spec.strip().lower() in ("off", "clear", "取消"):
        removed = _clear(name if name != "off" else "default")
        print(json.dumps({"cleared": removed}, ensure_ascii=False) if as_json
              else ("已取消计时器" if removed else "没有正在跑的计时器"))
        return
    now = _now_dt()
    target, kind, note = spec_to_target(spec, now)
    total = (target - now).total_seconds()
    data = {"name": name, "spec": spec.strip(), "kind": kind,
            "start": now.isoformat(timespec="seconds"),
            "target": target.isoformat(timespec="seconds"),
            "session": _session_key()}
    _save(name, data)
    if as_json:
        print(json.dumps(_progress(data, now), ensure_ascii=False, indent=1))
        return
    label = ("截止 %s" % target.strftime("%Y-%m-%d %H:%M:%S")) if kind == "deadline" \
        else ("必须干满 %s" % _human(total))
    print("计时器已设定（%s）：%s；从现在到目标 %s%s"
          % (name, label, target.strftime("%Y-%m-%d %H:%M:%S"),
             "（" + note + "）" if note else ""))


def main():
    try:                                   # Windows 控制台默认 GBK，强制 UTF-8
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    _migrate_legacy()
    _prune_stale()

    ap = argparse.ArgumentParser(description="工时计时器：设定时间要求，达标才交付")
    ap.add_argument("--json", action="store_true", help="输出 JSON（也可写在子命令后）")
    ap.add_argument("--name", default="default", help="计时器名（可并存多个）")
    sub = ap.add_subparsers(dest="action", required=True)
    for nm, ht in (("now", "查看当前时间与任务进度"), ("set", "设定任务的时间要求")):
        sp = sub.add_parser(nm, help=ht)
        sp.add_argument("--json", action="store_true", dest="json_sub")
        sp.add_argument("--name", default=None, dest="name_sub")
        if nm == "set":
            sp.add_argument("spec", nargs="+",
                            help="如 '20m' / 'until 18:00' / 'off'")
    args = ap.parse_args()
    as_json = args.json or getattr(args, "json_sub", False)
    name = getattr(args, "name_sub", None) or args.name

    if args.action == "now":
        action_now(name, as_json)
    else:
        action_set(" ".join(args.spec), name, as_json)


if __name__ == "__main__":
    main()
