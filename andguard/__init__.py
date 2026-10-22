"""andguard — 安卓手机 CPU/内存智能治理（温和、可逆、不误杀）。

架构参照 macOS 版 sysguard，翻译到 Android：
  原语        macOS sysguard           Android andguard
  降权/后台   taskpolicy -b/-B        cmd appops RUN_IN_BACKGROUND ignore/allow
  挂起可恢复  SIGSTOP / SIGCONT       am force-stop + appops ignore（轻挂起）
                                      pm disable-user / pm enable（重冻结）
  内存        purge + 挂大户          pm trim-caches + force-stop 后台大户
  通报        notify                 log 通报，绝不 kill 系统进程

本包导出命令行入口 `main()`，供 cli.py / daemon.py 使用。
"""

__version__ = "0.1.0"
