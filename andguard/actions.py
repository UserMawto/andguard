"""动作执行器：挂起/恢复/冻结/停止/内存治理。

所有动作可逆、可查状态，并写入动作流水（供 statefile 消费）。
"""
from .adb import ADB


class Actions:
    def __init__(self, adb: ADB, dry_run: bool = True):
        self.adb = adb
        self.dry_run = dry_run

    # ---------- 挂起/恢复（轻：appops 后台冻结，前台打开仍可用） ----------
    def suspend_appops(self, pkg: str) -> str:
        return self._exec(f"cmd appops set {pkg} RUN_IN_BACKGROUND ignore",
                          f"SUSPEND {pkg} (appops 后台冻结)")

    def resume_appops(self, pkg: str) -> str:
        return self._exec(f"cmd appops set {pkg} RUN_IN_BACKGROUND allow",
                          f"RESUME {pkg} (appops 解除后台冻结)")

    def appops_state(self, pkg: str) -> str:
        try:
            out = self.adb.shell(f"cmd appops get {pkg} RUN_IN_BACKGROUND")
            return out.strip().lower()
        except Exception:
            return ""

    # ---------- 停止当前实例 ----------
    def force_stop(self, pkg: str) -> str:
        return self._exec(f"am force-stop {pkg}", f"STOP {pkg} (force-stop)")

    def kill_bg(self, pkg: str) -> str:
        return self._exec(f"am kill {pkg}", f"KILLBG {pkg} (kill background)")

    # ---------- 冻结/解冻（重：pm disable-user，完全停用可恢复） ----------
    def freeze(self, pkg: str) -> str:
        return self._exec(f"pm disable-user --user 0 {pkg}", f"FREEZE {pkg} (pm disable-user)")

    def unfreeze(self, pkg: str) -> str:
        return self._exec(f"pm enable {pkg}", f"UNFREEZE {pkg} (pm enable)")

    def is_disabled(self, pkg: str) -> bool:
        try:
            out = self.adb.shell("pm list packages -d")
            return f"package:{pkg}" in out
        except Exception:
            return False

    # ---------- 真正杀掉 ----------
    def kill(self, pkg: str) -> str:
        """真正终止应用所有进程（force-stop）。比挂起/冻结更狠。"""
        return self._exec(f"am force-stop {pkg}", f"KILL {pkg} (force-stop 真正终止)")

    def kill_all_bg(self) -> str:
        return self._exec("am kill-all", "KILL-ALL 全部后台进程")

    def uninstall(self, pkg: str) -> str:
        """彻底卸载（从系统移除，不可逆）。用户安装应用适用。"""
        return self._exec(f"pm uninstall --user 0 {pkg}", f"UNINSTALL {pkg} (彻底卸载)")

    # ---------- 内存治理 ----------
    def trim_caches(self, keep_gb: int) -> str:
        return self._exec(f"pm trim-caches {keep_gb}G", f"TRIM 缓存(保留{keep_gb}G)")

    def set_bg_process_limit(self, n: int) -> str:
        """全局后台进程上限；n=-1 表示恢复默认(不设)。"""
        if n < 0:
            return self._exec("settings put global background_process_limit 4",
                              "BG-LIMIT 恢复默认(4)")
        return self._exec(f"settings put global background_process_limit {n}",
                          f"BG-LIMIT 后台进程上限={n}")

    def get_bg_process_limit(self) -> str:
        try:
            return self.adb.shell("settings get global background_process_limit").strip()
        except Exception:
            return "?"

    # ---------- 统一入口 ----------
    def _exec(self, cmd: str, label: str) -> str:
        if self.dry_run:
            return f"[DRYRUN] {label} -> 未执行"
        try:
            self.adb.shell(cmd)
            return f"[OK] {label}"
        except Exception as e:
            return f"[FAIL] {label} :: {e}"
