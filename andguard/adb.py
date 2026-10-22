"""ADB 封装：设备选择、shell 执行、前台应用检测。

统一通过 `adb -s <serial> shell ...` 与手机交互。
序列号支持 USB（如 5EF7N18726000799）或无线（192.168.0.237:5555）。
"""
import shlex
import subprocess
import time


class ADBError(RuntimeError):
    pass


class ADB:
    def __init__(self, serial: str = "", adb_bin: str = "adb", timeout: int = 20):
        self.serial = serial
        self.adb_bin = adb_bin
        self.timeout = timeout

    # ---------- 设备 ----------
    def devices(self) -> list:
        """返回 [ (serial, state), ... ]"""
        out = self._run_local([self.adb_bin, "devices"])
        devs = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and not parts[0].startswith("List"):
                devs.append((parts[0], parts[1]))
        return devs

    def resolve(self) -> str:
        """确定要用的设备序列号；串参数优先，否则取唯一在线设备。"""
        if self.serial:
            return self.serial
        devs = self.devices()
        online = [s for s, st in devs if st == "device"]
        if not online:
            raise ADBError("未发现可用设备。请先连接手机（USB 或无线）并授权。")
        if len(online) > 1:
            raise ADBError(
                f"检测到多台设备 {online}，请用 device 配置指定，如 192.168.0.237:5555")
        return online[0]

    def _base(self) -> list:
        return [self.adb_bin, "-s", self.resolve()]

    # ---------- 本地执行 ----------
    def _run_local(self, argv: list) -> str:
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise ADBError("adb 命令超时: " + " ".join(argv))
        if r.returncode != 0:
            raise ADBError(f"adb 失败({r.returncode}): {r.stderr.strip() or r.stdout.strip()}")
        return r.stdout

    # ---------- 手机 shell ----------
    def shell(self, cmd: str) -> str:
        """执行手机侧命令，返回 stdout（去尾空白）。"""
        argv = self._base() + ["shell", cmd]
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise ADBError(f"手机命令超时: {cmd}")
        if r.returncode != 0 and "error" in (r.stdout + r.stderr).lower():
            # 多数情况手机命令失败也返回 0，这里仅兜底抛错
            raise ADBError(f"手机命令失败: {cmd} :: {r.stderr.strip() or r.stdout.strip()}")
        return r.stdout

    # ---------- 便捷查询 ----------
    def getprop(self, key: str) -> str:
        return self.shell(f"getprop {key}").strip()

    def foreground_pkg(self) -> str:
        """返回当前前台应用的包名；桌面/系统界面返回 ''。"""
        try:
            w = self.shell("dumpsys window 2>/dev/null | grep -iE 'mCurrentFocus|mFocusedApp'")
        except ADBError:
            return ""
        pkg = ""
        import re
        for line in w.splitlines():
            m = re.search(r'([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)+)/([a-zA-Z0-9_.]+)', line)
            if m:
                pkg = m.group(1)
                break
        # 前台是系统壳/桌面/设置 等，视为无前台应用
        if not pkg or pkg in ("com.android.systemui", "com.android.settings", "com.huawei.android.launcher",
                              "com.huawei.launcher", "com.android.launcher3", "com.huawei.permissionmanager"):
            return ""
        return pkg


def shell_quote(x: str) -> str:
    return shlex.quote(x)


def now() -> float:
    return time.time()
