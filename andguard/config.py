"""配置加载：优先 YAML，未装 pyyaml 时退回内置默认；支持热加载。"""
import os

CONFIG_PATH = os.path.expanduser("~/.andguard/config.yaml")

DEFAULTS = {
    "device": "",                       # adb 序列号；空=自动选唯一设备
    "dry_run": True,                    # 观察期：只记录不执行
    "poll_interval": 3,                 # daemon 采样秒数
    "exclude": ["com.tencent.mm", "com.eg.android.AlipayGphone"],  # 永不自动挂
    "suspend_method": "appops",         # appops(轻) / freeze(pm disable)
    "rules": {
        "r1_bg_freeze": {"enable": True, "cpu_pct": 40, "duration_sec": 30, "cooldown_min": 10},
        "r2_suspend":   {"enable": True, "cpu_pct": 120, "duration_sec": 60, "cooldown_min": 15},
        "r3_memory":    {"warn_pct": 25, "critical_pct": 12, "persist_sec": 20},
        "r4_notify":    {"cpu_pct": 90, "persist_min": 5, "cooldown_min": 60},
        "r5_kill":      {"enable": False, "cpu_pct": 200, "duration_sec": 90, "cooldown_min": 30},  # 默认关
    },
    "limits": {
        "background_process_limit": -1,   # -1 不设；0-4 全局后台进程上限
        "trim_caches_gb": 1,              # 内存告急时 pm trim-caches 保留空闲GB
    },
}


def load(path: str = CONFIG_PATH) -> dict:
    cfg = dict(DEFAULTS)
    cfg["rules"] = dict(DEFAULTS["rules"])
    cfg["limits"] = dict(DEFAULTS["limits"])
    if os.path.exists(path):
        try:
            import yaml  # 可选依赖
            with open(path, encoding="utf-8") as f:
                user = yaml.safe_load(f) or {}
            _merge(cfg, user)
        except ImportError:
            pass  # 无 pyyaml 用默认
        except Exception:
            pass
    return cfg


def _merge(base: dict, user: dict):
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
