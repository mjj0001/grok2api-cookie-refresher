#!/usr/bin/env python3
"""
Grok2API 管理工具
功能：一键刷新Cookie / 检查更新 / 备份管理 / 状态查看
"""

import subprocess, time, json, sys, os, socket, threading, select, difflib
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

def load_config():
    """从 config.env 读取配置"""
    cfg = {}
    env_file = os.path.join(SCRIPT_DIR, "config.env")
    if not os.path.exists(env_file):
        print("❌ 未找到 config.env 配置文件！")
        print(f"   请在脚本同目录创建: {env_file}")
        sys.exit(1)
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg

CFG = load_config()
SERVER_HOST = CFG["SERVER_HOST"]
SERVER_PORT = int(CFG["SERVER_PORT"])
SERVER_USER = CFG["SERVER_USER"]
SERVER_PASS = CFG["SERVER_PASS"]
WARP_LOCAL_PORT = int(CFG.get("WARP_LOCAL_PORT", "1080"))
CHROME_DEBUG_PORT = int(CFG.get("CHROME_DEBUG_PORT", "9222"))
CONFIG_FILE = CFG.get("CONFIG_FILE", "~/grok2api/data/config.toml")
COMPOSE_DIR = CFG.get("COMPOSE_DIR", "~/grok2api")
BACKUP_DIR = CFG.get("BACKUP_DIR", "~/grok2api/backups")


def auto_install(packages):
    for pkg in packages:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            print(f"  正在安装依赖: {pkg}...")
            subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"], check=True)


class SSHTunnel:
    """通过 SSH 建立本地端口转发隧道，将本地端口映射到服务器端口"""
    def __init__(self, host, port, user, pwd, lport, rport):
        self.host, self.port, self.user, self.pwd = host, port, user, pwd
        self.lport, self.rport = lport, rport
        self._client = self._sock = None
        self._running = False

    def start(self):
        import paramiko
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(self.host, port=self.port, username=self.user,
                             password=self.pwd, timeout=15,
                             allow_agent=False, look_for_keys=False)
        transport = self._client.get_transport()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        self._sock.bind(("127.0.0.1", self.lport))
        self._sock.listen(10)
        self._sock.settimeout(1)
        self._running = True
        def loop():
            while self._running:
                try:
                    cs, addr = self._sock.accept()
                    ch = transport.open_channel("direct-tcpip", ("127.0.0.1", self.rport), addr)
                    threading.Thread(target=self._fwd, args=(cs, ch), daemon=True).start()
                except socket.timeout: continue
                except Exception: break
        threading.Thread(target=loop, daemon=True).start()

    def _fwd(self, s, c):
        try:
            while True:
                r, _, _ = select.select([s, c], [], [], 5)
                if s in r:
                    d = s.recv(4096)
                    if not d: break
                    c.sendall(d)
                if c in r:
                    d = c.recv(4096)
                    if not d: break
                    s.sendall(d)
        except Exception: pass
        finally: s.close(); c.close()

    def stop(self):
        self._running = False
        for x in (self._sock, self._client):
            if x:
                try: x.close()
                except: pass


def find_chrome():
    for p in CHROME_PATHS:
        e = os.path.expandvars(p)
        if os.path.exists(e): return e
    return None

def get_ssh():
    """建立 SSH 连接到服务器（自动重试3次）"""
    import paramiko
    for i in range(3):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(SERVER_HOST, port=SERVER_PORT, username=SERVER_USER,
                        password=SERVER_PASS, allow_agent=False, look_for_keys=False, timeout=15)
            return ssh
        except Exception as e:
            print(f"  SSH 连接失败 ({i+1}/3): {e}")
            time.sleep(3)
    return None

def ssh_exec(ssh, cmd):
    _, out, _ = ssh.exec_command(cmd)
    out.channel.recv_exit_status()
    return out.read().decode().strip()

def ssh_exec_stream(ssh, cmd):
    _, out, _ = ssh.exec_command(cmd, get_pty=True)
    while True:
        line = out.readline()
        if not line: break
        print(f"  {line}", end="")
    return out.channel.recv_exit_status()


