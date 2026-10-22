#!/usr/bin/env bash
# andguard 安装：建 venv、装依赖、生成配置、建可执行命令 ~/bin/andguard
set -e
cd "$(dirname "$0")"
HERE="$(pwd)"
DST="${ANDGUARD_DST:-$HOME/.andguard}"
BINDIR="$HOME/bin"
echo "==> 安装到 $DST (代码在 $HERE) =="

# 1. venv
python3 -m venv "$DST/venv" 2>/dev/null || { echo "venv 创建失败"; exit 1; }
"$DST/venv/bin/pip" install -q --upgrade pip 2>/dev/null || true
if [ -f requirements.txt ]; then "$DST/venv/bin/pip" install -q -r requirements.txt 2>/dev/null || true; fi

# 2. 生成默认配置（不覆盖已有）
mkdir -p "$DST/state"
if [ ! -f "$DST/config.yaml" ]; then
  if [ -f config.example.yaml ]; then cp config.example.yaml "$DST/config.yaml"; fi
  echo "==> 已生成 $DST/config.yaml（dry_run 观察期）"
fi

# 3. 生成可执行命令
mkdir -p "$BINDIR"
cat > "$BINDIR/andguard" <<'EOF'
#!/usr/bin/env bash
exec "$HOME/.andguard/venv/bin/python" -m andguard.cli "$@"
EOF
chmod +x "$BINDIR/andguard"
# 确保能 import 包（软链到 venv site-packages）
SITE="$($DST/venv/bin/python -c 'import site;print(site.getsitepackages()[0])' 2>/dev/null || echo "$DST/venv/lib/python3*/site-packages")"
ln -sfn "$HERE/andguard" "$SITE/andguard" 2>/dev/null || {
  # 备选：把包目录直接放 venv site-packages
  for d in "$DST/venv/lib/"python3*/site-packages; do [ -d "$d" ] && ln -sfn "$HERE/andguard" "$d/andguard"; done
}

echo "==> 安装完成。用法："
echo "    ~/bin/andguard status      # 仪表盘"
echo "    ~/bin/andguard apps        # 应用列表"
echo "    ~/bin/andguard top         # CPU/内存排行"
echo "    ~/bin/andguard suspend 包名 # 挂起(后台冻结)"
echo "    ~/bin/andguard freeze 包名  # 冻结(完全停用)"
echo "    ~/bin/andguard kill 包名    # 真正杀掉(force-stop)"
echo "    ~/bin/andguard uninstall 包名 --yes  # 彻底卸载"
echo "    ~/bin/andguard resume all  # 全部恢复"
echo "    ~/bin/andguard daemon      # 常驻治理"

# 4. 开机自动常驻（launchd）——生成 plist 并登记
mkdir -p "$HOME/Library/LaunchAgents" "$DST/logs"
cat > "$HOME/Library/LaunchAgents/local.andguard.daemon.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key><string>local.andguard.daemon</string>
	<key>ProgramArguments</key>
	<array>
		<string>$DST/venv/bin/python</string>
		<string>-m</string>
		<string>andguard.cli</string>
		<string>daemon</string>
	</array>
	<key>WorkingDirectory</key><string>$HOME</string>
	<key>RunAtLoad</key><true/>
	<key>KeepAlive</key><true/>
	<key>ProcessType</key><string>Background</string>
	<key>StandardOutPath</key><string>$DST/logs/daemon.log</string>
	<key>StandardErrorPath</key><string>$DST/logs/daemon.log</string>
</dict>
</plist>
PLIST
echo "==> 已生成开机自启 plist：$HOME/Library/LaunchAgents/local.andguard.daemon.plist"
echo "    若本终端能执行 launchctl，将自动登记："
launchctl bootout "gui/$(id -u)/local.andguard.daemon" 2>/dev/null
if launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.andguard.daemon.plist" 2>/dev/null; then
  echo "    ✅ 已登记开机自启并启动 daemon（后台治理已常驻）"
else
  echo "    ⚠ 无法自动登记（launchctl 被运行环境限制）。请在你的 Terminal 手动执行："
  echo "      launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/local.andguard.daemon.plist"
fi
