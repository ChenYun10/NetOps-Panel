# -*- coding: utf-8 -*-
"""
iperf 内网测速模块。

支持两种模式：
1. iperf3/iperf 客户端模式（首选）：调用系统 iperf3 -c 连接 iperf 服务端，
   解析 JSON 输出得到真实吞吐量；
2. 纯 Python TCP 吞吐量模式（兜底）：连到任意 TCP 服务端持续收发数据，
   估算吞吐量（无需安装 iperf3，但服务端需为普通 TCP 服务）。

用户可主动连接内网任意 iperf 服务端。
"""
import json
import os
import shutil
import socket
import sys
import threading
import time

from .logger import log
from . import syscmd


def _bundled_iperf3():
    """定位内置的 iperf3.exe（打包后从 sys._MEIPASS 取，开发时取项目 bin 目录）。"""
    candidates = []
    # PyInstaller onefile 运行时资源解压目录
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "iperf3.exe"))
    # 开发环境：项目根目录下的 bin/
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates.append(os.path.join(base, "bin", "iperf3.exe"))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def find_iperf():
    """
    检测 iperf3 / iperf 命令，优先使用内置的 iperf3.exe。
    返回 (命令名, 完整路径) 或 (None, None)。
    """
    bundled = _bundled_iperf3()
    if bundled:
        return "iperf3", bundled
    for cmd in ("iperf3", "iperf"):
        path = shutil.which(cmd)
        if path:
            return cmd, path
    return None, None


def run_iperf_test(server, port=5201, duration=10, reverse=False, udp=False):
    """
    用 iperf3/iperf 客户端连接服务端测速。

    reverse=True 表示下载（-R，服务端→客户端），否则上传。
    返回结构化 dict，含吞吐量 Mbps。
    """
    cmd_name, path = find_iperf()
    if not cmd_name:
        log.error("未检测到 iperf3 客户端")
        log.info("下载 iperf3：https://iperf.fr/iperf-download.php")
        log.info("Windows 版解压后，把 iperf3.exe 放到本程序目录或系统 PATH 即可")
        return {"error": "iperf3 未安装", "throughput_mbps": None}

    args = [path, "-c", server, "-p", str(port), "-t", str(duration)]
    if reverse:
        args.append("-R")
    if udp:
        args.append("-u")
    if cmd_name == "iperf3":
        args.append("-J")  # JSON 输出，便于精确解析

    direction = "下载" if reverse else "上传"
    proto = "UDP" if udp else "TCP"
    log.info(f"iperf3 连接 {server}:{port}（{proto} · {direction} · {duration}s）…")

    code, out = syscmd.run(args, timeout=duration + 20)
    result = {"server": server, "port": port, "throughput_mbps": None, "error": ""}

    if code != 0 or not out:
        result["error"] = f"iperf3 执行失败（退出码 {code}），请确认服务端已启动"
        log.error(result["error"])
        log.info("服务端启动示例：iperf3 -s -p 5201")
        return result

    # 尝试解析 JSON（iperf3 -J），失败则打印原始文本
    mbps = _parse_iperf3_json(out, reverse)
    if mbps is not None:
        result["throughput_mbps"] = mbps
        log.ok(f"iperf3 测速完成：{direction}吞吐量 {mbps:.2f} Mbps")
    else:
        # iperf2 或非 JSON 输出，直接展示末尾几行
        for line in out.splitlines()[-6:]:
            log.info(line)
        mbps = _parse_iperf2_text(out)
        if mbps is not None:
            result["throughput_mbps"] = mbps
            log.ok(f"iperf 测速完成：{mbps:.2f} Mbps")
        else:
            log.warn("未能从输出解析吞吐量，请查看上方原始结果")
    return result


def _parse_iperf3_json(out, reverse):
    """从 iperf3 -J 的 JSON 输出解析吞吐量(bps→Mbps)。"""
    try:
        data = json.loads(out)
        end = data.get("end", {})
        key = "sum_received" if reverse else "sum_sent"
        stream = end.get(key) or end.get("sum") or {}
        bps = stream.get("bits_per_second") or stream.get("bandwidth")
        if bps:
            return bps / 1_000_000
    except Exception:
        pass
    return None


def _parse_iperf2_text(out):
    """从 iperf2 文本输出解析吞吐量（Mbits/sec）。"""
    import re
    # 匹配 "... Mbits/sec" 或 "... Gbits/sec"
    m = re.findall(r"([\d.]+)\s*(Mbits|Gbits)/sec", out)
    if m:
        val, unit = m[-1]
        v = float(val)
        return v * 1000 if unit == "Gbits" else v
    return None


def run_tcp_throughput(server, port=5201, duration=10, reverse=False):
    """
    纯 Python TCP 吞吐量测试（兜底，无需 iperf3）。

    reverse=False（上传）：持续向服务端发送数据；
    reverse=True（下载）：持续从服务端接收数据。
    统计 duration 秒内的传输字节数，换算 Mbps。
    """
    log.info(f"TCP 吞吐量测试 {server}:{port}（{'下载' if reverse else '上传'} · {duration}s）")
    try:
        s = socket.create_connection((server, port), timeout=10)
    except Exception as e:
        log.error(f"连接服务端失败: {e}")
        return {"error": str(e), "throughput_mbps": None}

    counter = {"bytes": 0}
    stop = threading.Event()

    def tx_loop():
        chunk = b"0" * (64 * 1024)  # 64KB 块
        while not stop.is_set():
            try:
                s.sendall(chunk)
                counter["bytes"] += len(chunk)
            except Exception:
                break

    def rx_loop():
        while not stop.is_set():
            try:
                data = s.recv(64 * 1024)
                if not data:
                    break
                counter["bytes"] += len(data)
            except Exception:
                break

    t = threading.Thread(target=tx_loop if not reverse else rx_loop, daemon=True)
    t.start()
    time.sleep(duration)
    stop.set()
    try:
        s.close()
    except Exception:
        pass
    t.join(timeout=2)

    total_bits = counter["bytes"] * 8
    mbps = total_bits / duration / 1_000_000
    log.ok(f"TCP 吞吐量测试完成：{mbps:.2f} Mbps")
    return {"server": server, "port": port, "throughput_mbps": round(mbps, 2), "error": ""}