# ====================== 功能1: 刷新Cookie ======================
def refresh_cookie():
    """
    【一键刷新 CF Cookie】
    原理：通过 SSH 隧道将服务器的 WARP 代理转发到本地，
    用 Chrome 走 WARP IP 访问 grok.com 获取 cf_clearance，
    确保 Cookie 的 IP 与服务器请求的 IP 一致。
    """
    print("\n" + "=" * 52)
    print("   🍪 一键刷新 CF Cookie")
    print("=" * 52)
    print("   说明：自动完成以下操作：")
    print("   ① 建立 SSH 隧道，转发 WARP 代理到本地")
    print("   ② 验证 WARP 出口 IP")
    print("   ③ 启动 Chrome 走 WARP 代理访问 grok.com")
    print("   ④ 自动提取 cf_clearance Cookie")
    print("   ⑤ 将 Cookie 写入服务器并重启 grok2api")
    print("   注意：运行期间会关闭所有 Chrome 窗口！")
    print("-" * 52)

    auto_install(["paramiko", "websocket-client", "requests"])
    import websocket, requests

    chrome_path = find_chrome()
    if not chrome_path:
        print("❌ 未找到 Chrome 浏览器！")
        return
    print(f"  ✓ 找到 Chrome: {chrome_path}")

    tunnel = chrome = None
    try:
        print(f"\n  [步骤1/5] 建立 SSH 隧道到服务器 WARP 代理...")
        print(f"  → 将服务器 {SERVER_HOST}:1080 的 WARP 代理转发到本地 localhost:1080")
        tunnel = SSHTunnel(SERVER_HOST, SERVER_PORT, SERVER_USER, SERVER_PASS,
                           WARP_LOCAL_PORT, WARP_LOCAL_PORT)
        tunnel.start()
        time.sleep(2)
        print(f"  ✓ 隧道已建立")

        print(f"\n  [步骤2/5] 验证 WARP 出口 IP...")
        print(f"  → 通过代理访问 ifconfig.me 确认当前 WARP 的公网 IP")
        warp_ip = "unknown"
        try:
            resp = requests.get("https://ifconfig.me",
                                proxies={"https": f"socks5h://127.0.0.1:{WARP_LOCAL_PORT}"}, timeout=12)
            warp_ip = resp.text.strip()
            print(f"  ✓ WARP 出口 IP: {warp_ip}")
        except Exception as e:
            print(f"  ⚠ 无法验证 IP（不影响功能）: {e}")

        print(f"\n  [步骤3/5] 启动 Chrome 浏览器（走 WARP 代理）...")
        print(f"  → 关闭现有 Chrome → 启动新实例 → 代理指向 WARP → 打开 grok.com")
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
        time.sleep(2)
        chrome_tmp = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "warp-chrome-auto")
        chrome = subprocess.Popen([
            chrome_path,
            f"--proxy-server=socks5://127.0.0.1:{WARP_LOCAL_PORT}",
            f"--remote-debugging-port={CHROME_DEBUG_PORT}",
            f"--user-data-dir={chrome_tmp}",
            "--no-first-run", "--disable-default-apps", "--disable-extensions",
            "--disable-background-networking", "--remote-allow-origins=*",
            "https://grok.com",
        ])
        print("  ✓ Chrome 已启动，正在等待页面加载...")
        print("  → 如果弹出人机验证，请手动点击一下")
        time.sleep(5)

        print(f"\n  [步骤4/5] 自动提取 cf_clearance Cookie（最长等待90秒）...")
        print(f"  → 通过 Chrome 调试接口读取 grok.com 的 Cookie")
        cf_clearance = None
        last_error = ""
        for i in range(90):
            try:
                tabs = requests.get(f"http://localhost:{CHROME_DEBUG_PORT}/json", timeout=3).json()
                for tab in [t for t in tabs if "grok.com" in t.get("url", "")]:
                    ws_url = tab.get("webSocketDebuggerUrl")
                    if not ws_url: continue
                    ws = websocket.create_connection(ws_url, timeout=5)
                    ws.send(json.dumps({"id":1,"method":"Network.getCookies","params":{"urls":["https://grok.com"]}}))
                    result = json.loads(ws.recv())
                    ws.close()
                    for c in result.get("result",{}).get("cookies",[]):
                        if c["name"] == "cf_clearance":
                            cf_clearance = c["value"]; break
                if cf_clearance: break
            except Exception as e: last_error = str(e)
            print(f"  ... 等待中 {i+1}s", end="\r")
            time.sleep(1)

        if not cf_clearance:
            if last_error: print(f"\n  最后错误: {last_error}")
            print("\n  ❌ 提取 Cookie 失败，请重试")
            return
        print(f"\n  ✓ 成功提取到 cf_clearance!")

        print(f"\n  [步骤5/5] 写入服务器配置并重启 grok2api...")
        print(f"  → 关闭隧道 → SSH连接服务器 → 更新 config.toml → 重启容器")
        if tunnel: tunnel.stop(); tunnel = None; time.sleep(2)
        ssh = get_ssh()
        if not ssh:
            print(f"  ❌ SSH 连接失败，请手动更新:")
            print(f"  cf_clearance={cf_clearance}")
            return
        ssh_exec(ssh, f"sed -i 's|cf_cookies = \".*\"|cf_cookies = \"cf_clearance={cf_clearance}\"|' {CONFIG_FILE}")
        ssh_exec(ssh, f"cd {COMPOSE_DIR} && docker-compose restart grok2api")
        ssh.close()

        print("\n" + "=" * 52)
        print("  ✅ Cookie 刷新成功！")
        print(f"  使用的 WARP IP: {warp_ip}")
        print(f"  下次刷新: 约1小时后")
        print("=" * 52)
    finally:
        if chrome: chrome.terminate()
        if tunnel: tunnel.stop()


