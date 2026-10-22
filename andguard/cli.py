"""命令行入口：andguard status/top/apps/suspend/resume/freeze/unfreeze/kill/uninstall/optimize/scan/config/doctor/daemon"""
import argparse
import os
import subprocess
import sys

from .adb import ADB, ADBError
from .config import load as load_config, CONFIG_PATH
from .sampler import mem_status, app_stats, third_party_pkgs, running_pkgs
from .actions import Actions


def _adb(cfg) -> ADB:
    return ADB(serial=cfg.get("device", ""))


def _need_dev(cfg) -> ADB:
    a = _adb(cfg)
    try:
        a.resolve()
    except ADBError as e:
        print("✗ " + str(e)); sys.exit(1)
    return a


def _resolve_pkg(a, raw):
    raw = (raw or "").strip()
    if not raw:
        print("需要指定包名或关键字"); sys.exit(1)
    if "." in raw:
        return raw
    user = third_party_pkgs(a)
    hit = [p for p in user if raw.lower() in p.lower()]
    if len(hit) == 1:
        return hit[0]
    if len(hit) > 1:
        print(f"匹配到多个: {hit}，请指定完整包名"); sys.exit(1)
    return raw


def _guard(cfg, pkg, force):
    """exclude 保护名单兜底，除非 --force。"""
    if not force and pkg in cfg.get("exclude", []):
        print(f"✗ {pkg} 在 exclude 保护名单（核心应用），如需操作请加 --force"); sys.exit(1)


def cmd_status(args):
    cfg = load_config(); a = _need_dev(cfg)
    fg = a.foreground_pkg(); mem = mem_status(a); apps = app_stats(a)
    act = Actions(a, dry_run=True)
    print("=" * 56)
    print(f"设备 {a.resolve()}  前台: {fg or '(桌面/无)'}")
    used_g = (mem['total_mb']-mem['avail_mb'])/1024; total_g = mem['total_mb']/1024; avail_g = mem['avail_mb']/1024
    print(f"内存 已用 {used_g:.1f}G/{total_g:.1f}G · 可用 {avail_g:.1f}G ({mem['avail_pct']}%) · Swap 已用 {mem['swap_used_mb']}M")
    bg = act.get_bg_process_limit()
    print(f"后台进程上限: {bg if bg not in ('', 'null') else '(未设置)'}   dry_run: {cfg.get('dry_run')}")
    print("-" * 56)
    print("当前 CPU Top10 应用:")
    for r in apps[:10]:
        mark = " ◀前台" if r["pkg"] == fg else ""
        print(f"  {r['cpu']:>6.1f}%  MEM {r['mem']:>5.1f}%  {r['pkg']}{mark}")
    print("=" * 56)


def cmd_top(args):
    a = _need_dev(load_config())
    print(f"{'CPU%':>7} {'MEM%':>6} {'进程':>4}  包名")
    for r in app_stats(a)[:20]:
        print(f"{r['cpu']:>7.1f} {r['mem']:>6.1f} {r['procs']:>4}  {r['pkg']}")


def cmd_apps(args):
    a = _need_dev(load_config())
    user = third_party_pkgs(a); running = running_pkgs(a)
    print(f"用户安装 {len(user)} 个，其中运行中 {len(running & set(user))} 个：")
    for p in sorted(user):
        print(f"  {p}{'  ●运行中' if p in running else ''}")


def cmd_suspend(args):
    cfg = load_config(); a = _need_dev(cfg); pkg = _resolve_pkg(a, args.pkg)
    _guard(cfg, pkg, args.force)
    act = Actions(a, dry_run=args.dry_run)
    print(act.force_stop(pkg)); print(act.suspend_appops(pkg))


def cmd_freeze(args):
    cfg = load_config(); a = _need_dev(cfg); pkg = _resolve_pkg(a, args.pkg)
    _guard(cfg, pkg, args.force)
    act = Actions(a, dry_run=args.dry_run)
    print(act.freeze(pkg))


def cmd_unfreeze(args):
    a = _need_dev(load_config()); pkg = _resolve_pkg(a, args.pkg)
    act = Actions(a, dry_run=args.dry_run)
    print(act.unfreeze(pkg))


def cmd_resume(args):
    cfg = load_config(); a = _need_dev(cfg)
    act = Actions(a, dry_run=args.dry_run)
    if args.pkg in ("all", ""):
        for p in third_party_pkgs(a):
            st = act.appops_state(p)
            if "ignore" in st:
                print(act.resume_appops(p))
            if act.is_disabled(p):
                print(act.unfreeze(p))
        print("已恢复全部可治理应用。")
    else:
        pkg = _resolve_pkg(a, args.pkg)
        print(act.resume_appops(pkg)); print(act.unfreeze(pkg))


def cmd_kill(args):
    cfg = load_config(); a = _need_dev(cfg); pkg = _resolve_pkg(a, args.pkg)
    _guard(cfg, pkg, args.force)
    act = Actions(a, dry_run=args.dry_run)
    print(act.kill(pkg))


def cmd_uninstall(args):
    cfg = load_config(); a = _need_dev(cfg); pkg = _resolve_pkg(a, args.pkg)
    _guard(cfg, pkg, args.force)
    if not args.yes:
        print(f"⚠ 即将彻底卸载 {pkg}（不可逆）。确认请加 --yes"); return
    act = Actions(a, dry_run=args.dry_run)
    print(act.uninstall(pkg))


