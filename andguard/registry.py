"""受管应用白名单。

治理范围 = 用户安装的第三方应用 − 永不挂起的核心应用。
系统进程、华为自带应用默认不在治理范围（只通报）。
"""
from .sampler import third_party_pkgs
from .adb import ADB


class Registry:
    def __init__(self, adb: ADB, exclude: list = None):
        self.adb = adb
        self.exclude = set(exclude or [])

    def scan_user_apps(self) -> list:
        return third_party_pkgs(self.adb)

    def manageable(self) -> list:
        """可治理应用 = 用户应用 − exclude。"""
        return [p for p in self.scan_user_apps() if p not in self.exclude]

    def is_manageable(self, pkg: str) -> bool:
        return pkg in self.manageable()

    # 常见的"你未必想自动挂"的系统关键包，做额外保险
    SYSTEM_CRITICAL = {
        "com.tencent.mm", "com.eg.android.AlipayGphone",   # 消息/支付，仅当你配置了才动
    }