# ====================== 功能2: 检查更新 ======================
def check_update():
    """
    【检查并更新 grok2api】
    流程：检查远程镜像是否有新版本 → 备份配置 → 拉取新镜像 →
    重建容器 → 对比新旧配置差异 → 可选择还原旧配置
    """
    print("\n" + "=" * 52)
    print("   🔄 检查并更新 grok2api")
    print("=" * 52)
    print("   说明：自动完成以下操作：")
    print("   ① 对比本地镜像与远程最新镜像")
    print("   ② 有更新时自动备份 config.toml")
    print("   ③ 拉取新镜像并重建容器")
    print("   ④ 对比新旧配置差异（红色=删除 绿色=新增）")
    print("   ⑤ 如配置被覆盖，可一键还原")
    print("-" * 52)

    auto_install(["paramiko"])
    ssh = get_ssh()
    if not ssh: print("❌ 无法连接服务器"); return

    try:
        print("\n  [步骤1/4] 获取当前镜像版本...")
        print("  → 读取本地 Docker 镜像的 digest（唯一标识）")
        current = ssh_exec(ssh, "docker inspect ghcr.io/chenyme/grok2api:latest --format '{{.Id}}' 2>/dev/null || echo 'none'")
        print(f"  当前版本: {current[:24]}...")

        print("\n  [步骤2/4] 拉取远程最新镜像...")
        print("  → 从 GitHub Container Registry 下载最新镜像")
        ssh_exec_stream(ssh, f"cd {COMPOSE_DIR} && docker-compose pull grok2api")
        new = ssh_exec(ssh, "docker inspect ghcr.io/chenyme/grok2api:latest --format '{{.Id}}'")
        print(f"  最新版本: {new[:24]}...")

        if current == new:
            print("\n  ✅ 已经是最新版本，无需更新！")
            return
        print("\n  🆕 发现新版本！")

        print("\n  [步骤3/4] 备份当前配置...")
        print(f"  → 将 config.toml 复制到 {BACKUP_DIR}/")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = f"{BACKUP_DIR}/config_{ts}.toml"
        ssh_exec(ssh, f"mkdir -p {BACKUP_DIR}")
        ssh_exec(ssh, f"cp {CONFIG_FILE} {bak}")
        print(f"  ✓ 备份已保存: {bak}")
        old_cfg = ssh_exec(ssh, f"cat {CONFIG_FILE}")

        print("\n  [步骤4/4] 更新容器...")
        if input("  确认更新? (y/n): ").strip().lower() != "y":
            print("  已跳过"); return
        print("  → 强制重建 grok2api 容器（使用新镜像）")
        ssh_exec_stream(ssh, f"cd {COMPOSE_DIR} && docker-compose up -d --force-recreate grok2api")
        time.sleep(8)

        print("\n  对比配置差异...")
        print("  → 检查更新后的 config.toml 是否被新版本覆盖")
        new_cfg = ssh_exec(ssh, f"cat {CONFIG_FILE}")
        if old_cfg != new_cfg:
            print("\n  ⚠️ 配置文件在更新后发生了变化！差异如下：")
            print("  " + "-" * 48)
            for line in difflib.unified_diff(old_cfg.splitlines(), new_cfg.splitlines(),
                                              fromfile="更新前", tofile="更新后", lineterm=""):
                if line.startswith("+") and not line.startswith("+++"): print(f"  \033[92m{line}\033[0m")
                elif line.startswith("-") and not line.startswith("---"): print(f"  \033[91m{line}\033[0m")
                else: print(f"  {line}")
            print("  " + "-" * 48)
            if input("\n  是否还原旧配置? (y/n): ").strip().lower() == "y":
                ssh_exec(ssh, f"cp {bak} {CONFIG_FILE}")
                ssh_exec(ssh, f"cd {COMPOSE_DIR} && docker-compose restart grok2api")
                print("  ✓ 已还原旧配置并重启")
            else:
                print(f"  ✓ 保留新配置。备份位于: {bak}")
        else:
            print("  ✅ 配置未变化，一切正常！")

        print("\n  ✅ 更新完成！")
    finally:
        ssh.close()


