"""采样器：内存 / CPU / 进程，全部来自 `adb shell`（无需 root）。"""
from .adb import ADB


def meminfo(adb: ADB) -> dict:
    """解析 /proc/meminfo，返回单位 MB 的字典。"""
    out = adb.shell("cat /proc/meminfo")
    m = {}
    for line in out.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip().split()
        kb = int(v[0]) if v else 0
        m[k] = kb // 1024
    return m


def mem_status(adb: ADB) -> dict:
    mi = meminfo(adb)
    total = mi.get("MemTotal", 0)
    avail = mi.get("MemAvailable", 0)
    free = mi.get("MemFree", 0)
    pct = (avail / total * 100) if total else 0
    return {
        "total_mb": total,
        "avail_mb": avail,
        "free_mb": free,
        "avail_pct": round(pct, 1),
        "swap_used_mb": mi.get("SwapTotal", 0) - mi.get("SwapFree", 0),
    }


def top_procs(adb: ADB) -> list:
    """解析 `top -b -n 1`，返回 [{pid,user,cpu,res,mem,name}]。"""
    out = adb.shell("top -b -n 1 2>/dev/null")
    procs = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 12:
            continue
        # top 列: PID USER PR NI VIRT RES SHR S %CPU %MEM TIME+ ARGS
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        user = parts[1]
        cpu = _num(parts[8])
        mem = _num(parts[9])
        res = parts[4]
        name = " ".join(parts[11:])
        procs.append({"pid": pid, "user": user, "cpu": cpu, "mem": mem,
                      "res": res, "name": name})
    return procs


def _num(s: str) -> float:
    try:
        return float(s.rstrip("%"))
    except ValueError:
        return 0.0


def app_stats(adb: ADB) -> list:
    """按应用包名聚合 CPU/内存。

    进程名即包名（Android 主进程 = 包名）；`:push` 等子进程并入主包。
    仅返回 CPU 或内存非 0 的应用，已按 CPU 降序。
    """
    agg = {}
    for p in top_procs(adb):
        name = p["name"]
        if "." not in name:
            continue
        base = name.split(":")[0]
        e = agg.setdefault(base, {"cpu": 0.0, "mem": 0.0, "procs": 0})
        e["cpu"] += p["cpu"]
        e["mem"] = max(e["mem"], p["mem"])
        e["procs"] += 1
    rows = []
    for pkg, e in agg.items():
        if e["cpu"] > 0 or e["mem"] > 0:
            rows.append({"pkg": pkg, "cpu": round(e["cpu"], 1),
                         "mem": round(e["mem"], 1), "procs": e["procs"]})
    rows.sort(key=lambda r: r["cpu"], reverse=True)
    return rows


def running_pkgs(adb: ADB) -> set:
    """当前正在运行的应用包名集合（来自 ps）。"""
    out = adb.shell("ps -A -o NAME 2>/dev/null")
    pkgs = set()
    for line in out.splitlines():
        name = line.strip()
        if "." not in name:
            continue
        base = name.split(":")[0]
        if base.startswith(("com.huawei", "com.android", "com.google", "android.")):
            continue
        if base.islower() and not base.startswith("com.") and "/" not in base:
            continue
        pkgs.add(base)
    return pkgs


def third_party_pkgs(adb: ADB) -> list:
    """用户安装的第三方应用列表。"""
    out = adb.shell("pm list packages -3")
    return sorted(l.strip()[8:] for l in out.splitlines() if l.strip().startswith("package:"))
