#!/usr/bin/env bash
# andguard 卸载：先恢复所有挂起/冻结，再清理 ~/.andguard
set -e
cd "$(dirname "$0")"
echo "==> 先尝试恢复所有可治理应用 =="
"$HOME/.andguard/venv/bin/python" -m andguard.cli resume all 2>/dev/null || echo "(恢复跳过/无需)"
echo "==> 停止并移除开机自启 daemon =="
launchctl bootout "gui/$(id -u)/local.andguard.daemon" 2>/dev/null || echo "(未登记或受限)"
rm -f "$HOME/Library/LaunchAgents/local.andguard.daemon.plist"
echo "==> 删除运行时目录 =="
rm -rf "$HOME/.andguard"
rm -f "$HOME/bin/andguard"
echo "==> 卸载完成（代码目录保留：$PWD）"