# ====================== 功能3: 备份管理 ======================
def manage_backups():
    """
    【备份管理】
    可以手动创建备份、查看历史备份、对比差异、一键还原
    """
    print("\n" + "=" * 52)
    print("   💾 备份管理")
    print("=" * 52)
    print("   说明：管理服务器上 config.toml 的备份文件")
    print("   备份存放位置: ~/grok2api/backups/")
    print("-" * 52)

    auto_install(["paramiko"])
    ssh = get_ssh()
    if not ssh: print("❌ 无法连接服务器"); return

    try:
        ssh_exec(ssh, f"mkdir -p {BACKUP_DIR}")
        while True:
            print("\n  [1] 📝 立即创建备份    — 备份当前 config.toml")
            print("  [2] 📋 查看备份列表    — 列出所有历史备份")
            print("  [3] 🔍 对比差异        — 选择一个备份与当前配置对比")
            print("  [4] ⏪ 还原备份        — 选择一个备份覆盖当前配置")
            print("  [0] ↩️  返回主菜单")
            choice = input("\n  请选择: ").strip()

            if choice == "1":
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                bak = f"{BACKUP_DIR}/config_{ts}.toml"
                ssh_exec(ssh, f"cp {CONFIG_FILE} {bak}")
                print(f"  ✓ 备份已创建: {bak}")
            elif choice == "2":
                files = ssh_exec(ssh, f"ls -lht {BACKUP_DIR}/ 2>/dev/null")
                print(f"\n  {files}" if files else "  暂无备份")
            elif choice == "3":
                files = ssh_exec(ssh, f"ls -1t {BACKUP_DIR}/*.toml 2>/dev/null")
                if not files: print("  暂无备份"); continue
                fl = files.strip().split("\n")
                for i, f in enumerate(fl): print(f"  [{i+1}] {os.path.basename(f)}")
                try: pick = fl[int(input("  选择备份编号: ").strip()) - 1]
                except: print("  无效选择"); continue
                old = ssh_exec(ssh, f"cat {pick}")
                cur = ssh_exec(ssh, f"cat {CONFIG_FILE}")
                diff = list(difflib.unified_diff(old.splitlines(), cur.splitlines(),
                            fromfile=os.path.basename(pick), tofile="当前配置", lineterm=""))
                if not diff: print("  ✅ 完全相同，无差异")
                else:
                    for line in diff:
                        if line.startswith("+") and not line.startswith("+++"): print(f"  \033[92m{line}\033[0m")
                        elif line.startswith("-") and not line.startswith("---"): print(f"  \033[91m{line}\033[0m")
                        else: print(f"  {line}")
            elif choice == "4":
                files = ssh_exec(ssh, f"ls -1t {BACKUP_DIR}/*.toml 2>/dev/null")
                if not files: print("  暂无备份"); continue
                fl = files.strip().split("\n")
                for i, f in enumerate(fl): print(f"  [{i+1}] {os.path.basename(f)}")
                try: pick = fl[int(input("  选择备份编号: ").strip()) - 1]
                except: print("  无效选择"); continue
                if input(f"  确认还原 {os.path.basename(pick)}? (y/n): ").strip().lower() == "y":
                    ssh_exec(ssh, f"cp {pick} {CONFIG_FILE}")
                    ssh_exec(ssh, f"cd {COMPOSE_DIR} && docker-compose restart grok2api")
                    print("  ✓ 已还原并重启容器")
            elif choice == "0": break
    finally:
        ssh.close()


