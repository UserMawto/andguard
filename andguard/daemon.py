"""daemon：常驻治理循环（对应 sysguard daemon）。

每 poll_interval 秒：采样 → 评估规则 → 执行动作 → 写状态。
SIGTERM 时先恢复全部，避免手机被"冻"住。
"""
import signal
import sys
import time

from .adb import ADB
from .rules import RuleEngine
from .actions import Actions
from .sampler import third_party_pkgs
from . import statefile


class _Halt(Exception):
    pass


def run_daemon(cfg: dict, once: bool = False, interval: int = 3):
    adb = ADB(serial=cfg.get("device", ""))
    try:
        adb.resolve()
    except Exception as e:
        print("✗ " + str(e)); sys.exit(1)

    eng = RuleEngine(adb, cfg)
    stopped = []

    def _sigterm(*_):
        _restore_all(adb, cfg, stopped)
        raise _Halt()

    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)

    print(f"andguard daemon 启动 · 设备 {adb.resolve()} · dry_run={cfg.get('dry_run')} · 每{interval}s")
    try:
        while True:
            try:
                log = eng.evaluate()
                for l in log:
                    print(l)
            except Exception as e:
                print(f"[warn] 采样/执行异常: {e}")
            if once:
                print("(once 模式，执行一轮后退出)"); break
            time.sleep(interval)
    except _Halt:
        print("已收到停止信号，恢复全部后退出。")
    except KeyboardInterrupt:
        _restore_all(adb, cfg, stopped)
        print("手动中断，已恢复。")


def _restore_all(adb, cfg, stopped):
    act = Actions(adb, dry_run=False)
    try:
        for p in third_party_pkgs(adb):
            try:
                if "ignore" in act.appops_state(p):
                    act.resume_appops(p)
                if act.is_disabled(p):
                    act.unfreeze(p)
            except Exception:
                pass
        statefile.log_action("RESUME-ALL", "daemon 退出前恢复全部")
        print("已恢复全部可治理应用。")
    except Exception as e:
        print(f"恢复失败: {e}")
