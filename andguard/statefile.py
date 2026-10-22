"""状态文件：原子写入 ~/.andguard/state/state.json，动作流水 actions.jsonl。"""
import json
import os
import time

STATE_DIR = os.path.expanduser("~/.andguard/state")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
ACTIONS_LOG = os.path.join(STATE_DIR, "actions.jsonl")


def _ensure():
    os.makedirs(STATE_DIR, exist_ok=True)


def load() -> dict:
    _ensure()
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save(state: dict):
    _ensure()
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)  # 原子替换


def log_action(action: str, detail: str = "", dry_run: bool = False):
    _ensure()
    rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "action": action,
           "detail": detail, "dry_run": dry_run}
    with open(ACTIONS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
