# -*- coding: utf-8 -*-
"""上传 NetOpsPanel.exe 到 GitHub Release。"""
import subprocess, json, urllib.request, hashlib, os

EXE = "dist/NetOpsPanel.exe"
VERSION = "v1.0.0"
REPO = "ChenYun10/NetOps-Panel"

# 1. 拿 token（不 echo）
proc = subprocess.run(['git', 'credential', 'fill'],
                      input=b'protocol=https\nhost=github.com\n\n', capture_output=True)
token = None
for line in proc.stdout.decode().splitlines():
    if line.startswith('password='):
        token = line.split('=', 1)[1]
        break
if not token:
    print('NO_TOKEN')
    exit(1)

# 2. 计算 sha256 与大小
h = hashlib.sha256()
with open(EXE, 'rb') as f:
    for chunk in iter(lambda: f.read(65536), b''):
        h.update(chunk)
sha = h.hexdigest()
size_mb = os.path.getsize(EXE) / (1024 * 1024)

# 3. Release 说明
body = f"""# NetOps Panel v1.0.0 网络运维检测面板

深色科技风格的 Windows 桌面网络运维工具，左侧竖向导航 + 右侧卡片式工作台。
**单文件 exe，双击即用，无需安装 Python 或任何依赖。**

## 下载

| 文件 | 说明 |
|---|---|
| `NetOpsPanel.exe` | 单文件可执行程序（{size_mb:.1f} MB） |

- **SHA256**：`{sha}`

## 功能特性

### 首页工作台
- 本机 IP / 网关 / DNS / 外网连通性卡片 + 各节点 Ping 延迟
- CPU / 内存 / 磁盘占用环形仪表盘 + 实时上下行流量曲线
- 系统信息：主机名、运行时长、内存剩余、磁盘剩余（正确识别 Windows 10/11）

### 基础检测
诊断检测、网络健康、Ping 测试、路由追踪、端口扫描、主机发现（ping+TCP+ARP 三合一）、
摄像头扫描、安全自测、日志审计、IP 冲突检测、速度测试、外网/内网测速、会话测试、
网络分析、数据抓包、DHCP 检测。

### 高级检测（独立入口）
- **TCP 应用层握手**：三次握手 RTT + 应用层握手（裸TCP/HTTP/SSH/TLS）
- **SSH 连通性**：握手耗时、版本识别、弱加密算法检测、认证结果
- **HTTPS 检测**：TLS 版本、加密套件、证书信息、证书链完整性、降级风险
- **DoH 加密 DNS**：连通性、证书校验、解析结果、耗时（默认 alidns）
- **DoT 加密 DNS**：853 连通、TLS 握手、解析结果、耗时（默认 alidns:853）

### 内网测速
**内嵌 iperf3 客户端**（3.17.1），主动连接内网 iperf 服务端测速，
支持下载/上传、TCP/UDP，无需单独安装 iperf3。

## 使用说明

1. 下载 `NetOpsPanel.exe`，双击运行即可
2. 内网测速：目标机器运行 `iperf3 -s -p 5201`，本机填服务端 IP 测速
3. 数据抓包/安全自测需「以管理员身份运行」才能读完整信息
4. 每个检测页都有「保存日志」按钮，可导出 txt 审计留档

## 系统要求
- Windows 10 / 11（x64）
- 无需安装 Python 或其他运行时

## 开源协议
[MIT License](https://github.com/ChenYun10/NetOps-Panel/blob/main/LICENSE)
"""

# 4. 创建 release
data = json.dumps({
    "tag_name": VERSION,
    "name": f"NetOps Panel {VERSION}",
    "body": body,
    "draft": False,
    "prerelease": False,
}).encode()
req = urllib.request.Request(
    f"https://api.github.com/repos/{REPO}/releases", method="POST", data=data,
    headers={"Authorization": "token " + token, "Content-Type": "application/json",
             "User-Agent": "NetOps", "Accept": "application/vnd.github+json"})
try:
    rel = json.loads(urllib.request.urlopen(req, timeout=30).read())
except urllib.error.HTTPError as e:
    print('创建 release 失败:', e.code, e.read().decode()[:300])
    exit(1)
print('Release 创建:', rel['html_url'])
upload_url = rel['upload_url'].split('{')[0]

# 5. 上传 exe
with open(EXE, 'rb') as f:
    content = f.read()
req2 = urllib.request.Request(
    f"{upload_url}?name=NetOpsPanel.exe", method="POST", data=content,
    headers={"Authorization": "token " + token,
             "Content-Type": "application/octet-stream", "User-Agent": "NetOps"})
try:
    asset = json.loads(urllib.request.urlopen(req2, timeout=600).read())
    print('Asset 上传成功:', asset['browser_download_url'])
except urllib.error.HTTPError as e:
    print('上传失败:', e.code, e.read().decode()[:300])
