# -*- coding: utf-8 -*-
"""
主窗口模块：左侧竖向导航菜单 + 右侧卡片式工作台布局。

- 左侧：分组导航菜单（可滚动），点击切换右侧页面；
- 右侧：内容区，懒加载 + 缓存各功能页面。
"""
import tkinter as tk

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import theme
from app.ui.dashboard import Dashboard
from app.ui.widgets import LogPanel
from app.core.logger import log

# 菜单分组定义：(分组标题, [(页面key, 菜单名, 类型), ...])
MENU_GROUPS = [
    ("概览", [
        ("overview", "概览", "dashboard"),
        ("workspace", "工作台", "dashboard"),
    ]),
    ("基础检测", [
        ("diag", "诊断检测", "diag"),
        ("health", "网络健康", "health"),
        ("ping", "Ping测试", "ping"),
        ("traceroute", "路由追踪", "traceroute"),
        ("portscan", "端口扫描", "portscan"),
        ("hostdiscover", "主机发现", "hostdiscover"),
        ("camera", "摄像头扫描", "camera"),
        ("security", "安全自测", "security"),
        ("audit", "日志审计", "audit"),
        ("ipconflict", "IP冲突检测", "ipconflict"),
    ]),
    ("测速与会话", [
        ("speed", "速度测试", "speed"),
        ("speed_wan", "外网测速", "speed"),
        ("speed_lan", "内网测速", "iperf"),
        ("session", "会话测试", "session"),
    ]),
    ("分析与抓包", [
        ("analysis", "网络分析", "analysis"),
        ("capture", "数据抓包", "capture"),
        ("dhcp", "DHCP检测", "dhcp"),
    ]),
    ("高级检测", [
        ("tcp", "TCP握手检测", "tcp"),
        ("ssh", "SSH检测", "ssh"),
        ("https", "HTTPS检测", "https"),
        ("doh", "DoH检测", "doh"),
        ("dot", "DoT检测", "dot"),
    ]),
    ("IPv6 与公网", [
        ("ipv6", "IPv6检测", "ipv6"),
        ("ipv6_forward", "IPv6网关转发测试", "ipv6_forward"),
        ("ipv6_conn", "IPv6连通性测试", "ipv6_conn"),
        ("expose", "公网暴露测试", "expose"),
        ("upnp", "UPnP状态", "upnp"),
    ]),
]


class AuditPage(tk.Frame):
    """日志审计页：回放历史日志 + 实时接收全局日志。"""

    def __init__(self, parent, root):
        super().__init__(parent, bg=theme.BG)
        self.root = root
        self.panel = LogPanel(self, height=22)
        self.panel.pack(fill="both", expand=True, padx=16, pady=16)
        # 回放历史
        for level, msg, _ in log.history():
            self.panel.append(level, msg)
        log.add_listener(self._cb)

    def _cb(self, level, msg):
        try:
            self.root.after(0, self.panel.append, level, msg)
        except Exception:
            pass


