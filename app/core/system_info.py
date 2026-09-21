# -*- coding: utf-8 -*-
"""
系统信息模块：采集本机网络与硬件信息。

- 本机 IP / 网关 / DNS（Windows 原生 socket + psutil）
- 主机名、运行时长、内存剩余、磁盘剩余
"""
import socket
import platform
import psutil


def get_hostname():
    """返回主机名。"""
    return socket.gethostname()


def get_uptime_seconds():
    """返回系统运行时长（秒），基于 psutil.boot_time()。"""
    import time
    try:
        return time.time() - psutil.boot_time()
    except Exception:
        return 0


def format_uptime(seconds):
    """把秒数格式化为 'X天X小时X分'。"""
    s = int(seconds)
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d:
        return f"{d}天{h}小时{m}分"
    if h:
        return f"{h}小时{m}分"
    return f"{m}分钟"


def get_local_ip():
    """
    获取本机对外出口 IP。
    用 UDP 连一个公网地址（不真正发包），内核会选路并填充本地地址，
    这是跨平台拿'出口网卡 IP'的常用技巧。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        # 兜底：走系统 hostname 解析
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "未知"
    finally:
        s.close()


def get_all_ips():
    """返回所有网卡的 IPv4 地址列表。"""
    ips = set()
    for name, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET:
                ips.add(a.address)
    return sorted(ips)


def get_gateway():
    """返回默认网关地址。"""
    gws = psutil.net_if_stats()
    try:
        for name, addrs in psutil.net_if_addrs().items():
            if name not in gws:
                continue
            # psutil 不直接给网关，这里用 Windows 路由表解析
            pass
    except Exception:
        pass
    # Windows 下用 `route print` 解析默认网关最稳
    return _windows_default_gateway()


def _windows_default_gateway():
    """调用 Windows 原生 route 命令解析默认网关(0.0.0.0)。"""
    from . import syscmd
    try:
        out = syscmd.run_capture(["route", "print", "-4"], timeout=5)
        # 找 0.0.0.0 目标且掩码 0.0.0.0 的行，网关在第三列
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                return parts[2]
    except Exception:
        pass
    return "未知"


def get_dns_servers():
    """返回本机配置的 DNS 服务器列表。"""
    # 优先用 dnspython 读系统 DNS 配置（Windows 读注册表，最可靠）
    dns = []
    try:
        import dns.resolver
        dns = list(dns.resolver.Resolver().nameservers)
    except Exception:
        dns = []
    if dns:
        return dns
    # 回退：解析 ipconfig /all 里的 DNS Servers
    from . import syscmd
    try:
        out = syscmd.run_capture(["ipconfig", "/all"], timeout=8)
        lines = out.splitlines()
        for i, line in enumerate(lines):
            if "DNS Servers" in line or "DNS 服务器" in line:
                # 取该行冒号后，或下一行（有时 DNS 在下一行）
                val = line.split(":", 1)[-1].strip()
                if val:
                    dns.append(val)
                elif i + 1 < len(lines):
                    nxt = lines[i + 1].strip()
                    if nxt:
                        dns.append(nxt)
    except Exception:
        pass
    # 去重去空
    seen, result = set(), []
    for d in dns:
        d = d.strip()
        if d and d not in seen and _looks_like_ip(d):
            seen.add(d)
            result.append(d)
    return result if result else ["未检测到"]


def _looks_like_ip(s):
    """粗判是否为 IP 地址。"""
    parts = s.split(".")
    return len(parts) == 4 and all(p.isdigit() for p in parts)


def get_cpu_percent():
    """返回 CPU 总占用率(0-100)。"""
    return psutil.cpu_percent(interval=None)


def get_memory():
    """返回 (总量GB, 已用GB, 占用率%)。"""
    vm = psutil.virtual_memory()
    total = vm.total / (1024 ** 3)
    used = vm.used / (1024 ** 3)
    return total, used, vm.percent


def get_disk():
    """返回系统盘 (总量GB, 已用GB, 占用率%, 剩余GB)。"""
    du = psutil.disk_usage("C:/")
    total = du.total / (1024 ** 3)
    used = du.used / (1024 ** 3)
    free = du.free / (1024 ** 3)
    return total, used, du.percent, free


# Windows 版本英文标识 -> 友好中文名
_EDITION_MAP = {
    "IoTEnterpriseS": "IoT 企业版 LTSC",
    "IoTEnterprise": "IoT 企业版",
    "EnterpriseS": "企业版 LTSC",
    "Enterprise": "企业版",
    "Professional": "专业版",
    "ProEducation": "专业教育版",
    "Education": "教育版",
    "Core": "家庭版",
    "Home": "家庭版",
}


def get_os_info():
    """返回操作系统描述（正确识别 Windows 10 / 11 及版本）。"""
    try:
        ver = platform.version()  # 如 "10.0.26100"
        parts = ver.split(".")
        build = int(parts[-1]) if parts else 0
        # NT 内核同为 10.0：build >= 22000 即为 Windows 11，否则 Windows 10
        name = "Windows 11" if build >= 22000 else "Windows 10"
        edition = platform.win32_edition() or ""
        edition_cn = _EDITION_MAP.get(edition, edition)
        if edition_cn:
            return f"{name} {edition_cn} ({ver})"
        return f"{name} ({ver})"
    except Exception:
        return f"{platform.system()} {platform.release()}"


def get_python_info():
    """返回解释器版本。"""
    return platform.python_version()
