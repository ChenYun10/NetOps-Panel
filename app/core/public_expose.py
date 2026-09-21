# -*- coding: utf-8 -*-
"""
公网检测模块。

- 出口公网 IPv4 / IPv6 地址查询（多源容错）
- 公网暴露测试（检测常见端口是否对公网开放）
- UPnP 状态检测（SSDP 发现路由器 + GetExternalIPAddress）
"""
import re
import socket
import urllib.request

from .logger import log

# 公网 IP 查询源（IPv4）
IPV4_SOURCES = [
    "https://4.ipw.cn",          # 国内服务，快
    "http://ip.3322.net",
    "https://api.ipify.org",
]
# 公网 IP 查询源（IPv6，需本机有 IPv6）
IPV6_SOURCES = [
    "https://6.ipw.cn",
    "https://api64.ipify.org",
]

# 常见对外暴露检测端口
EXPOSE_PORTS = [22, 23, 80, 443, 3389, 445, 8080, 8000, 7547]


def _is_ipv4(s):
    parts = s.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def _is_ipv6(s):
    return ":" in s


def get_public_ipv4(timeout=5):
    """查询出口公网 IPv4 地址。失败返回 None。"""
    for url in IPV4_SOURCES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NetOps-Panel/1.0"})
            ip = urllib.request.urlopen(req, timeout=timeout).read().decode().strip()
            if _is_ipv4(ip):
                return ip
        except Exception:
            continue
    return None


def get_public_ipv6(timeout=5):
    """
    查询出口公网 IPv6 地址。失败返回 None。
    优先走外部 API（验证 IPv6 出网），失败则回退本机全局 IPv6 地址
    （IPv6 端到端设计，全局单播地址即公网地址）。
    """
    for url in IPV6_SOURCES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NetOps-Panel/1.0"})
            ip = urllib.request.urlopen(req, timeout=timeout).read().decode().strip()
            if _is_ipv6(ip):
                return ip
        except Exception:
            continue
    # 兜底：本机全局 IPv6 地址
    try:
        from . import ipv6_check
        addrs = ipv6_check.get_ipv6_addresses()
        if addrs:
            return addrs[0]
    except Exception:
        pass
    return None


def _check_port_open(host, port, timeout=3):
    """本地 socket 探测端口（受 NAT 回环限制，结果仅供辅助参考）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        r = s.connect_ex((host, port))
        s.close()
        return r == 0
    except Exception:
        return False


def run_public_expose():
    """
    公网暴露测试：
    1. 查询出口公网 IPv4；
    2. 用第三方 API（hackertarget）扫描公网开放端口；
    3. 本地 socket 探测常见端口作为辅助（NAT 回环限制）。
    """
    log.info("开始公网暴露测试")
    result = {"public_ipv4": None, "open_ports": [], "error": ""}

    pub_ip = get_public_ipv4()
    if not pub_ip:
        log.error("无法获取公网 IPv4 地址")
        result["error"] = "无法获取公网 IP"
        return result
    result["public_ipv4"] = pub_ip
    log.info(f"出口公网 IPv4: {pub_ip}")

    # 方式 1：第三方 nmap API（可靠，从公网视角扫描）
    try:
        url = f"https://api.hackertarget.com/nmap/?q={pub_ip}"
        req = urllib.request.Request(url, headers={"User-Agent": "NetOps-Panel/1.0"})
        text = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
        if "error" not in text.lower() and "nmap" not in text.lower()[:50]:
            # 解析 "PORT     STATE SERVICE" 后的端口行
            ports = re.findall(r"^(\d+)/tcp\s+open", text, re.M)
            for p in ports:
                result["open_ports"].append(int(p))
                log.warn(f"端口 {p} 对公网开放（暴露风险）")
            if ports:
                log.warn(f"检测到 {len(ports)} 个公网开放端口")
            else:
                log.ok("未检测到公网开放端口")
        else:
            log.info("第三方扫描服务不可用，改用本地探测")
            result["open_ports"] = _local_port_check(pub_ip)
    except Exception as e:
        log.info(f"第三方扫描失败（{e}），改用本地探测")
        result["open_ports"] = _local_port_check(pub_ip)

    if not result["open_ports"]:
        log.ok("公网暴露测试完成：未发现明显暴露端口")
    return result


def _local_port_check(pub_ip):
    """本地 socket 探测常见端口（辅助，NAT 回环可能不准）。"""
    log.info("本地探测常见端口…")
    open_ports = []
    for p in EXPOSE_PORTS:
        if _check_port_open(pub_ip, p):
            open_ports.append(p)
            log.warn(f"端口 {p} 疑似对公网开放")
    if not open_ports:
        log.ok("本地探测未发现开放端口")
    return open_ports


# ---------------- UPnP ----------------

SSDP_ADDR = ("239.255.255.250", 1900)
SSDP_MSG = ('M-SEARCH * HTTP/1.1\r\n'
            'HOST: 239.255.255.250:1900\r\n'
            'MAN: "ssdp:discover"\r\n'
            'MX: 2\r\n'
            'ST: ssdp:all\r\n'
            '\r\n').encode()


def _ssdp_discover(timeout=3):
    """SSDP 组播发现，返回 [(ip, location, st), ...]。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    devices = []
    try:
        sock.sendto(SSDP_MSG, SSDP_ADDR)
        while True:
            try:
                data, addr = sock.recvfrom(65507)
            except socket.timeout:
                break
            text = data.decode("utf-8", "replace")
            m = re.search(r"LOCATION:\s*(\S+)", text, re.I)
            st = re.search(r"(?:ST|NT):\s*(\S+)", text, re.I)
            if m:
                devices.append((addr[0], m.group(1), st.group(1) if st else ""))
    except Exception:
        pass
    finally:
        sock.close()
    return devices