class MainWindow:
    """主窗口控制器。"""

    def __init__(self, root):
        self.root = root
        self.pages = {}          # key -> page 实例（缓存）
        self._menu_buttons = {}  # key -> 按钮（用于高亮）
        self.current_key = None
        self._build_sidebar()
        self._build_content()
        self.show("overview")

    # ---------- 侧边栏 ----------
    def _build_sidebar(self):
        sidebar = tk.Frame(self.root, bg=theme.BG_SIDE, width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Logo
        logo = tk.Frame(sidebar, bg=theme.BG_SIDE, height=64)
        logo.pack(fill="x")
        logo.pack_propagate(False)
        tk.Label(logo, text="◉ NetOps Panel", bg=theme.BG_SIDE, fg=theme.TEXT_ACCENT,
                 font=theme.font(14, bold=True)).pack(side="left", padx=16)
        tk.Label(logo, text="网络运维检测", bg=theme.BG_SIDE, fg=theme.TEXT_FAINT,
                 font=theme.font(8)).pack(side="left", padx=4)

        # 可滚动菜单区
        canvas = tk.Canvas(sidebar, bg=theme.BG_SIDE, highlightthickness=0)
        scroll = tk.Scrollbar(sidebar, command=canvas.yview, bg=theme.BG_SIDE)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        menu_frame = tk.Frame(canvas, bg=theme.BG_SIDE)
        self._menu_window = canvas.create_window((0, 0), window=menu_frame, anchor="nw")
        menu_frame.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(
            self._menu_window, width=e.width))

        # 逐组添加菜单
        for group_title, items in MENU_GROUPS:
            tk.Label(menu_frame, text=group_title, bg=theme.BG_SIDE,
                     fg=theme.TEXT_FAINT, font=theme.font(8, bold=True),
                     anchor="w").pack(fill="x", padx=16, pady=(12, 4))
            for key, label, _type in items:
                btn = tk.Button(
                    menu_frame, text="  " + label, anchor="w",
                    command=lambda k=key: self.show(k),
                    bg=theme.BG_SIDE, fg=theme.TEXT, relief="flat", bd=0,
                    activebackground=theme.BG_HOVER, activeforeground=theme.TEXT,
                    font=theme.font(10), padx=16, pady=6, cursor="hand2")
                btn.pack(fill="x")
                self._menu_buttons[key] = btn

    # ---------- 内容区 ----------
    def _build_content(self):
        self.content = tk.Frame(self.root, bg=theme.BG)
        self.content.pack(side="left", fill="both", expand=True)

    # ---------- 页面路由 ----------
    def show(self, key):
        # 切换高亮
        if self.current_key and self.current_key in self._menu_buttons:
            self._menu_buttons[self.current_key].config(bg=theme.BG_SIDE)
        if key in self._menu_buttons:
            self._menu_buttons[key].config(bg=theme.BG_HOVER)
        self.current_key = key

        # 隐藏旧页面
        for k, page in self.pages.items():
            if hasattr(page, "on_hide"):
                page.on_hide()
            page.pack_forget()

        # 加载/显示目标页面
        page = self._get_page(key)
        page.pack(fill="both", expand=True)
        if hasattr(page, "on_show"):
            page.on_show()

    def _get_page(self, key):
        """懒加载页面并缓存。"""
        if key in self.pages:
            return self.pages[key]
        page = self._create_page(key)
        self.pages[key] = page
        return page

    def _create_page(self, key):
        """根据 key 创建对应页面实例。"""
        from app.ui import detector_pages as dp
        # 找到菜单类型
        ptype = None
        for _, items in MENU_GROUPS:
            for k, _lbl, t in items:
                if k == key:
                    ptype = t
                    break
        parent, root = self.content, self.root

        if ptype == "dashboard":
            return Dashboard(parent)
        if ptype == "audit":
            return AuditPage(parent, root)
        if ptype == "tcp":
            return dp.make_tcp_page(parent, root)
        if ptype == "ssh":
            return dp.make_ssh_page(parent, root)
        if ptype == "https":
            return dp.make_https_page(parent, root)
        if ptype == "doh":
            return dp.make_doh_page(parent, root)
        if ptype == "dot":
            return dp.make_dot_page(parent, root)
        if ptype == "ipv6":
            return dp.make_ipv6_page(parent, root)
        if ptype == "ipv6_forward":
            return dp.make_ipv6_forward_page(parent, root)
        if ptype == "ipv6_conn":
            return dp.make_ipv6_conn_page(parent, root)
        if ptype == "expose":
            return dp.make_expose_page(parent, root)
        if ptype == "upnp":
            return dp.make_upnp_page(parent, root)
        if ptype == "ping":
            return dp.make_ping_page(parent, root)
        if ptype == "traceroute":
            return dp.make_traceroute_page(parent, root)
        if ptype == "portscan":
            return dp.make_portscan_page(parent, root)
        if ptype == "hostdiscover":
            return dp.make_hostdiscover_page(parent, root)
        if ptype == "camera":
            return dp.make_camera_page(parent, root)
        if ptype == "session":
            return dp.make_session_page(parent, root)
        if ptype == "speed":
            return dp.make_speed_page(parent, root)
        if ptype == "iperf":
            return dp.make_iperf_page(parent, root)
        if ptype == "dhcp":
            return dp.make_dhcp_page(parent, root)
        if ptype == "ipconflict":
            return dp.make_ipconflict_page(parent, root)
        if ptype == "capture":
            return dp.make_netstat_page(parent, root)
        if ptype == "health":
            return dp.make_health_page(parent, root)
        if ptype == "security":
            return dp.make_security_page(parent, root)
        if ptype == "diag":
            return dp.make_diag_page(parent, root)
        if ptype == "analysis":
            return dp.make_analysis_page(parent, root)
        # 兜底
        return dp.make_ping_page(parent, root)
