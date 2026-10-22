"""规则引擎（对应 sysguard R1-R4，翻译到安卓动作）。

核心原则：温和治理、可逆、绝不自动 kill 系统进程。
只治理"可治理应用"（用户应用 − exclude），前台应用绝不触碰。
"""
import time

from .adb import ADB
from .sampler import mem_status, app_stats, running_pkgs
from .actions import Actions
from .registry import Registry
from . import statefile


class RuleEngine:
    def __init__(self, adb: ADB, cfg: dict):
        self.adb = adb
        self.cfg = cfg
        self.actions = Actions(adb, dry_run=cfg.get("dry_run", True))
        self.registry = Registry(adb, exclude=cfg.get("exclude", []))
        self.method = cfg.get("suspend_method", "appops")
        # 状态跟踪
        self._cpu_since = {}     # pkg -> first_hit_time
        self._cooldown_until = {}  # pkg -> time
        self._mem_hit_since = None
        self._notify_since = {}

    # ---------- 采样 ----------
    def snapshot(self) -> dict:
        fg = self.adb.foreground_pkg()
        mem = mem_status(self.adb)
        apps = app_stats(self.adb)
        return {"fg": fg, "mem": mem, "apps": apps}

    # ---------- 单轮评估 ----------
    def evaluate(self) -> list:
        """返回本轮动作日志列表；dry_run 时全部带 [DRYRUN]。"""
        snap = self.snapshot()
        fg = snap["fg"]
        mem = snap["mem"]
        apps = snap["apps"]
        managed = set(self.registry.manageable())
        running = running_pkgs(self.adb) | {a["pkg"] for a in apps}
        log = []
        now = time.time()

        # 前台应用不做任何动作
        targets = [a for a in apps if a["pkg"] in managed and a["pkg"] != fg]

        # ---- R1 后台冻结：后台高 CPU 持续 → 挂起(appops ignore) ----
        r1 = self.cfg["rules"]["r1_bg_freeze"]
        if r1.get("enable", True):
            for a in targets:
                p = a["pkg"]
                if a["cpu"] >= r1["cpu_pct"]:
                    if p not in self._cpu_since:
                        self._cpu_since[p] = now
                    elif now - self._cpu_since[p] >= r1["duration_sec"]:
                        if now >= self._cooldown_until.get(p, 0):
                            log.append(self._suspend(p, f"R1 后台CPU {a['cpu']}% 持续≥{r1['duration_sec']}s"))
                            self._cooldown_until[p] = now + r1["cooldown_min"] * 60
                else:
                    self._cpu_since.pop(p, None)

        # ---- R2 挂起：后台整树累计高 → 重度挂起(freeze) ----
        r2 = self.cfg["rules"]["r2_suspend"]
        if r2.get("enable", True):
            for a in targets:
                p = a["pkg"]
                if a["cpu"] >= r2["cpu_pct"] and p in running:
                    if p not in self._cpu_since:
                        self._cpu_since[p] = now
                    elif now - self._cpu_since[p] >= r2["duration_sec"]:
                        if now >= self._cooldown_until.get(p, 0):
                            log.append(self._freeze(p, f"R2 后台整树CPU {a['cpu']}% 持续≥{r2['duration_sec']}s"))
                            self._cooldown_until[p] = now + r2["cooldown_min"] * 60

        # ---- R3 内存：avail 过低 → 清缓存 + 挂最大后台应用 ----
        r3 = self.cfg["rules"]["r3_memory"]
        warn, crit, persist = r3["warn_pct"], r3["critical_pct"], r3["persist_sec"]
        if mem["avail_pct"] <= crit:
            if self._mem_hit_since is None:
                self._mem_hit_since = now
            elif now - self._mem_hit_since >= persist:
                if targets:
                    big = max(targets, key=lambda x: x["mem"])
                    log.append(self._suspend(big["pkg"], f"R3 内存告急(可用{mem['avail_pct']}%)→挂起内存最大后台应用{big['mem']}%"))
                log.append(self.actions.trim_caches(self.cfg["limits"]["trim_caches_gb"]))
                self._mem_hit_since = None
        elif mem["avail_pct"] <= warn:
            self._mem_hit_since = self._mem_hit_since or now  # 只积累，告急才动手
        else:
            self._mem_hit_since = None

        # ---- R4 通报：任意进程超高 → 仅记录，绝不 kill ----
        r4 = self.cfg["rules"]["r4_notify"]
        if r4.get("cpu_pct"):
            for a in apps:
                if a["cpu"] >= r4["cpu_pct"]:
                    if a["pkg"] not in self._notify_since:
                        self._notify_since[a["pkg"]] = now
                    elif now - self._notify_since[a["pkg"]] >= r4["persist_min"] * 60:
                        if now >= self._cooldown_until.get("notify:" + a["pkg"], 0):
                            log.append(f"[NOTIFY] {a['pkg']} CPU {a['cpu']}% 持续≥{r4['persist_min']}分钟（仅通报）")
                            self._cooldown_until["notify:" + a["pkg"]] = now + r4["cooldown_min"] * 60
                else:
                    self._notify_since.pop(a["pkg"], None)

        # ---- R5 真正杀掉（默认关闭，手动启用后对失控后台应用真杀） ----
        r5 = self.cfg["rules"]["r5_kill"]
        if r5.get("enable", False):
            for a in targets:
                p = a["pkg"]
                if a["cpu"] >= r5["cpu_pct"]:
                    if p not in self._cpu_since:
                        self._cpu_since[p] = now
                    elif now - self._cpu_since[p] >= r5["duration_sec"]:
                        if now >= self._cooldown_until.get(p, 0):
                            log.append(self.actions.kill(p) + f"  (R5 失控CPU {a['cpu']}%)")
                            self._cooldown_until[p] = now + r5["cooldown_min"] * 60
                else:
                    self._cpu_since.pop(p, None)

        # 写动作流水 + 状态
        for lg in log:
            statefile.log_action(lg, dry_run=self.cfg.get("dry_run", True))
        statefile.save({"t": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "fg": fg, "mem": mem, "managed": sorted(managed),
                        "last_actions": log})
        return log

    # ---------- 挂起执行 ----------
    def _suspend(self, pkg: str, why: str) -> str:
        """轻挂起：先 force-stop 当前实例，再 appops 禁止后台。"""
        if self.method == "freeze":
            return self._freeze(pkg, why)
        s = self.actions.force_stop(pkg)
        b = self.actions.suspend_appops(pkg)
        return f"[{pkg}] {why} :: {s} ; {b}"

    def _freeze(self, pkg: str, why: str) -> str:
        """重挂起：pm disable-user 完全冻结。"""
        return self.actions.freeze(pkg) + f"  ({why})"
