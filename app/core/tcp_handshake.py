# -*- coding: utf-8 -*-
"""
【1】TCP 应用层握手检测模块（原生调用 Windows 网络栈）。

流程：
  1. socket.create_connection 完成 TCP 三次握手，计时得到握手 RTT；
  2. 按所选应用协议执行上层握手交互：
     - 裸TCP : 仅验证三次握手，不发应用层数据；
     - HTTP  : 发送 GET / 请求，校验 HTTP 响应状态行；
     - SSH   : 等待服务器 Banner，完成 SSH 版本识别；
     - TLS   : 发送 Client Hello，完成 TLS 握手并读取协商结果。

输出：TCP 握手状态、握手延迟、应用层握手状态、错误详情。
"""
import socket
import ssl
import time

from .logger import log


def _resolve(host):
    """域名解析为 IP（返回首选 IPv4）。"""
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
        return infos[0][4][0]
    except socket.gaierror as e:
        raise ConnectionError(f"域名解析失败: {e}")


def _tcp_handshake(host, port, timeout):
    """
    完成 TCP 三次握手并返回 (sock, rtt_ms)。
    抛异常时附带友好错误信息。
    """
    start = time.perf_counter()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except socket.timeout:
        raise ConnectionError("连接超时（TCP 握手无响应）")
    except ConnectionRefusedError:
        raise ConnectionError("连接被拒绝（端口未开放）")
    except ConnectionResetError:
        raise ConnectionError("连接被重置（RST）")
    except OSError as e:
        raise ConnectionError(f"连接失败: {e}")
    rtt = (time.perf_counter() - start) * 1000
    sock.settimeout(timeout)
    return sock, rtt


def _http_interact(sock, host, timeout):
    """HTTP：发送 GET 请求，返回状态行。"""
    req = (f"GET / HTTP/1.1\r\nHost: {host}\r\n"
           f"User-Agent: NetOps-Panel/1.0\r\n"
           f"Accept: */*\r\nConnection: close\r\n\r\n")
    sock.sendall(req.encode("utf-8"))
    data = sock.recv(4096)
    if not data:
        raise ConnectionError("服务器未返回 HTTP 响应")
    line = data.decode("utf-8", "replace").split("\r\n")[0]
    return line


def _ssh_interact(sock, timeout):
    """SSH：发送客户端 Banner 并读取服务器 Banner，识别版本。"""
    # 客户端先声明自己的 SSH 版本（标准 SSH 握手双方都先发 banner）
    sock.sendall(b"SSH-2.0-NetOps-Panel_1.0\r\n")
    banner = b""
    try:
        while b"\n" not in banner:
            chunk = sock.recv(64)
            if not chunk:
                break
            banner += chunk
    except socket.timeout:
        if not banner:
            raise ConnectionError("等待 SSH Banner 超时")
    banner = banner.decode("utf-8", "replace").strip()
    if not banner.startswith("SSH-"):
        raise ConnectionError(f"非 SSH 服务，收到: {banner[:50] or '(空)'}")
    return banner


def _tls_interact(sock, host, timeout):
    """TLS：Client Hello + 握手，返回协商的版本/套件。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # 检测场景只验证握手，不强制证书链
    try:
        tls = ctx.wrap_socket(sock, server_hostname=host)
        tls.do_handshake()
        return tls.version(), tls.cipher()[0]
    except ssl.SSLError as e:
        raise ConnectionError(f"TLS 握手失败: {e}")
    finally:
        try:
            sock.close()
        except Exception:
            pass


def run_tcp_app_check(host, port, protocol, timeout=5):
    """
    执行 TCP 应用层握手检测。
    返回结构化 dict：
      {tcp_ok, tcp_rtt_ms, app_ok, app_detail, error}
    """
    result = {
        "tcp_ok": False,
        "tcp_rtt_ms": None,
        "app_ok": False,
        "app_detail": "",
        "error": "",
    }

    ip = host
    try:
        # 若是域名则先解析，记录真实连接目标
        try:
            socket.inet_aton(host)
        except OSError:
            ip = _resolve(host)
            log.info(f"域名 {host} 解析为 {ip}")

        # 1) TCP 三次握手
        sock, rtt = _tcp_handshake(ip, port, timeout)
        result["tcp_ok"] = True
        result["tcp_rtt_ms"] = round(rtt, 2)
        log.ok(f"TCP 三次握手成功，RTT = {rtt:.2f} ms")

        # 2) 应用层握手
        if protocol == "裸TCP":
            result["app_ok"] = True
            result["app_detail"] = "仅验证 TCP 三次握手，未发送应用层数据"
            log.info(result["app_detail"])
            sock.close()
        elif protocol == "HTTP":
            try:
                line = _http_interact(sock, host, timeout)
                result["app_ok"] = True
                result["app_detail"] = f"HTTP 响应: {line}"
                log.ok(f"HTTP 握手成功：{line}")
            except Exception as e:
                result["error"] = str(e)
                log.error(f"HTTP 应用层失败: {e}")
            finally:
                sock.close()
        elif protocol == "SSH":
            try:
                banner = _ssh_interact(sock, timeout)
                result["app_ok"] = True
                result["app_detail"] = f"SSH Banner: {banner}"
                log.ok(f"SSH 版本识别：{banner}")
            except Exception as e:
                result["error"] = str(e)
                log.error(f"SSH 应用层失败: {e}")
            finally:
                sock.close()
        elif protocol == "TLS":
            try:
                version, cipher = _tls_interact(sock, host, timeout)
                result["app_ok"] = True
                result["app_detail"] = f"TLS {version} / {cipher}"
                log.ok(f"TLS 握手成功：{version} · 套件 {cipher}")
            except Exception as e:
                result["error"] = str(e)
                log.error(f"TLS 应用层失败: {e}")

    except ConnectionError as e:
        result["error"] = str(e)
        log.error(f"TCP 握手失败: {e}")
    except Exception as e:
        result["error"] = str(e)
        log.error(f"检测异常: {e}")

    return result