# ====================== 功能4: 状态查看 ======================
def quick_status():
    """
    【快速状态检查】
    一键查看：容器运行状态、WARP IP、配置摘要、最近日志、内存使用
    """
    print("\n" + "=" * 52)
    print("   📊 快速状态检查")
    print("=" * 52)
    print("   说明：一键查看服务器各项运行状态")
    print("-" * 52)

    auto_install(["paramiko"])
    ssh = get_ssh()
    if not ssh: print("❌ 无法连接服务器"); return

    try:
        print("\n  📦 容器状态")
        print("  → 检查 grok2api 和 warp 容器是否正常运行")
        containers = ssh_exec(ssh, 'docker ps --filter name=grok2api --filter name=warp --format "table {{.Names}}\t{{.Status}}" 2>/dev/null')
        print(f"  {containers}")

        print("\n  🌐 WARP 出口 IP")
        print("  → 通过 WARP 代理访问 ifconfig.me 获取公网 IP")
        print(f"  {ssh_exec(ssh, 'curl -s --socks5-hostname 127.0.0.1:1080 https://ifconfig.me --max-time 8 2>/dev/null || echo unreachable')}")

        print("\n  ⚙️ 代理配置")
        print("  → 读取 config.toml 中的代理和 Cookie 设置")
        print(f"  {ssh_exec(ssh, f'grep proxy_url {CONFIG_FILE} | head -1')}")
        cookie = ssh_exec(ssh, f"grep cf_cookies {CONFIG_FILE}")
        has = "cf_clearance=" in cookie and len(cookie) > 30
        print(f"  Cookie: {'✅ 已设置' if has else '❌ 未设置'}")

        print("\n  📝 最近日志（最后3行）")
        print("  → 查看 grok2api 容器的最新输出")
        for line in ssh_exec(ssh, f"cd {COMPOSE_DIR} && docker-compose logs --tail=3 grok2api 2>/dev/null").split("\n"):
            print(f"  {line}")

        print("\n  💾 内存使用")
        print(f"  {ssh_exec(ssh, 'free -h | head -2')}")
    finally:
        ssh.close()
    print("\n" + "=" * 52)


