# -*- coding: utf-8 -*-
"""
【5】DoT（基于 TLS 的加密 DNS）检测模块。

默认服务器：tls://dns.alidns.com（端口 853，可自定义）。
检测项目：853 端口 TCP 连通、TLS 握手校验、DNS over TLS 解析结果、耗时。

实现：标准库 socket + ssl（RFC 7858：2 字节长度前缀 + DNS wire 报文），
dnspython 仅用于构造/解析报文。
"""
import socket
import ssl
import struct
import time

import dns.message

from .logger import log

DEFAULT_DOT = "dns.alidns.com"
DEFAULT_DOT_PORT = 853


def run_dot_check(domain, server=None, port=853, timeout=8):
    """
    执行 DoT 检测，返回结构化 dict。
    server 为空时使用 dns.alidns.com:853。
    """
    host = (server or DEFAULT_DOT).strip()
    # 去掉可能的 tls:// 前缀
    if host.startswith("tls://"):
        host = host[len("tls://"):]
    result = {
        "server": host,
        "port": int(port),
        "tcp_ok": False,
        "tls_ok": False,
        "domain": domain,
        "answers": [],
        "elapsed_ms": None,
        "error": "",
    }

    try:
        # 1) TCP 连通（853）
        start = time.perf_counter()
        raw = socket.create_connection((host, int(port)), timeout=timeout)
        result["tcp_ok"] = True
        log.ok(f"DoT 端口 {port} TCP 连通")

        # 2) TLS 握手（走系统 CA 校验证书）
        ctx = ssl.create_default_context()
        tls = ctx.wrap_socket(raw, server_hostname=host)
        tls.do_handshake()
        result["tls_ok"] = True
        log.ok(f"TLS 握手成功：{tls.version()} · {tls.cipher()[0]}")

        # 3) 发送 DNS 查询（2 字节长度前缀 + wire）
        q = dns.message.make_query(domain, "A")
        wire = q.to_wire()
        tls.sendall(struct.pack("!H", len(wire)) + wire)

        # 4) 读取响应
        hdr = _recv_exact(tls, 2, timeout)
        (rlen,) = struct.unpack("!H", hdr)
        body = _recv_exact(tls, rlen, timeout)
        result["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 2)

        resp_msg = dns.message.from_wire(body)
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
        log.ok(f"DoT 整体耗时 {result['elapsed_ms']} ms")
        tls.close()

    except socket.timeout:
        result["error"] = "DoT 连接超时"
        log.error(result["error"])
    except ConnectionRefusedError:
        result["error"] = f"连接被拒绝（{port} 端口未开放）"
        log.error(result["error"])
    except ssl.SSLCertVerificationError as e:
        result["error"] = f"DoT 证书校验失败: {e}"
        log.error(result["error"])
    except ssl.SSLError as e:
        result["error"] = f"TLS 握手失败: {e}"
        log.error(result["error"])
    except Exception as e:
        result["error"] = f"检测异常: {e}"
        log.error(result["error"])

    return result


def _recv_exact(sock, n, timeout):
    """精确读取 n 字节。"""
    sock.settimeout(timeout)
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise socket.error("连接被提前关闭")
        buf += chunk
    return buf
