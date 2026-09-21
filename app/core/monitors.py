# -*- coding: utf-8 -*-
"""
监控采集模块：定时采样 CPU / 内存 / 磁盘 / 网络流量。

- CPU/内存/磁盘：psutil 即时读取。
- 上下行流量：两次 net_io_counters 差值 / 时间间隔，得到实时速率。
"""
import time
import psutil


class TrafficMeter:
    """网络流量测速器：维护上一次采样，计算实时上下行速率(bytes/s)。"""

    def __init__(self):
        self._last = None
        self._last_ts = 0.0
        self.down_rate = 0.0   # 下行 bytes/s
        self.up_rate = 0.0     # 上行 bytes/s

    def tick(self):
        """采样一次并更新速率。返回 (down_rate, up_rate)。"""
        io = psutil.net_io_counters()
        now = time.time()
        if self._last is not None and (now - self._last_ts) > 0:
            dt = now - self._last_ts
            self.down_rate = (io.bytes_recv - self._last.bytes_recv) / dt
            self.up_rate = (io.bytes_sent - self._last.bytes_sent) / dt
        self._last = io
        self._last_ts = now
        return self.down_rate, self.up_rate


def collect_snapshot(meter):
    """
    采集一次完整快照，供首页仪表盘使用。
    返回 dict：cpu/mem/disk/流量等。
    """
    from . import system_info as si
    cpu = si.get_cpu_percent()
    total_mem, used_mem, mem_pct = si.get_memory()
    total_disk, used_disk, disk_pct, free_disk = si.get_disk()
    down, up = meter.tick()
    return {
        "cpu": cpu,
        "mem_pct": mem_pct,
        "mem_total": total_mem,
        "mem_used": used_mem,
        "disk_pct": disk_pct,
        "disk_total": total_disk,
        "disk_free": free_disk,
        "down_rate": down,
        "up_rate": up,
    }
