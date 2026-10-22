#!/system/bin/sh
# andguard 手机端网页控制台 CGI
# 由 busybox httpd 调用:  http://<手机IP>:8080/cgi-bin/panel.cgi
LOG=/data/local/tmp/andguard-panel.log

log(){ echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }

# 解析 QUERY_STRING: act=...&pkg=...
QS="${QUERY_STRING:-}"
act=""; pkg=""
for kv in $(echo "$QS" | tr '&' ' '); do
  case "$kv" in
    act=*) act="${kv#act=}" ;;
    pkg=*) pkg="${kv#pkg=}" ;;
  esac
done

# ---------- 数据采集 ----------
mem_pct(){ awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}END{if(t>0)printf "%d",a*100/t}' /proc/meminfo; }
pkg_running(){ pidof "$1" >/dev/null 2>&1; }
pkg_frozen(){ pm list packages -d --user 0 2>/dev/null | grep -q "^package:$1$"; }

# 一次性 top 快照,按包聚合 CPU%
cpu_pkgs(){
  top -b -n 1 2>/dev/null | awk '
    function base(n){sub(/:.*/,"",n);return n}
    { s[base($NF)]+=$9+0 }
    END{ for(k in s) printf "%s %.0f\n", k, s[k] }'
}

hdr(){
  echo "HTTP/1.0 200 OK"
  echo "Content-Type: text/html; charset=utf-8"
  echo "Cache-Control: no-cache"
  echo ""
}

page_head(){
  cat <<'EOF'
<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>andguard 控制台</title>
<style>
body{font-family:-apple-system,system-ui,sans-serif;background:#0f1115;color:#e6e6e6;margin:0;padding:16px}
h1{font-size:20px;margin:4px 0 12px}
.bar{height:14px;background:#22252b;border-radius:7px;overflow:hidden;margin:6px 0 14px}
.bar>div{height:100%;background:linear-gradient(90deg,#22c55e,#eab308);transition:width .3s}
.meta{font-size:13px;color:#9aa0a6;margin-bottom:10px}
.msg{background:#1c3a2a;border:1px solid #2f6b44;color:#7ee2a8;padding:8px 10px;border-radius:8px;margin:10px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 6px;text-align:left;border-bottom:1px solid #22252b;vertical-align:middle}
th{color:#9aa0a6;font-weight:600;white-space:nowrap}
.cpu{font-variant-numeric:tabular-nums;min-width:52px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
.run{background:#22c55e}.stop{background:#4b5563}.frz{background:#f59e0b}
.btn{display:inline-block;padding:5px 10px;margin:2px;border-radius:7px;text-decoration:none;font-size:12px;color:#fff}
.b-sus{background:#b45309}.b-res{background:#15803d}.b-frz{background:#6b21a8}.b-thw{background:#15803d}.b-kill{background:#b91c1c}.b-run{background:#0369a1}
.pkg{font-family:ui-monospace,monospace;font-size:11px;color:#cbd5e1;word-break:break-all}
.foot{color:#4b5563;font-size:11px;margin-top:16px}
</style></head><body>
EOF
}

page_tail(){ cat <<'EOF'
<div class="foot">andguard 手机端控制台 · 治理由手机内守护执行 · 刷新即更新</div>
</body></html>
EOF
}

# ---------- 主逻辑 ----------
hdr
page_head

echo "<h1>📱 andguard 控制台</h1>"
MYIP="$(ip route get 1.1.1.1 2>/dev/null | grep -oE 'src [0-9.]+' | cut -d' ' -f2)"
echo "<div class=meta>手机 IP: ${MYIP:-未知} · 可用内存 <b>$(mem_pct)%</b></div>"
echo "<div class=bar><div style='width:$(mem_pct)%'></div></div>"

# 执行动作
if [ -n "$act" ] && [ -n "$pkg" ]; then
  case "$act" in
    suspend) am force-stop "$pkg" >/dev/null 2>&1; cmd appops set "$pkg" RUN_IN_BACKGROUND ignore >/dev/null 2>&1; log "SUSPEND $pkg"; msg="已挂起 $pkg";;
    resume)  cmd appops set "$pkg" RUN_IN_BACKGROUND allow >/dev/null 2>&1; log "RESUME $pkg"; msg="已恢复 $pkg";;
    freeze)  am force-stop "$pkg" >/dev/null 2>&1; pm disable-user --user 0 "$pkg" >/dev/null 2>&1; log "FREEZE $pkg"; msg="已冻结 $pkg";;
    thaw)    pm enable --user 0 "$pkg" >/dev/null 2>&1; log "THAW $pkg"; msg="已解冻 $pkg";;
    kill)    am force-stop "$pkg" >/dev/null 2>&1; log "KILL $pkg"; msg="已真杀 $pkg";;
    start)   monkey -p "$pkg" 1 >/dev/null 2>&1; log "START $pkg"; msg="已启动 $pkg";;
  esac
  echo "<div class=msg>$msg</div>"
fi

# 一次性采集
CPU="$(cpu_pkgs)"
FROZEN="$(pm list packages -d --user 0 2>/dev/null | sed 's/^package://')"

echo "<table><tr><th>应用</th><th>运行</th><th>CPU%</th><th>冻结</th><th>操作</th></tr>"
for p in $(pm list packages -3 2>/dev/null | sed 's/^package://'); do
  case "$p" in
    com.huawei.android.launcher|com.android.systemui|com.huawei.systemmanager|com.android.settings) continue;;
  esac
  c="$(echo "$CPU" | awk -v p="$p" '$1==p{printf "%d",$2}')"
  if pkg_running "$p"; then st='<span class=dot run></span>'; else st='<span class=dot stop></span>'; fi
  if echo "$FROZEN" | grep -q "^$p$"; then fr='<span class=dot frz></span>'; else fr='<span class=dot stop></span>'; fi
  echo "<tr><td class=pkg>$p</td><td>$st</td><td class=cpu>${c:-0}</td><td>$fr</td><td>"
  echo "<a class='btn b-sus' href='panel.cgi?act=suspend&amp;pkg=$p'>挂起</a>"
  echo "<a class='btn b-res'  href='panel.cgi?act=resume&amp;pkg=$p'>恢复</a>"
  echo "<a class='btn b-frz'  href='panel.cgi?act=freeze&amp;pkg=$p'>冻结</a>"
  echo "<a class='btn b-thw'  href='panel.cgi?act=thaw&amp;pkg=$p'>解冻</a>"
  echo "<a class='btn b-kill' href='panel.cgi?act=kill&amp;pkg=$p'>真杀</a>"
  echo "<a class='btn b-run'  href='panel.cgi?act=start&amp;pkg=$p'>启动</a>"
  echo "</td></tr>"
done
echo "</table>"
page_tail