# ====================== 功能5: UA 指纹检查与同步 ======================
def check_ua_consistency():
    """
    【UA 指纹检查与同步】
    获取本地 Chrome 的真实 UA，并与服务器 config.toml 中的 user_agent 对比。
    如果不一致，支持一键同步更新。
    """
    print("\n" + "=" * 52)
    print("   🔍 UA 指纹检查与同步")
    print("=" * 52)
    print("   说明：确保本地浏览器与服务器配置的 User-Agent 完全一致")
    print("-" * 52)

    auto_install(["paramiko", "websocket-client", "requests"])
    import websocket, requests

    chrome_path = find_chrome()
    if not chrome_path: print("❌ 未找到 Chrome"); return

    local_ua = None
    chrome = None
    try:
        print("\n  [步骤1/3] 获取本地浏览器 UA...")
        # 启动一个临时的调试实例
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
        time.sleep(1)
        chrome_tmp = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "ua-check-tmp")
        chrome = subprocess.Popen([
            chrome_path, "--headless", f"--remote-debugging-port={CHROME_DEBUG_PORT}",
            f"--user-data-dir={chrome_tmp}", "--remote-allow-origins=*", "about:blank"
        ])
        
        for _ in range(10):
            try:
                tabs = requests.get(f"http://localhost:{CHROME_DEBUG_PORT}/json", timeout=2).json()
                if tabs:
                    ws_url = tabs[0].get("webSocketDebuggerUrl")
                    ws = websocket.create_connection(ws_url, timeout=5)
                    ws.send(json.dumps({"id": 1, "method": "Browser.getVersion"}))
                    res = json.loads(ws.recv())
                    local_ua = res.get("result", {}).get("userAgent")
                    if local_ua:
                        # 重点：修正 Headless 标记，防止 Cloudflare 报机器人
                        local_ua = local_ua.replace("HeadlessChrome", "Chrome")
                    ws.close()
                    if local_ua: break
            except: pass
            time.sleep(1)
        
        if not local_ua: print("  ❌ 提取本地 UA 失败"); return
        print(f"  ✓ 本地 UA: {local_ua}")

    finally:
        if chrome: chrome.terminate()

    print("\n  [步骤2/3] 获取服务器配置 UA...")
    ssh = get_ssh()
    if not ssh: print("  ❌ SSH 连接失败"); return
    
    try:
        remote_ua_line = ssh_exec(ssh, f"grep 'user_agent' {CONFIG_FILE} | head -1")
        import re
        match = re.search(r'user_agent\s*=\s*"(.*)"', remote_ua_line)
        remote_ua = match.group(1) if match else "未找到"
        print(f"  ✓ 服务器 UA: {remote_ua}")

        print("\n  [步骤3/3] 对比结果")
        if local_ua == remote_ua:
            print("  ✅ 匹配！本地与服务器指纹完全一致。")
        else:
            print("  ❌ 不匹配！这可能导致 Cookie 校验失败。")
            if input("\n  是否一键同步本地 UA 到服务器? (y/n): ").strip().lower() == "y":
                # 安全转义 UA 中的特殊字符
                escaped_ua = local_ua.replace('"', '\\"')
                ssh_exec(ssh, f"sed -i 's|user_agent = \".*\"|user_agent = \"{escaped_ua}\"|' {CONFIG_FILE}")
                ssh_exec(ssh, f"cd {COMPOSE_DIR} && docker-compose restart grok2api")
                print("  ✅ 同步成功并已重启容器！")
    finally:
        ssh.close()
    print("\n" + "=" * 52)


# ====================== 主菜单 ======================
def main():
    print("\n" + "=" * 52)
    print("   🚀 Grok2API 管理工具")
    print("=" * 52)
    print(f"   服务器: {SERVER_HOST}:{SERVER_PORT}")
    print(f"   时间:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 52)

    while True:
        print("\n  [1] 🍪 刷新 Cookie     — 自动获取 cf_clearance 并更新到服务器")
        print("  [2] 🔄 检查更新         — 检测新版本、备份配置、对比差异")
        print("  [3] 💾 备份管理         — 创建/查看/对比/还原配置备份")
        print("  [4] 📊 状态查看         — 容器状态、WARP IP、内存等")
        print("  [5] 🔍 UA 指纹检查      — 检查并同步本地与服务器的 User-Agent")
        print("  [0] ❌ 退出")
        choice = input("\n  请选择功能: ").strip()

        if choice == "1": refresh_cookie()
        elif choice == "2": check_update()
        elif choice == "3": manage_backups()
        elif choice == "4": quick_status()
        elif choice == "5": check_ua_consistency()
        elif choice == "0": print("\n  再见！👋"); break
        else: print("  无效选择，请重新输入")

    input("\n按回车键退出...")

if __name__ == "__main__":
    main()
