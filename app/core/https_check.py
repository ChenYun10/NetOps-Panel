# -*- coding: utf-8 -*-
"""
【3】HTTPS 检测模块。

检测项目：
- TLS 协议版本、加密套件；
- 证书信息（签发机构、有效期、SAN 域名、本地信任状态）；
- HTTPS 握手耗时、证书链完整性校验、TLS 降级风险判断。

实现：标准库 socket + ssl（走 Windows 系统 CA 信任库）。
"""
import socket
import ssl
import time

from .logger import log


def _tls_handshake(host, port, timeout, verify=True):
    """
    建立 TLS 连接。verify=True 时走系统 CA 校验证书链（CERT_REQUIRED）。
    返回 (ssock, rtt_ms)。
    """
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    start = time.perf_counter()
    raw = socket.create_connection((host, port), timeout=timeout)
    try:
        ssock = ctx.wrap_socket(raw, server_hostname=host)
        rtt = (time.perf_counter() - start) * 1000
        return ssock, rtt
    except Exception:
        raw.close()
        raise


def _probe_old_tls(host, port, timeout):
    """探测是否支持 TLS 1.0 / 1.1（降级风险）。返回支持列表。"""
    supported = []
    for ver, label in ((ssl.TLSVersion.TLSv1, "TLS 1.0"),
                       (ssl.TLSVersion.TLSv1_1, "TLS 1.1")):
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.minimum_version = ver
            ctx.maximum_version = ver
            raw = socket.create_connection((host, port), timeout=timeout)
            with ctx.wrap_socket(raw, server_hostname=host) as s:
                s.do_handshake()
            supported.append(label)
        except Exception:
            pass
    return supported


def run_https_check(host, port=443, timeout=8):
    """
    执行 HTTPS 检测，返回结构化 dict。
    """
    result = {
        "conn_ok": False,
        "handshake_ms": None,
        "tls_version": "",
        "cipher": "",
        "cert": None,
        "chain_ok": False,
        "local_trust": False,
        "downgrade_risk": [],
        "error": "",
    }

    try:
        # 主握手：严格校验（证书链完整性 + 本地信任）
        ssock, rtt = _tls_handshake(host, port, timeout, verify=True)
        result["conn_ok"] = True
        result["handshake_ms"] = round(rtt, 2)
        result["tls_version"] = ssock.version()
        result["cipher"] = ssock.cipher()[0]
        result["chain_ok"] = True      # CERT_REQUIRED 握手成功 => 链完整
        result["local_trust"] = True   # 走系统 CA => 本地信任
        log.ok(f"HTTPS 握手成功，耗时 {rtt:.2f} ms")
        log.ok(f"TLS 协议版本：{ssock.version()}")
        log.ok(f"加密套件：{ssock.cipher()[0]}")

        # 证书信息
        cert = ssock.getpeercert()
        result["cert"] = cert
        _report_cert(cert)
        ssock.close()

        # 降级风险探测
        old = _probe_old_tls(host, port, timeout)
        result["downgrade_risk"] = old
        if old:
            log.warn(f"存在 TLS 降级风险：仍支持 {'、'.join(old)}")
        else:
            log.ok("未发现 TLS 降级风险（不支持 TLS 1.0/1.1）")

    except ssl.SSLCertVerificationError as e:
        result["error"] = f"证书链校验失败（不受信任）: {e}"
        log.error(result["error"])
        # 证书链可能不完整或不受本地信任
        result["chain_ok"] = False
        result["local_trust"] = False
    except ssl.SSLError as e:
        result["error"] = f"TLS 握手失败: {e}"
        log.error(result["error"])
    except socket.timeout:
        result["error"] = "连接超时"
        log.error(result["error"])
    except ConnectionRefusedError:
        result["error"] = "连接被拒绝（端口未开放）"
        log.error(result["error"])
    except Exception as e:
        result["error"] = f"检测异常: {e}"
        log.error(result["error"])

    return result


def _report_cert(cert):
    """把证书信息格式化打印到日志。"""
    if not cert:
        log.warn("未获取到证书信息")
        return
    issuer = ", ".join(x[0][1] for x in cert.get("issuer", ()) if x[0][0] == "commonName")
    subject = ", ".join(x[0][1] for x in cert.get("subject", ()) if x[0][0] == "commonName")
    not_after = cert.get("notAfter", "")
    not_before = cert.get("notBefore", "")
    san = cert.get("subjectAltName", ())
    log.info(f"证书主体：{subject or '(未知)'}")
    log.info(f"签发机构：{issuer or '(未知)'}")
    log.info(f"有效期：{not_before} ~ {not_after}")
    if san:
        names = [v for _, v in san]
        log.info(f"SAN 域名：{', '.join(names[:8])}")