def cmd_optimize(args):
    cfg = load_config(); a = _need_dev(cfg)
    # optimize 遵循配置 dry_run（观察期只记录），可用 --dry-run 强制观察
    eff_dry = args.dry_run or cfg.get("dry_run", True)
    act = Actions(a, dry_run=eff_dry)
    n = cfg["limits"]["background_process_limit"]
    if n >= 0:
        print(act.set_bg_process_limit(n))
    print(act.trim_caches(cfg["limits"]["trim_caches_gb"]))
    fg = a.foreground_pkg()
    user = set(third_party_pkgs(a)); ex = set(cfg.get("exclude", [])); running = running_pkgs(a)
    for p in sorted(user - ex):
        if p == fg or p not in running:
            continue
        print(act.suspend_appops(p))
    print("优化完成。" + ("（dry_run 观察期，未实际治理）" if eff_dry else ""))


def cmd_scan(args):
    a = _need_dev(load_config())
    print(", ".join(sorted(set(third_party_pkgs(a)) - set(load_config().get("exclude", [])))))


def cmd_config(args):
    if args.edit:
        if not os.path.exists(CONFIG_PATH):
            print(f"先创建配置：mkdir -p {os.path.dirname(CONFIG_PATH)} && cp 示例 config.example.yaml {CONFIG_PATH}")
        subprocess.call([os.environ.get("EDITOR", "vi"), CONFIG_PATH])
    else:
        print(f"配置路径: {CONFIG_PATH}（未生成时用内置默认 + dry_run）")


def cmd_doctor(args):
    cfg = load_config(); a = _need_dev(cfg)
    print(f"adb: {a.adb_bin}  设备: {a.resolve()}")
    print(f"系统: Android {a.getprop('ro.build.version.release')} / {a.getprop('ro.product.model')}")
    print(f"前台检测: {a.foreground_pkg() or '(无前台/桌面)'}")
    if args.selftest:
        pkg = args.pkg or (next(iter(third_party_pkgs(a)), None))
        if not pkg:
            print("无可用测试应用"); return
        act = Actions(a, dry_run=False)
        print(f"-- 用 {pkg} 做原语自测（测完即恢复） --")
        print("① force-stop:", act.force_stop(pkg))
        print("② appops 挂起:", act.suspend_appops(pkg), "->", act.appops_state(pkg))
        print("③ appops 恢复:", act.resume_appops(pkg), "->", act.appops_state(pkg))
        print("④ pm disable:", act.freeze(pkg), "->", act.is_disabled(pkg))
        print("⑤ pm enable:", act.unfreeze(pkg), "->", act.is_disabled(pkg))
        print("✅ 原语自测完成。")


def cmd_daemon(args):
    from .daemon import run_daemon
    cfg = load_config()
    run_daemon(cfg, once=args.once, interval=cfg.get("poll_interval", 3))


def main(argv=None):
    p = argparse.ArgumentParser(prog="andguard", description="安卓手机 CPU/内存智能治理（温和、可逆）")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("top").set_defaults(fn=cmd_top)
    sub.add_parser("apps").set_defaults(fn=cmd_apps)

    sp = sub.add_parser("suspend"); sp.add_argument("pkg"); sp.add_argument("--force", action="store_true"); sp.add_argument("--dry-run", action="store_true"); sp.set_defaults(fn=cmd_suspend)
    sp = sub.add_parser("freeze"); sp.add_argument("pkg"); sp.add_argument("--force", action="store_true"); sp.add_argument("--dry-run", action="store_true"); sp.set_defaults(fn=cmd_freeze)
    sp = sub.add_parser("unfreeze"); sp.add_argument("pkg"); sp.add_argument("--dry-run", action="store_true"); sp.set_defaults(fn=cmd_unfreeze)
    sp = sub.add_parser("resume"); sp.add_argument("pkg", nargs="?", default="all"); sp.add_argument("--dry-run", action="store_true"); sp.set_defaults(fn=cmd_resume)
    sp = sub.add_parser("kill"); sp.add_argument("pkg"); sp.add_argument("--force", action="store_true"); sp.add_argument("--dry-run", action="store_true"); sp.set_defaults(fn=cmd_kill)
    sp = sub.add_parser("uninstall"); sp.add_argument("pkg"); sp.add_argument("--yes", action="store_true"); sp.add_argument("--force", action="store_true"); sp.add_argument("--dry-run", action="store_true"); sp.set_defaults(fn=cmd_uninstall)
    sp = sub.add_parser("optimize"); sp.add_argument("--dry-run", action="store_true"); sp.set_defaults(fn=cmd_optimize)
    sub.add_parser("scan").set_defaults(fn=cmd_scan)
    sp = sub.add_parser("config"); sp.add_argument("-e", "--edit", action="store_true"); sp.set_defaults(fn=cmd_config)
    sp = sub.add_parser("doctor"); sp.add_argument("--selftest", action="store_true"); sp.add_argument("--pkg"); sp.set_defaults(fn=cmd_doctor)
    sp = sub.add_parser("daemon"); sp.add_argument("--once", action="store_true"); sp.set_defaults(fn=cmd_daemon)

    args = p.parse_args(argv)
    if not getattr(args, "fn", None):
        p.print_help(); return
    args.fn(args)


if __name__ == "__main__":
    main()
