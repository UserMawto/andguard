#!/system/bin/sh
# ============================================================
# andguard-ondevice.sh —— 安卓手机端自治治理守护
# 一次性通过 adb 启动后，在手机内自主循环运行，不依赖电脑。
#
# 启动(在Mac终端执行一次，之后手机自主运行)：
#   adb shell "setsid nohup sh /data/local/tmp/andguard-ondevice.sh >/dev/null 2>&1 &"
# 查看是否在运行：
#   adb shell "ps -A | grep andguard-ondevice"
# 停止：
#   adb shell "pkill -f andguard-ondevice.sh"
# 查看日志：
#   adb shell "cat /data/local/tmp/andguard.log"
# 编辑治理名单/阈值：
#   adb push andguard.conf /data/local/tmp/andguard.conf
#
# 权限：以 shell 身份运行，可 force-stop / pm disable / appops / trim
# 局限：手机重启后需重新 adb 启动一次；如需"重启也自启"请走 root 路线。
# ============================================================

CONF=/data/local/tmp/andguard.conf
LOG=/data/local/tmp/andguard.log
PID=/data/local/tmp/andguard.pid
INTERVAL=5          # 采样间隔(秒)

# ---------- 默认参数(可用 andguard.conf 覆盖: KEY=value) ----------
EXCLUDE="com.tencent.mm com.eg.android.AlipayGphone"   # 永不治理(空格分隔)
MANAGED=""          # 治理名单；空=自动取全部用户应用
BG_CPU=40           # 后台CPU% ≥ 此值→挂起
BG_HITS=3           # 连续命中次数(≈INTERVAL*次数 秒)
MEM_CRIT=12         # 可用内存% < 此值→内存治理
MEM_WARN=25
TRIM_GB=1
KILL_CPU=200        # "真杀"阈值
KILL_ENABLE=0       # 0=关 1=开(真杀)
SUSPEND_METHOD=appops   # appops(轻) / freeze(pm disable)

# ---------- 读配置覆盖 ----------
if [ -f "$CONF" ]; then . "$CONF"; fi

log(){ echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }
# 退出时清理 pid 并记录
trap 'log "EXIT-进程退出"; rm -f "$PID"' EXIT

# 前台应用包名
fg_pkg(){
  dumpsys window 2>/dev/null | grep -iE 'mCurrentFocus|mFocusedApp' | \
    grep -oE '[A-Za-z0-9_.]+\.[A-Za-z0-9_]+' | head -1
}

# 可用内存百分比
mem_pct(){
  awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{if(t>0) printf "%d", a*100/t}' /proc/meminfo
}

# 当前所有用户应用
user_apps(){ pm list packages -3 2>/dev/null | sed 's/^package://'; }

# 是否在 exclude
in_exclude(){ echo "$EXCLUDE" | grep -q "(^| )$1( |$)"; }

# 是否正在运行
is_running(){ ps -A 2>/dev/null | grep -q "$1"; }

# 某应用后台CPU%(聚合子进程)
bg_cpu(){
  top -b -n 1 2>/dev/null | awk -v p="$1" '
    function base(n){ sub(/:.*/,"",n); return n }
    { if(base($NF)==p) sum+=$9+0 }
    END{ printf "%.0f", sum }'
}

# ---------- 治理动作 ----------
suspend(){
  pkg=$1
  am force-stop "$pkg" 2>/dev/null
  if [ "$SUSPEND_METHOD" = "freeze" ]; then
    pm disable-user --user 0 "$pkg" 2>/dev/null
    log "SUSPEND(freeze) $pkg"
  else
    cmd appops set "$pkg" RUN_IN_BACKGROUND ignore 2>/dev/null
    log "SUSPEND(appops) $pkg"
  fi
}
resume(){
  pkg=$1
  cmd appops set "$pkg" RUN_IN_BACKGROUND allow 2>/dev/null
  pm enable "$pkg" 2>/dev/null
  log "RESUME $pkg"
}
killpkg(){
  am force-stop "$1" 2>/dev/null
  log "KILL $1"
}

# 某应用是否被挂起(appops ignore)
is_suspended(){
  cmd appops get "$1" RUN_IN_BACKGROUND 2>/dev/null | grep -qi "ignore"
}

log "=== andguard-ondevice 启动 INTERVAL=${INTERVAL}s SUSPEND=${SUSPEND_METHOD} ==="
echo $$ > "$PID"   # 写 pid 供状态检测

_hits=""   # pkg:hits 连续高CPU计数
_n=0        # 循环计数(调试)

while :; do
  _n=$((_n+1))
  echo $$ > "$PID"   # 每轮刷新 pid，保证 pid 文件实时反映存活
  [ $((_n % 5)) -eq 0 ] && log "LOOP $_n fg=${fg:-none} mem=${mp:-?}%"
  fg=$(fg_pkg)
  mp=$(mem_pct)

  # 1) 前台被挂起的应用 → 自动恢复(对应 sysguard"回前台自动恢复")
  if [ -n "$fg" ] && is_suspended "$fg"; then resume "$fg"; fi

  # 2) 遍历治理名单做后台治理
  for p in $(user_apps); do
    in_exclude "$p" && continue
    [ "$p" = "$fg" ] && continue          # 前台不碰
    is_running "$p" || continue           # 没在运行跳过
    cpu=$(bg_cpu "$p")
    if [ "${cpu:-0}" -ge "$BG_CPU" ]; then
      # 累计命中
      hit=$(echo "$_hits" | awk -v p="$p" '$1==p{print $2+1}')
      if [ -z "$hit" ]; then _hits="$_hits
$p 1"; else _hits=$(echo "$_hits" | awk -v p="$p" -v h="$hit" '$1==p{$2=h}1'); fi
      if [ "$hit" -ge "$BG_HITS" ] && ! is_suspended "$p"; then
        suspend "$p"
        # 重置该应用计数
        _hits=$(echo "$_hits" | awk -v p="$p" '$1!=p')
      fi
    fi
  done

  # 3) 内存治理
  if [ "${mp:-100}" -le "$MEM_CRIT" ]; then
    pm trim-caches ${TRIM_GB}G 2>/dev/null
    # 挂起内存占用最大的后台应用(粗略按CPU最高代理)
    big=$(for p in $(user_apps); do
      in_exclude "$p" && continue
      [ "$p" = "$fg" ] && continue
      is_running "$p" || continue
      echo "$(bg_cpu "$p") $p"
    done | sort -rn | head -1 | awk '{print $2}')
    [ -n "$big" ] && ! is_suspended "$big" && suspend "$big"
    log "MEM ${mp}%<${MEM_CRIT}% → trim + suspend $big"
  fi

  # 4) "真杀"(可选, 默认关)
  if [ "$KILL_ENABLE" = "1" ]; then
    for p in $(user_apps); do
      in_exclude "$p" && continue
      [ "$p" = "$fg" ] && continue
      cpu=$(bg_cpu "$p")
      [ "${cpu:-0}" -ge "$KILL_CPU" ] && killpkg "$p"
    done
  fi

  sleep "$INTERVAL"
done
