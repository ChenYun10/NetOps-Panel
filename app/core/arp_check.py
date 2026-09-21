# -*- coding: utf-8 -*-
"""
ARP 检测与 ARP 欺诈检测模块。

- ARP 检测：解析本机 ARP 表，列出局域网 IP-MAC 映射与 MAC 厂商；
- ARP 欺诈检测：识别 MAC 复用（同一 MAC 冒充多个 IP，典型 ARP 欺骗）、
  IP 冲突（同一 IP 对应多个 MAC）、网关 MAC 异常提示。
"""
import re

from .logger import log
from . import syscmd

# 常见 MAC OUI 厂商前缀（前 3 字节）
OUI_DB = {
    "d8:32:14": "TP-Link",
    "f4:6d:04": "TP-Link",
    "48:46:fb": "华为",
    "00:e0:fc": "华为",
    "3c:07:54": "Apple",
    "00:03:93": "Apple",
    "8c:be:be": "小米",
    "f0:b4:29": "小米",
    "00:1b:21": "Intel",
    "00:14:22": "Dell",
    "b8:27:eb": "树莓派",
    "dc:a6:32": "树莓派",
    "00:0c:29": "VMware",
    "00:50:56": "VMware",
    "08:00:27": "VirtualBox",
    "00:1a:2b": "Realtek",
    "bc:5f:f4": "华硕",
    "04:d9:f5": "华硕",
    "50:3e:aa": "乐视/TP-Link",
    "34:ce:00": "乐视",
}


def parse_arp_table():
    """解析 arp -a 输出，返回 [(ip, mac, 类型), ...]。"""
    out = syscmd.run_capture(["arp", "-a"], timeout=8)
    entries = []
    for line in out.splitlines():
        m = re.search(
            r"(\d+\.\d+\.\d+\.\d+)\s+"
            r"([0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2}-"
            r"[0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2})\s+"
            r"(动态|静态|dynamic|static)",
            line)
        if m:
            entries.append((m.group(1), m.group(2).lower(), m.group(3)))
    return entries


def lookup_vendor(mac):
    """根据 MAC 前 3 字节查厂商。"""
    prefix = mac[:8]  # "xx:xx:xx"
    return OUI_DB.get(prefix, "")


def _is_real_device(ip, mac):
    """过滤组播/广播地址，只保留真实单播设备。"""
    if mac == "ff-ff-ff-ff-ff-ff":
        return False  # 广播 MAC
    if mac.startswith("01-00-5e"):
        return False  # IPv4 组播 MAC
    parts = ip.split(".")
    if len(parts) == 4:
        first, last = int(parts[0]), int(parts[3])
        if 224 <= first <= 239:
            return False  # 组播 IP
        if last == 255:
            return False  # 广播 IP
    return True


def run_arp_check():
    """ARP 检测：列出 ARP 表并识别 MAC 厂商。"""
    log.info("开始 ARP 检测")
    entries = parse_arp_table()
    entries = [e for e in entries if _is_real_device(e[0], e[1])]
    if not entries:
        log.warn("ARP 表为空（可能刚清空或局域网无通信）")
        return {"entries": [], "count": 0}
    for ip, mac, typ in entries:
        vendor = lookup_vendor(mac)
        suffix = f"  [{vendor}]" if vendor else ""
        log.info(f"{ip:<16} {mac}  {typ}{suffix}")
    log.ok(f"ARP 检测完成，共 {len(entries)} 条记录")
    return {"entries": entries, "count": len(entries)}


def run_arp_spoof_check():
    """
    ARP 欺诈检测：
    1. MAC 复用 —— 同一 MAC 对应多个 IP（攻击者用自己 MAC 冒充网关/多设备）；
    2. IP 冲突 —— 同一 IP 对应多个 MAC；
    3. 网关 MAC 提示 —— 提醒用户核对网关 MAC 是否可信。
    """
    log.info("开始 ARP 欺诈检测")
    entries = parse_arp_table()
    entries = [e for e in entries if _is_real_device(e[0], e[1])]
    if not entries:
        log.warn("ARP 表为空，无法检测")
        return {"suspicious": [], "entries": []}

    suspicious = []

    # 1. 同一 MAC 映射多个 IP（疑似 ARP 欺骗）
    mac_to_ips = {}
    for ip, mac, _typ in entries:
        mac_to_ips.setdefault(mac, []).append(ip)
    for mac, ips in mac_to_ips.items():
        if len(ips) > 1:
            vendor = lookup_vendor(mac)
            suspicious.append({"type": "MAC复用(疑似ARP欺骗)", "mac": mac, "ips": ips})
            log.warn(f"疑似 ARP 欺骗：MAC {mac}{(' [' + vendor + ']') if vendor else ''} "
                     f"同时对应 {len(ips)} 个 IP：{', '.join(ips)}")

    # 2. 同一 IP 映射多个 MAC（IP 冲突）
    ip_to_macs = {}
    for ip, mac, _typ in entries:
        ip_to_macs.setdefault(ip, set()).add(mac)
    for ip, macs in ip_to_macs.items():
        if len(macs) > 1:
            suspicious.append({"type": "IP冲突", "ip": ip, "macs": list(macs)})
            log.warn(f"IP 冲突：{ip} 对应多个 MAC：{', '.join(sorted(macs))}")

    # 3. 网关 MAC 提示
    try:
        from . import system_info as si
        gw = si.get_gateway()
        for ip, mac, _typ in entries:
            if ip == gw:
                vendor = lookup_vendor(mac)
                log.info(f"网关 {gw} 的 MAC 为 {mac}{(' [' + vendor + ']') if vendor else ''}，"
                         f"请核对是否为你的路由器真实 MAC")
                break
    except Exception:
        pass

    if not suspicious:
        log.ok("未发现 ARP 欺诈迹象")
    else:
        log.error(f"发现 {len(suspicious)} 项可疑记录，请立即核对网络设备")
    return {"suspicious": suspicious, "entries": entries}
