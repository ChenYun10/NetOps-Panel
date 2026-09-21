# -*- coding: utf-8 -*-
"""
高级网络功能模块：路由追踪、端口扫描、主机发现、摄像头扫描、
速度测试、DHCP 检测、IP 冲突检测等原有基础功能。

均采用后台线程 + log 输出，不阻塞 UI。
"""
import ipaddress
import re
import socket
import threading
import time

from .logger import log
from . import syscmd

# 常用端口列表（端口扫描默认目标）
COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445,
                465, 587, 993, 995, 1433, 1521, 3306, 3389, 5432, 6379,
                7001, 8000, 8080, 8443, 8888, 9000, 9090, 9200, 27017]

# RTSP / 摄像头相关端口
CAMERA_PORTS = [80, 554, 8000, 8080, 8081, 8554, 37777]


def traceroute(host, max_hops=30, timeout=1):
    """路由追踪：调用 Windows tracert 逐跳实时解析。"""
    log.info(f"开始路由追踪 {host}（最多 {max_hops} 跳）")
    try:
        # 流式输出：每读一行实时滚动，避免看起来像卡死
        syscmd.run_stream(
            ["tracert", "-d", "-h", str(max_hops), "-w",
             str(int(timeout * 1000)), host],
            line_cb=lambda line: log.info(line) if line.strip() else None,
        )
        log.ok("路由追踪完成")
    except Exception as e:
        log.error(f"路由追踪异常: {e}")


def port_scan(host, ports=None, timeout=2, workers=50):
    """端口扫描：多线程 TCP connect 探测。"""
    ports = ports or COMMON_PORTS
    log.info(f"开始扫描 {host} 的 {len(ports)} 个端口")
    open_ports = []
    lock = threading.Lock()

    def worker(p):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            if s.connect_ex((host, p)) == 0:
                with lock:
                    open_ports.append(p)
                    log.ok(f"端口 {p} 开放")
            s.close()
        except Exception:
            pass

    threads = []
    for p in ports:
        t = threading.Thread(target=worker, args=(p,), daemon=True)
        t.start()
        threads.append(t)
        # 简单限流，避免线程爆炸
        if len(threads) >= workers:
            for t in threads:
                t.join()
            threads = []
    for t in threads:
        t.join()

    if open_ports:
        log.ok(f"扫描完成，开放端口：{sorted(open_ports)}")
    else:
        log.warn("扫描完成，未发现开放端口")
    return sorted(open_ports)


def host_discover(subnet, timeout=1, workers=100):
    """
    主机发现：三阶段扫描提高发现率。

    1. ping 快速扫描（快速过滤）；
    2. 对 ping 未响应的地址，改用 TCP 探测常见端口
       （Windows 主机默认防火墙禁 ICMP，但 135/139/445/3389 等端口常开）；
    3. 合并本机 ARP 缓存中的同网段 IP。

    subnet 形如 '192.168.1.0/24' 或 '192.168.1'。
    """
    try:
        net = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        log.error(f"网段格式错误: {subnet}")
        return []
    hosts = [str(ip) for ip in net.hosts()]
    log.info(f"开始发现主机，网段 {subnet}（{len(hosts)} 个地址）")

    # 网段校验：本机 IP 不在目标网段时提醒（常见填错网段）
    try:
        from . import system_info as si
        local = ipaddress.ip_address(si.get_local_ip())
        if local not in net:
            log.warn(f"本机 IP {local} 不在目标网段 {subnet} 内，请确认网段是否正确")
    except Exception:
        pass

    alive = []
    ping_dead = []
    lock = threading.Lock()

    # ---- 阶段 1：并发 ping ----
    def ping_worker(ip):
        try:
            code, _ = syscmd.run(
                ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip],
                timeout=timeout + 1,
            )
            with lock:
                if code == 0:
                    alive.append(ip)
                    log.ok(f"发现存活主机: {ip}")
                else:
                    ping_dead.append(ip)
        except Exception:
            with lock:
                ping_dead.append(ip)

    _run_pool(ping_worker, hosts, workers)
    log.info(f"ping 阶段完成：{len(alive)} 台响应，{len(ping_dead)} 台未响应")

    # ---- 阶段 2：对未响应的做 TCP 端口探测 ----
    if ping_dead:
        log.info("对 ping 未响应的地址做 TCP 端口探测（识别禁 ICMP 的 Windows 主机）…")
        tcp_ports = [135, 139, 445, 3389, 22, 80, 443, 8080, 8000]

        def tcp_worker(ip):
            for p in tcp_ports:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(timeout)
                    if s.connect_ex((ip, p)) == 0:
                        with lock:
                            if ip not in alive:
                                alive.append(ip)
                                log.ok(f"发现设备: {ip}（TCP {p} 开放）")
                        s.close()
                        return
                    s.close()
                except Exception:
                    return

        _run_pool(tcp_worker, ping_dead, workers)

    # ---- 阶段 3：合并 ARP 缓存 ----
    try:
        arp_out = syscmd.run_capture(["arp", "-a"], timeout=8)
        for line in arp_out.splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})", line)
            if m:
                mac = m.group(2)
                if mac.lower() == "ff-ff-ff-ff-ff-ff":
                    continue  # 广播地址，跳过
                ip = m.group(1)
                try:
                    if ipaddress.ip_address(ip) in net and ip not in alive:
                        alive.append(ip)
                        log.ok(f"发现设备: {ip}（ARP 缓存，MAC {mac}）")
                except ValueError:
                    pass
    except Exception:
        pass

    alive.sort(key=lambda x: [int(p) for p in x.split(".")])
    log.ok(f"主机发现完成，共发现 {len(alive)} 台设备")
    return alive


