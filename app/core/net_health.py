# -*- coding: utf-8 -*-
"""
网络基础检测模块：Ping 延迟、TCP 连通、外网连通性。

- ping：Windows 原生 `ping -n 1` 解析延迟（避免 root 权限 raw socket）。
- tcp_connect：socket 三次握手 + 计时。
- 外网连通：连多个公网目标判断。
"""
import re
import socket
import time
import threading

from .logger import log
from . import syscmd


def ping(host, timeout=3):
    """
    用 Windows 原生 ping 检测单次延迟。
    返回 (成功bool, 延迟ms 或 None, 错误信息)。
    """
    try:
        code, text = syscmd.run(
            ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host],
            timeout=timeout + 2,
        )
        if code != 0:
            return False, None, "目标不可达(超时/无响应)"
        # 中文/英文系统兼容：匹配 '时间=xxms' 或 'time=xxms' 或 'time<xxms'
        m = re.search(r"(?:时间|time)[=<]\s*(\d+)\s*ms", text, re.I)
        if m:
            return True, int(m.group(1)), ""
        if "TTL=" in text or "ttl=" in text:
            return True, 0, ""  # 通了但没解析到时间
        return False, None, "无响应"
    except Exception as e:
        return False, None, str(e)


def tcp_connect(host, port, timeout=3):
    """
    TCP 三次握手检测。
    返回 (成功bool, RTT毫秒, 错误信息)。
    RTT 用 connect 阻塞耗时近似（含三次握手与本地内核处理）。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    start = time.perf_counter()
    try:
        s.connect((host, port))
        rtt = (time.perf_counter() - start) * 1000
        return True, rtt, ""
    except socket.timeout:
        return False, None, "连接超时"
    except ConnectionRefusedError:
        return False, None, "连接被拒绝"
    except ConnectionResetError:
        return False, None, "连接被重置"
    except OSError as e:
        return False, None, str(e)
    finally:
        s.close()


def check_internet(targets=None, timeout=3):
    """
    外网连通性检测：依次 TCP 连 80/443 端口。
    返回 (是否通外网, 详情列表[(目标, 结果, 延迟ms)]).
    """
    if targets is None:
        targets = [
            ("8.8.8.8", 53),
            ("223.5.5.5", 53),
            ("www.baidu.com", 443),
        ]
    detail = []
    any_ok = False
    for host, port in targets:
        ok, rtt, err = tcp_connect(host, port, timeout)
        detail.append((f"{host}:{port}", ok, rtt, err))
        if ok:
            any_ok = True
    return any_ok, detail


def ping_async(host, timeout, callback):
    """
    在后台线程执行 ping，完成后回调 callback(success, ms, err)。
    供 UI 异步调用，避免阻塞界面。
    """
    def worker():
        ok, ms, err = ping(host, timeout)
        callback(ok, ms, err)
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t