def _soap_get_external_ip(control_url, timeout=5):
    """SOAP 调 GetExternalIPAddress 获取 UPnP 公网 IP。"""
    body = ('<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            '<s:Body><u:GetExternalIPAddress '
            'xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1"/>'
            '</s:Body></s:Envelope>')
    req = urllib.request.Request(
        control_url, data=body.encode(),
        headers={"Content-Type": 'text/xml; charset="utf-8"',
                 "SOAPAction": '"urn:schemas-upnp-org:service:WANIPConnection:1#GetExternalIPAddress"',
                 "User-Agent": "NetOps-Panel/1.0"})
    resp = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
    m = re.search(r"<NewExternalIPAddress>([^<]+)</NewExternalIPAddress>", resp)
    return m.group(1) if m else None


def run_upnp_check(timeout=5):
    """
    UPnP 状态检测：
    1. SSDP 发现局域网内 UPnP 设备；
    2. 识别 IGD（路由器）；
    3. 取设备描述找 WANIPConnection 控制地址；
    4. SOAP 调 GetExternalIPAddress 验证 UPnP 是否真正可用。
    """
    log.info("开始 UPnP 状态检测（SSDP 发现）")
    result = {"upnp_enabled": False, "devices": [], "external_ip": None, "error": ""}

    devices = _ssdp_discover(timeout)
    if not devices:
        log.warn("未发现 UPnP 设备（路由器可能关闭了 UPnP）")
        result["error"] = "未发现 UPnP 设备"
        return result

    igd_found = False
    for ip, location, st in devices:
        is_igd = "InternetGatewayDevice" in st or "WANIPConnection" in st or "WANPPPConnection" in st
        if is_igd:
            igd_found = True
        result["devices"].append({"ip": ip, "st": st})
        log.info(f"发现 UPnP 设备: {ip} ({st[:60]})")

    if not igd_found:
        log.warn("发现 UPnP 设备但未见 IGD 路由器（UPnP 可能未对 WAN 开放）")
        result["error"] = "无 IGD 路由器响应"
        return result

    # 尝试从 IGD 设备描述里找 WANIPConnection 控制地址
    for ip, location, st in devices:
        if "InternetGatewayDevice" not in st and "WANIPConnection" not in st and "WANPPPConnection" not in st:
            continue
        try:
            desc = urllib.request.urlopen(location, timeout=timeout).read().decode("utf-8", "replace")
            m = re.search(r"<controlURL>(.*?)</controlURL>", desc)
            if not m:
                continue
            # 拼完整控制 URL
            control = m.group(1)
            from urllib.parse import urljoin
            control_url = urljoin(location, control)
            ext_ip = _soap_get_external_ip(control_url, timeout)
            if ext_ip:
                result["upnp_enabled"] = True
                result["external_ip"] = ext_ip
                log.ok(f"UPnP 已开启，公网 IP（经 UPnP 查询）: {ext_ip}")
                break
        except Exception as e:
            log.info(f"查询 {ip} UPnP 服务失败: {e}")

    if not result["upnp_enabled"]:
        log.warn("发现 IGD 但无法获取外部 IP（UPnP 功能受限或关闭）")
        result["error"] = "UPnP 查询失败"
    return result