def _run_pool(worker, items, workers=100):
    """按批次并发执行 worker(items)，每批不超过 workers 个线程。"""
    threads = []
    for it in items:
        t = threading.Thread(target=worker, args=(it,), daemon=True)
        t.start()
        threads.append(t)
        if len(threads) >= workers:
            for t in threads:
                t.join()
            threads = []
    for t in threads:
        t.join()


def camera_scan(hosts, timeout=2):
    """摄像头扫描：探测 RTSP/HTTP 常见端口。"""
    log.info("开始摄像头扫描")
    if isinstance(hosts, str):
        hosts = [hosts]
    for host in hosts:
        for p in CAMERA_PORTS:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                if s.connect_ex((host, p)) == 0:
                    log.ok(f"{host}:{p} 开放（可能是摄像头）")
                s.close()
            except Exception:
                pass
    log.ok("摄像头扫描完成")


def speed_test(url="http://speedtest.tele2.net/10MB.zip", timeout=20):
    """
    速度测试：下载一个测试文件测速。
    返回 (下载MB, 耗时秒, 速率Mbps)。
    """
    import urllib.request
    log.info(f"开始下载测速: {url}")
    start = time.perf_counter()
    total = 0
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NetOps-Panel/1.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if time.perf_counter() - start > timeout:
                break
        elapsed = time.perf_counter() - start
        mb = total / (1024 * 1024)
        mbps = (total * 8) / (elapsed * 1_000_000) if elapsed > 0 else 0
        log.ok(f"下载 {mb:.2f} MB，耗时 {elapsed:.2f}s，速率 {mbps:.2f} Mbps")
        return mb, elapsed, mbps
    except Exception as e:
        log.error(f"测速失败: {e}")
        return 0, 0, 0


def dhcp_check():
    """DHCP 检测：解析 ipconfig /all 里的 DHCP 服务器与租约信息。"""
    log.info("开始 DHCP 检测")
    try:
        out = syscmd.run_capture(["ipconfig", "/all"], timeout=8)
        in_dhcp = False
        for line in out.splitlines():
            low = line.lower()
            if "dhcp" in low and ("server" in low or "服务器" in line):
                log.info(f"DHCP 服务器: {line.split(':', 1)[-1].strip()}")
                in_dhcp = True
            elif "lease" in low and ("obtained" in low or "获得" in line):
                log.info(f"租约获取: {line.split(':', 1)[-1].strip()}")
            elif "lease" in low and ("expires" in low or "过期" in line):
                log.info(f"租约过期: {line.split(':', 1)[-1].strip()}")
        if not in_dhcp:
            log.warn("未检测到 DHCP 服务器（可能是静态 IP）")
        log.ok("DHCP 检测完成")
    except Exception as e:
        log.error(f"DHCP 检测失败: {e}")


def ip_conflict_check(local_ip=None):
    """
    IP 冲突检测：通过 ARP 表检查是否存在重复 IP 的 MAC。
    （Windows 原生 arp -a 输出解析）
    """
    log.info("开始 IP 冲突检测（基于 ARP 表）")
    try:
        out = syscmd.run_capture(["arp", "-a"], timeout=8)
        # 统计每个 IP 出现的次数，出现多次即为疑似冲突
        ip_counter = {}
        for line in out.splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})", line)
            if m:
                ip = m.group(1)
                ip_counter.setdefault(ip, set()).add(m.group(2))
        conflicts = [ip for ip, macs in ip_counter.items() if len(macs) > 1]
        if conflicts:
            for ip in conflicts:
                log.warn(f"疑似 IP 冲突: {ip} -> {ip_counter[ip]}")
        else:
            log.ok("未发现 IP 冲突")
        log.ok("IP 冲突检测完成")
        return conflicts
    except Exception as e:
        log.error(f"IP 冲突检测失败: {e}")
        return []


def session_test(host, port=443, count=5, timeout=3):
    """会话测试：反复建立 TCP 连接统计成功率与延迟。"""
    log.info(f"会话测试 {host}:{port}，{count} 次")
    ok = 0
    rtts = []
    for i in range(count):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            start = time.perf_counter()
            s.connect((host, port))
            rtt = (time.perf_counter() - start) * 1000
            rtts.append(rtt)
            ok += 1
            s.close()
            log.ok(f"第 {i + 1} 次成功，RTT {rtt:.1f} ms")
        except Exception as e:
            log.error(f"第 {i + 1} 次失败: {e}")
    if ok:
        avg = sum(rtts) / len(rtts)
        log.ok(f"会话测试完成：成功率 {ok}/{count}，平均延迟 {avg:.1f} ms")
    else:
        log.warn(f"会话测试完成：全部失败（{count}/{count}）")
