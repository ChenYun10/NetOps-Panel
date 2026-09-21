# -*- coding: utf-8 -*-
"""
传统 DNS（明文）检测模块。

- UDP 53 / TCP 53 未加密 DNS 查询（可自定义服务器与端口）
- 检测：服务器连通性、DNS 解析结果、查询耗时、响应状态码、
  UDP 截断(TC)与 TCP 回退支持。

与 DoH/DoT 相对，本模块检测的是未加密的传统 DNS。
"""
import time

import dns.flags
import dns.message
import dns.query
import dns.rcode

from .logger import log

DEFAULT_DNS = "223.5.5.5"


def _query(server, port, domain, proto, timeout):
    """按协议查询，返回 (response, elapsed_ms)。"""
    q = dns.message.make_query(domain, "A")
    start = time.perf_counter()
    if proto == "UDP":
        resp = dns.query.udp(q, server, port=port, timeout=timeout)
    else:
        resp = dns.query.tcp(q, server, port=port, timeout=timeout)
    elapsed = (time.perf_counter() - start) * 1000
    return resp, elapsed


def run_dns_check(server=None, port=53, domain="www.baidu.com",
                  proto="UDP", timeout=5):
    """
    执行传统 DNS 检测。
    proto: "UDP" / "TCP" / "BOTH"（两者都测，并检查 TCP 回退）。
    """
    server = (server or DEFAULT_DNS).strip()
    result = {
        "server": server,
        "port": int(port),
        "proto": proto,
        "domain": domain,
        "udp": None,
        "tcp": None,
        "ok": False,
        "error": "",
    }

    def one(p):
        """单协议查询，返回小结果 dict。"""
        r = {"ok": False, "rcode": "", "answers": [], "elapsed_ms": None,
             "tc": False, "error": ""}
        try:
            resp, elapsed = _query(server, int(port), domain, p, timeout)
            r["elapsed_ms"] = round(elapsed, 2)
            r["rcode"] = dns.rcode.to_text(resp.rcode())
            r["tc"] = bool(resp.flags & dns.flags.TC)
            for rr in resp.answer:
                for rdata in rr:
                    r["answers"].append(str(rdata))
            r["ok"] = resp.rcode() == dns.rcode.NOERROR
            return r
        except Exception as e:
            r["error"] = str(e)
            return r

    if proto in ("UDP", "BOTH"):
        r = one("UDP")
        result["udp"] = r
        log.info(f"UDP/{port} 查询 {server}…")
        if r["ok"]:
            log.ok(f"UDP 解析成功：{domain} -> {', '.join(r['answers']) or '(无记录)'}（{r['elapsed_ms']} ms）")
            if r["tc"]:
                log.warn("UDP 响应被截断（TC 标志），服务器要求 TCP 回退")
        else:
            log.error(f"UDP 查询失败：{r['rcode'] or r['error']}")
        result["ok"] = result["ok"] or r["ok"]

    if proto in ("TCP", "BOTH"):
        r = one("TCP")
        result["tcp"] = r
        log.info(f"TCP/{port} 查询 {server}…")
        if r["ok"]:
            log.ok(f"TCP 解析成功：{domain} -> {', '.join(r['answers']) or '(无记录)'}（{r['elapsed_ms']} ms）")
        else:
            log.error(f"TCP 查询失败：{r['rcode'] or r['error']}")
        result["ok"] = result["ok"] or r["ok"]

    # TCP 回退判定（仅 BOTH 模式）
    if proto == "BOTH":
        udp, tcp = result["udp"], result["tcp"]
        if udp and udp["tc"] and tcp and tcp["ok"]:
            log.ok("TCP 回退正常：UDP 截断后 TCP 查询成功")
        elif udp and udp["tc"] and not (tcp and tcp["ok"]):
            log.warn("UDP 截断但 TCP 回退失败（服务器可能未开放 TCP 53）")

    return result
