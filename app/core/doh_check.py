# -*- coding: utf-8 -*-
"""
【4】DoH（基于 HTTPS 的加密 DNS）检测模块。

默认服务地址：https://dns.alidns.com/dns-query（可自定义）。
检测项目：DoH 服务连通性、HTTPS 证书校验、DNS 解析结果、整体耗时。

实现：dnspython 构造/解析 DNS 报文，标准库 urllib 发 HTTPS 请求
（走系统 CA 校验证书），无需额外 HTTP 客户端依赖。
"""
import socket
import ssl
import time
import urllib.request

import dns.message

from .logger import log

DEFAULT_DOH = "https://dns.alidns.com/dns-query"


def run_doh_check(domain, doh_url=None, timeout=8):
    """
    执行 DoH 检测，返回结构化 dict。
    doh_url 为空时使用默认 https://dns.alidns.com/dns-query
    """
    url = (doh_url or DEFAULT_DOH).strip()
    if "://" not in url:
        url = "https://" + url
    result = {
        "url": url,
        "conn_ok": False,
        "cert_ok": False,
        "domain": domain,
        "answers": [],
        "elapsed_ms": None,
        "error": "",
    }

    try:
        # 1) 构造 A 记录查询报文
        q = dns.message.make_query(domain, "A")
        wire = q.to_wire()

        # 2) 发 HTTPS POST（系统 CA 校验证书）
        req = urllib.request.Request(
            url, data=wire, method="POST",
            headers={
                "Content-Type": "application/dns-message",
                "Accept": "application/dns-message",
                "User-Agent": "NetOps-Panel/1.0",
            },
        )
        start = time.perf_counter()
        # urlopen 默认走系统 CA（create_default_context），证书校验失败抛 SSLError
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = resp.read()
        result["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 2)
        result["conn_ok"] = True
        result["cert_ok"] = True
        log.ok(f"DoH 连通成功，耗时 {result['elapsed_ms']} ms")

        # 3) 解析响应
        resp_msg = dns.message.from_wire(data)
        rcode = dns.rcode.to_text(resp_msg.rcode())
        if resp_msg.rcode() != dns.rcode.NOERROR:
            result["error"] = f"DNS 返回码异常: {rcode}"
            log.warn(result["error"])
            return result
        for rr in resp_msg.answer:
            for rdata in rr:
                result["answers"].append(str(rdata))
        if result["answers"]:
            log.ok(f"解析结果：{domain} -> {', '.join(result['answers'])}")
        else:
            log.warn(f"{domain} 无 A 记录应答")

    except urllib.error.URLError as e:
        result["error"] = f"DoH 请求失败: {e.reason}"
        log.error(result["error"])
    except ssl.SSLCertVerificationError as e:
        result["error"] = f"DoH 证书校验失败: {e}"
        log.error(result["error"])
    except socket.timeout:
        result["error"] = "DoH 请求超时"
        log.error(result["error"])
    except Exception as e:
        result["error"] = f"检测异常: {e}"
        log.error(result["error"])

    return result
