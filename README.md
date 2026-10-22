# AndGuard — 安卓手机 CPU/内存智能治理

对标 macOS 版 [sysguard](https://github.com/eternity4719/sysguard) 的理念，翻译到安卓：**温和治理、可逆、绝不误杀系统进程**。目标是让一台"很卡、有应用卸载不掉"的安卓手机变得流畅，且**治理逻辑能跑在手机里、不依赖电脑**。

**三大能力**：
1. **挂起** —— 后台冻结某应用（前台打开仍可用，不吃后台 CPU/内存）
2. **冻结** —— 完全停用某应用（`pm disable-user`，点开需先解冻）
3. **真正杀掉** —— `am force-stop` 立即终止进程；也可彻底卸载

**两种运行形态**：
| 形态 | 在哪控制 | 是否需要电脑常驻 | 适用 |
|---|---|---|---|
| **桌面 CLI** | Mac 终端 | 需连电脑 | 手动/批量操作、真机自测 |
| **手机自治守护 + 网页控制台** | **手机浏览器** | **不需要**，启动后手机独立 | 日常治理（推荐） |

> ⚠️ 华为 P20 Pro 用户注意：华为 2018 年已停发 bootloader 解锁码，**无法 root**。本项目的"手机自治 + 网页控制台"是**不 root 前提下的最优解**。

---

## 一、快速上手（手机自治，推荐）

手机和电脑连**同一个 WiFi**，电脑装好 `adb`。三行命令：

```bash
# ① 首次：手机插 USB 线，打开 开发者选项→USB调试，授权后转无线（一次即可）
adb tcpip 5555
adb connect 手机IP:5555

# ② 进项目目录，一键启动（推送脚本+配置，拉起守护+网页控制台）
cd andguard/ondevice && ./ond start

# ③ 手机浏览器打开控制台，开始点按钮治理
http://手机IP:8080/cgi-bin/panel.cgi
```

之后**拔掉电脑**，手机自己每 5 秒扫描治理。**手机重启后**只需插线 + `./ond boot` 一条命令恢复（见第四节）。

---

## 二、桌面 CLI（需要电脑连着手机时）

### 安装
```bash
./install.sh
```
生成 `~/.andguard/config.yaml`（默认 **dry_run 观察期**，只记录不动手）和命令 `~/bin/andguard`。

### 命令速查
```bash
~/bin/andguard status            # 仪表盘（设备/规则/状态）
~/bin/andguard apps              # 用户应用 + 运行状态
~/bin/andguard top               # CPU/内存排行
~/bin/andguard suspend 包名       # 挂起(后台冻结)   [关键字也可，如"围棋"]
~/bin/andguard freeze  包名       # 冻结(完全停用)
~/bin/andguard kill     包名       # 真正杀掉
~/bin/andguard uninstall 包名 --yes  # 彻底卸载(不可逆)
~/bin/andguard resume all        # 全部恢复
~/bin/andguard optimize          # 一键优化：限后台+清缓存+挂起所有后台应用
~/bin/andguard doctor --selftest # 真机原语自测(杀→挂→恢复→冻结→解冻，验证可逆)
~/bin/andguard daemon            # 常驻治理(Ctrl+C 自动恢复全部)
```

`dry_run` 改 `false` 才真正动手：编辑 `~/.andguard/config.yaml` 里 `dry_run: false`。

---

## 三、手机自治守护 + 网页控制台（核心，不依赖电脑）

### 3.1 手机端守护（每 5 秒自主治理）

用 `ondevice/ond` 管理（Mac 终端，`cd ondevice` 后执行）：

```bash
./ond start       # 推送守护+配置到手机并启动（守护+网页一起拉起）
./ond status      # 守护是否运行
./ond stop        # 停止守护+网页
./ond restart     # 重启(改了配置后用它生效)
./ond log         # 查看治理日志
./ond pushconf    # 重新推送配置(改治理名单/阈值后)
```

**守护自动做的事**（按 `ondevice/andguard.conf` 规则）：
| 动作 | 触发 | 行为 |
|---|---|---|
| 挂起 | 后台 CPU≥BG_CPU 连续 BG_HITS 次 | force-stop + appops 后台冻结 |
| 冻结 | 后台整树高 | pm disable-user |
| 杀掉 | KILL_ENABLE=1 且 CPU≥KILL_CPU | am force-stop（默认关） |
| 内存 | 可用内存<MEM_CRIT% | 清缓存 + 挂起内存最大后台应用 |
| 自动恢复 | 被挂起的应用变前台 | 立即解除挂起（前台绝不碰） |

### 3.2 手机端网页控制台（在手机里点按钮）

守护在手机上用 **busybox httpd** 托管一个网页，**用手机浏览器打开**就能实时看到占用、点按钮治理：

```
http://手机IP:8080/cgi-bin/panel.cgi
```

> 手机 IP 以 `./ond web status` 显示的为准，可存浏览器书签。

**面板功能**：
- 顶部：手机 IP、可用内存百分比进度条
- 列表：每个第三方应用 → 运行状态点、CPU%、冻结状态
- 每行按钮：`挂起` `恢复` `冻结` `解冻` `真杀` `启动`

| 按钮 | 实际动作 |
|---|---|
| 挂起 | force-stop + appops 后台冻结 |
| 恢复 | 解除后台冻结 |
| 冻结 | pm disable-user 彻底停用 |
| 解冻 | pm enable |
| 真杀 | am force-stop 立即结束 |
| 启动 | 拉起应用 |

**网页管理**：
```bash
./ond web start     # 启动网页控制台
./ond web stop      # 停止网页
./ond web status    # 状态 + 显示访问地址
```

> 原理：`busybox-arm64` 是内置静态 busybox（提供 httpd）。面板 CGI 跑在 **shell 权限**下，所以能执行 `am/pm/cmd` 治理命令——这就是**不 root 也能控制其它 App** 的原因。

### 3.3 配置参考（`ondevice/andguard.conf`）

```ini
EXCLUDE="com.tencent.mm com.eg.android.AlipayGphone"   # 永不治理(空格分隔)
MANAGED=""                                              # 治理名单；留空=自动取全部用户应用
BG_CPU=40       # 后台CPU%≥此值→挂起
BG_HITS=3       # 连续多少次触发
MEM_WARN=25     # 内存告警%
MEM_CRIT=12     # 内存告急%，触发清缓存+挂大户
TRIM_GB=1       # 清缓存保留空闲GB
KILL_CPU=200    # 真杀CPU阈值
KILL_ENABLE=0   # 1=开启"真正杀掉"自动规则(默认关)
SUSPEND_METHOD=appops  # appops(轻)/freeze(pm disable)
INTERVAL=5      # 采样间隔秒
```

---

## 四、手机重启后怎么恢复（务必看）

非 root 下，手机重启后守护和网页**不会自动起来**、无线调试端口也会失效。恢复只需一条命令：

```bash
# ① 手机插 USB 线连电脑，保持 开发者选项→USB调试 开启（首次弹窗点"允许"）
# ② Mac 终端运行：
cd andguard/ondevice && ./ond boot
```

`./ond boot` 自动：尝试重连无线 → 拉起守护 → 拉起网页控制台。拔线后手机继续独立运行。

> **为什么必须经电脑一次？** 治理动作必须由 shell 权限进程执行，而这种进程只能通过 adb 建立。手机重启后它消失，安卓安全模型又不允许普通 App 开机自启"能杀别的 App"的进程——这就是当初想 root 的原因（华为已停发解锁码）。**这是安全边界，非 root 无法完全绕过。**

---

## 五、桌面配置参考（`~/.andguard/config.yaml`）

```yaml
device: "192.168.0.237:5555"     # adb 设备；无线格式 IP:5555
dry_run: true                    # true=观察期只记录；false=真正治理
poll_interval: 3                 # daemon 采样间隔(秒)
exclude:                         # 永不治理
  - com.tencent.mm
  - com.eg.android.AlipayGphone
suspend_method: appops           # appops / freeze
rules:
  r1_bg_freeze:  {enable: true,  cpu_pct: 40,  duration_sec: 30}
  r2_suspend:    {enable: true,  cpu_pct: 120, duration_sec: 60}
  r3_memory:     {warn_pct: 25, critical_pct: 12, persist_sec: 20}
  r4_notify:     {cpu_pct: 90, persist_min: 5}          # 仅通报，绝不杀
  r5_kill:       {enable: false, cpu_pct: 200, duration_sec: 90}  # 真杀，默认关
limits:
  background_process_limit: -1   # -1不设；0-4 后台进程上限
  trim_caches_gb: 1
```

---

## 六、项目结构

```
andguard/
├── andguard/            # 桌面 CLI(Python)：adb/sampler/actions/rules/cli/daemon...
├── config.example.yaml  # 桌面配置模板
├── requirements.txt     # 桌面依赖(PyYAML)
├── install.sh / uninstall.sh
└── ondevice/            # ★ 手机自治(核心)
    ├── ond              # 管理脚本: start/stop/restart/boot/status/log/pushconf/web
    ├── andguard-ondevice.sh   # 手机端自治守护(shell循环，每INTERVAL秒治理)
    ├── andguard.conf          # 手机端配置
    ├── busybox-arm64          # 内置静态busybox(提供httpd)
    └── www/cgi-bin/panel.cgi  # 网页控制台面板
```

---

## 七、安全设计（同 sysguard 理念）

1. 默认 `dry_run` 观察期，看日志确认后再开治理
2. 只治理**用户应用**白名单；`exclude` 保护核心应用（默认微信/支付宝）；**前台应用绝不触碰**
3. 守护/CLI 退出时自动恢复全部挂起
4. "真正杀掉"R5 默认关闭，需显式启用

## 八、故障排查

| 现象 | 处理 |
|---|---|
| `./ond start` 显示未连接 | 手机重启后先插 USB，跑 `./ond boot` |
| 面板打不开 | `./ond web status` 确认运行与正确 IP；确认手机与电脑同 WiFi |
| 守护状态误报"未运行" | 守护每轮刷新 pid 文件，`./ond restart` 后 `./ond status` 再看 |
| 想治理某应用但列表没有 | 它在系统应用里；面板只列第三方应用 |

## 九、环境要求
- macOS / Linux，装有 `adb`（无线连接先 `adb tcpip 5555` + `adb connect 手机IP:5555`）
- 手机：开启 开发者选项→USB调试（华为/EMUI 无"无线调试"开关，需 USB 首连转无线）

## 免责声明
治理对象均为**用户应用**；请勿冻结系统/核心进程。本项目仅提供工具，因使用造成的数据或设备问题由使用者自行承担。
