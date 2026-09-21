# -*- coding: utf-8 -*-
"""
IPv6 检测模块。

- 本机 IPv6 地址 / IPv6 默认网关
- IPv6 支持检测
- IPv6 连通性测试（ping6 公网 IPv6）
- IPv6 网关转发测试（ping6 网关 + ping6 公网，判断转发是否正常）
"""
import ipaddress
import re
import socket

import psutil

from .logger import log
from . import syscmd

# 常见公网 IPv6 探测目标（DNS 服务器）
PUBLIC_V6_TARGETS = [
    "2400:3200::1",           # 阿里公共 DNS IPv6
    "2400:3200:baba::1",      # 阿里公共 DNS IPv6 备用
    "2606:4700:4700::1111",   # Cloudflare DNS IPv6
]


def _is_temporary(ip):
    """
    判断是否为隐私扩展临时地址。
    稳定地址（EUI-64）的接口标识符(IID)第 4-5 字节固定为 ff:fe；
    临时地址 IID 随机生成，无此特征。
    """
    try:
        obj = ipaddress.ip_address(ip)
        if obj.version != 6:
            return False
        iid = obj.packed[-8:]  # 后 8 字节 = IID
        return iid[3:5] != b"\xff\xfe"
    except Exception:
        return False


def get_ipv6_addresses():
    """
    返回本机所有全局 IPv6 地址列表。
    稳定地址（EUI-64）优先，隐私扩展临时地址靠后。
    """
    addrs = set()
    try:
        for name, addr_list in psutil.net_if_addrs().items():
            for a in addr_list:
                if a.family == socket.AF_INET6:
                    ip = a.address.split("%")[0]  # 去掉 zone id
                    try:
                        obj = ipaddress.ip_address(ip)
                        # 过滤链路本地/回环，只保留全局单播
                        if obj.is_global and not obj.is_multicast:
                            addrs.add(ip)
                    except ValueError:
                        continue
    except Exception:
        pass
    # 稳定地址优先，临时地址靠后
    return sorted(addrs, key=lambda ip: 1 if _is_temporary(ip) else 0)


def get_stable_ipv6():
    """返回首选稳定全局 IPv6 地址（非临时），无则返回 None。"""
    addrs = get_ipv6_addresses()
    return addrs[0] if addrs else None


def get_ipv6_gateway():
    """解析 IPv6 默认网关（route print -6 里 ::/0 的下一跳）。"""
    try:
        out = syscmd.run_capture(["route", "print", "-6"], timeout=5)
        for line in out.splitlines():
            parts = line.split()
            # 找网络目标列是 ::/0 的行，网关在其下一列（格式因系统而异）
            for i, p in enumerate(parts):
                if p == "::/0" and i + 1 < len(parts):
                    gw = parts[i + 1]
                    try:
                        if ipaddress.ip_address(gw).version == 6:
                            return gw
                    except ValueError:
                        continue
        # 兜底：netsh interface ipv6 show route 的 ::/0 默认路由
        out2 = syscmd.run_capture(
            ["netsh", "interface", "ipv6", "show", "route"], timeout=5)
        for line in out2.splitlines():
            if "::/0" in line:
                m = re.search(r"([0-9a-fA-F:]+%?\d*)", line)
                if m and ":" in m.group(1):
                    gw = m.group(1).split("%")[0]
                    try:
                        if ipaddress.ip_address(gw).version == 6:
                            return gw
                    except ValueError:
                        continue
    except Exception:
        pass
    return None


def ping6(host, timeout=3):
    """ping6 指定 IPv6 地址。返回 (成功, 延迟ms, 错误)。"""
    try:
        code, text = syscmd.run(
            ["ping", "-6", "-n", "1", "-w", str(int(timeout * 1000)), host],
            timeout=timeout + 2,
        )
        if code != 0:
            return False, None, "IPv6 目标不可达"
        m = re.search(r"(?:时间|time)[=<]\s*(\d+)\s*ms", text, re.I)
        if m:
            return True, int(m.group(1)), ""
        if "TTL=" in text or "ttl=" in text:
            return True, 0, ""
        return False, None, "无响应"
    except Exception as e:
        return False, None, str(e)


def check_ipv6_support():
    """检测本机 IPv6 支持情况。返回结构化 dict。"""
    result = {
        "supported": False,
        "addresses": [],
        "gateway": None,
        "has_global_addr": False,
    }
    addrs = get_ipv6_addresses()
    result["addresses"] = addrs
    result["has_global_addr"] = len(addrs) > 0
    gw = get_ipv6_gateway()
    result["gateway"] = gw
    result["supported"] = len(addrs) > 0 or gw is not None
    return result


def run_ipv6_check():
    """IPv6 检测：完整检测本机 IPv6 配置。"""
    log.info("开始 IPv6 检测")
    r = check_ipv6_support()
    if r["addresses"]:
        for ip in r["addresses"]:
            log.ok(f"本机 IPv6 地址: {ip}")
    else:
        log.warn("本机无全局 IPv6 地址（可能未启用 IPv6 或网络不支持）")
    if r["gateway"]:
        log.ok(f"IPv6 默认网关: {r['gateway']}")
    else:
        log.warn("未检测到 IPv6 默认网关")
    log.ok("IPv6 检测完成")
    return r


def run_ipv6_connectivity():
    """IPv6 连通性测试：ping6 多个公网 IPv6 目标。"""
    log.info("开始 IPv6 连通性测试")
    results = []
    ok_count = 0
    for target in PUBLIC_V6_TARGETS:
        ok, ms, err = ping6(target, 3)
        if ok:
            ok_count += 1
            log.ok(f"IPv6 连通 {target}：{ms} ms")
        else:
            log.warn(f"IPv6 不可达 {target}：{err}")
        results.append({"target": target, "ok": ok, "ms": ms, "err": err})
    if ok_count == 0:
        log.error("IPv6 连通性测试全部失败，本机可能无可用 IPv6 网络")
    else:
        log.ok(f"IPv6 连通性测试完成：{ok_count}/{len(PUBLIC_V6_TARGETS)} 可达")
    return {"results": results, "ok_count": ok_count}


def run_ipv6_gateway_forward():
    """
    IPv6 网关转发测试：
    1. ping6 本机 IPv6 网关（链路可达性）；
    2. ping6 公网 IPv6（需经网关转发）。
    两者都通 => 转发正常；网关通但公网不通 => 网关未转发 IPv6。
    """
    log.info("开始 IPv6 网关转发测试")
    gw = get_ipv6_gateway()
    if not gw:
        log.error("未检测到 IPv6 默认网关，无法测试转发")
        return {"error": "无 IPv6 网关"}

    log.info(f"IPv6 网关: {gw}")
    ok_gw, ms_gw, err_gw = ping6(gw, 3)
    if ok_gw:
        log.ok(f"IPv6 网关可达：{ms_gw} ms")
    else:
        log.error(f"IPv6 网关不可达：{err_gw}")
        return {"gateway_ok": False, "forward_ok": False}

    # 测试经网关转发到公网
    ok_wan = False
    for target in PUBLIC_V6_TARGETS[:2]:
        ok, ms, err = ping6(target, 3)
        if ok:
            ok_wan = True
            log.ok(f"经网关转发到 {target} 成功：{ms} ms")
            break
        else:
            log.warn(f"转发到 {target} 失败：{err}")

    if ok_wan:
        log.ok("IPv6 网关转发正常")
    else:
        log.error("IPv6 网关可达但无法转发到公网（网关可能未启用 IPv6 转发/NAT64）")
    return {"gateway": gw, "gateway_ok": ok_gw, "forward_ok": ok_wan}
