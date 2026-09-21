# -*- coding: utf-8 -*-
"""
首页工作台面板。

- 顶部信息卡片：本机 IP、网关、DNS、外网连通性 + 各节点 Ping 延迟；
- 中部：CPU/内存/磁盘环形仪表盘 + 实时上下行流量曲线；
- 底部：系统信息（主机名、运行时长、内存剩余、磁盘剩余）。
"""
import tkinter as tk
import threading

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import theme
from app.ui.widgets import RingGauge, TrafficChart, StatCard
from app.core import system_info as si
from app.core import monitors
from app.core import net_health

# 外网连通性检测的参考节点
PING_NODES = ["223.5.5.5", "114.114.114.114", "8.8.8.8", "www.baidu.com"]


class Dashboard(tk.Frame):
    """首页工作台页面。"""

    def __init__(self, parent):
        super().__init__(parent, bg=theme.BG)
        self.meter = monitors.TrafficMeter()
        self._build()
        self._refresh_metrics()
        self._refresh_nodes()

    # ---------- 构建 UI ----------
    def _build(self):
        # ===== 顶部信息卡片行 =====
        top = tk.Frame(self, bg=theme.BG)
        top.pack(fill="x", padx=16, pady=(16, 8))
        for i in range(4):
            top.grid_columnconfigure(i, weight=1, uniform="cards")

        self.card_ip = StatCard(top, "本机 IP", "--", theme.TEXT_ACCENT)
        self.card_ip.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=10, ipadx=10)

        self.card_gw = StatCard(top, "网关", "--", theme.TEXT_ACCENT)
        self.card_gw.grid(row=0, column=1, sticky="ew", padx=8, ipady=10, ipadx=10)

        self.card_dns = StatCard(top, "DNS 服务器", "--", theme.TEXT_ACCENT)
        self.card_dns.grid(row=0, column=2, sticky="ew", padx=8, ipady=10, ipadx=10)

        self.card_net = StatCard(top, "外网连通", "检测中…", theme.ORANGE)
        self.card_net.grid(row=0, column=3, sticky="ew", padx=(8, 0), ipady=10, ipadx=10)

        # ===== 中部：仪表盘 + 流量曲线 =====
        mid = tk.Frame(self, bg=theme.BG)
        mid.pack(fill="both", expand=True, padx=16, pady=8)

        # 左侧：3 个环形仪表盘
        gauges = tk.Frame(mid, bg=theme.BG)
        gauges.pack(side="left", fill="y")
        self.gauge_cpu = RingGauge(gauges, "CPU 占用", theme.CPU_COLOR)
        self.gauge_cpu.pack(side="left", padx=6)
        self.gauge_mem = RingGauge(gauges, "内存占用", theme.MEM_COLOR)
        self.gauge_mem.pack(side="left", padx=6)
        self.gauge_disk = RingGauge(gauges, "磁盘占用", theme.DISK_COLOR)
        self.gauge_disk.pack(side="left", padx=6)

        # 右侧：流量曲线
        chart_wrap = tk.Frame(mid, bg=theme.BG_CARD, highlightbackground=theme.BORDER,
                              highlightthickness=1)
        chart_wrap.pack(side="left", fill="both", expand=True, padx=(16, 0))
        tk.Label(chart_wrap, text="实时上下行流量", bg=theme.BG_CARD, fg=theme.TEXT,
                 font=theme.font(11, bold=True)).pack(anchor="w", padx=10, pady=(8, 0))
        self.chart = TrafficChart(chart_wrap, height=180)
        self.chart.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # ===== 底部：系统信息 + 节点延迟 =====
        bottom = tk.Frame(self, bg=theme.BG)
        bottom.pack(fill="x", padx=16, pady=(8, 16))

        sys_card = tk.Frame(bottom, bg=theme.BG_CARD, highlightbackground=theme.BORDER,
                            highlightthickness=1)
        sys_card.pack(side="left", fill="both", expand=True)
        tk.Label(sys_card, text="系统信息", bg=theme.BG_CARD, fg=theme.TEXT,
                 font=theme.font(11, bold=True)).pack(anchor="w", padx=10, pady=(8, 4))
        self.sys_lbl = tk.Label(sys_card, text="", bg=theme.BG_CARD, fg=theme.TEXT_DIM,
                                font=theme.font(9, mono=True), justify="left", anchor="w")
        self.sys_lbl.pack(anchor="w", padx=10, pady=(0, 10))

        node_card = tk.Frame(bottom, bg=theme.BG_CARD, highlightbackground=theme.BORDER,
                             highlightthickness=1)
        node_card.pack(side="left", fill="both", expand=True, padx=(16, 0))
        tk.Label(node_card, text="节点 Ping 延迟", bg=theme.BG_CARD, fg=theme.TEXT,
                 font=theme.font(11, bold=True)).pack(anchor="w", padx=10, pady=(8, 4))
        self.node_lbl = tk.Label(node_card, text="检测中…", bg=theme.BG_CARD,
                                 fg=theme.TEXT_DIM, font=theme.font(9, mono=True),
                                 justify="left", anchor="w")
        self.node_lbl.pack(anchor="w", padx=10, pady=(0, 10))

    # ---------- 定时刷新 ----------
    def _refresh_metrics(self):
        """每秒刷新 CPU/内存/磁盘/流量。"""
        try:
            snap = monitors.collect_snapshot(self.meter)
            self.gauge_cpu.set(snap["cpu"])
            self.gauge_mem.set(snap["mem_pct"], f"{snap['mem_used']:.1f}/{snap['mem_total']:.1f} GB")
            self.gauge_disk.set(snap["disk_pct"], f"剩余 {snap['disk_free']:.1f} GB")
            self.chart.push(snap["down_rate"], snap["up_rate"])

            # 系统信息
            hostname = si.get_hostname()
            uptime = si.format_uptime(si.get_uptime_seconds())
            total_mem, used_mem, _ = si.get_memory()
            _, _, _, free_disk = si.get_disk()
            self.sys_lbl.config(text=(
                f"主机名     : {hostname}\n"
                f"运行时长   : {uptime}\n"
                f"内存剩余   : {total_mem - used_mem:.1f} GB\n"
                f"磁盘剩余   : {free_disk:.1f} GB\n"
                f"操作系统   : {si.get_os_info()}"
            ))
        except Exception:
            pass
        self.after(1000, self._refresh_metrics)

    def _refresh_nodes(self):
        """刷新信息卡片 + 后台 ping 节点延迟。"""
        # 本机信息（即时）
        self.card_ip.set(si.get_local_ip())
        self.card_gw.set(si.get_gateway())
        dns = si.get_dns_servers()
        self.card_dns.set(dns[0] if dns else "未检测到",
                          sub=", ".join(dns[1:]) if len(dns) > 1 else "")

        # 外网连通 + 节点延迟（后台线程，避免阻塞）
        def worker():
            ok, detail = net_health.check_internet()
            node_texts = []
            for host in PING_NODES:
                pok, ms, _ = net_health.ping(host, 2)
                if pok:
                    color = theme.GREEN if ms < 80 else (theme.ORANGE if ms < 200 else theme.RED)
                    node_texts.append(f"{host:<20} {ms} ms")
                else:
                    node_texts.append(f"{host:<20} 超时")
            self.after(0, self._apply_nodes, ok, "\n".join(node_texts))

        threading.Thread(target=worker, daemon=True).start()
        self.after(10000, self._refresh_nodes)

    def _apply_nodes(self, ok, node_text):
        """在主线程更新外网连通卡片与节点延迟。"""
        if ok:
            self.card_net.set("已连接", theme.GREEN, sub="外网可达")
        else:
            self.card_net.set("断开", theme.RED, sub="外网不可达")
        self.node_lbl.config(text=node_text)
