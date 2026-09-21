# -*- coding: utf-8 -*-
"""
检测页面模块：通用检测页面框架 + 各检测功能页面。

每个页面 = 表单输入区 + 执行按钮 + 实时日志面板。
点击执行后启动后台线程跑 run_fn，通过全局 logger 实时回传日志，不阻塞 UI。
"""
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import theme
from app.ui.widgets import LogPanel
from app.core.logger import log
from app.core import syscmd


class Field:
    """表单字段定义。kind: entry|password|combo|file。"""

    def __init__(self, label, key, default="", kind="entry",
                 options=None, width=32):
        self.label = label
        self.key = key
        self.default = default
        self.kind = kind
        self.options = options or []
        self.width = width


class DetectorPage(tk.Frame):
    """通用检测页面：标题 + 表单 + 执行 + 日志。"""

    def __init__(self, parent, root, title, fields, run_fn, desc=""):
        super().__init__(parent, bg=theme.BG)
        self.root = root
        self.title = title
        self.fields = fields
        self.run_fn = run_fn
        self.desc = desc
        self.active = False
        self._vars = {}          # key -> tk variable
        self._running = False
        self._build()
        log.add_listener(self._log_cb)

    # ---------- 构建 ----------
    def _build(self):
        # 标题 + 描述
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=16, pady=(16, 4))
        tk.Label(head, text=self.title, bg=theme.BG, fg=theme.TEXT,
                 font=theme.font(15, bold=True)).pack(anchor="w")
        if self.desc:
            tk.Label(head, text=self.desc, bg=theme.BG, fg=theme.TEXT_DIM,
                     font=theme.font(9), wraplength=900, justify="left").pack(anchor="w", pady=(2, 0))

        # 表单卡片
        form = tk.Frame(self, bg=theme.BG_CARD, highlightbackground=theme.BORDER,
                        highlightthickness=1)
        form.pack(fill="x", padx=16, pady=8)
        self._form = form
        for i, f in enumerate(self.fields):
            self._build_field(form, f, i)

        # 执行按钮行
        bar = tk.Frame(self, bg=theme.BG)
        bar.pack(fill="x", padx=16, pady=(0, 4))
        self.run_btn = tk.Button(
            bar, text="▶ 开始检测", command=self._start,
            bg=theme.GREEN_DIM, fg="#ffffff", relief="flat", bd=0,
            activebackground=theme.GREEN, activeforeground="#ffffff",
            font=theme.font(11, bold=True), padx=18, pady=6, cursor="hand2")
        self.run_btn.pack(side="left")
        self.status_lbl = tk.Label(bar, text="", bg=theme.BG, fg=theme.TEXT_DIM,
                                   font=theme.font(9))
        self.status_lbl.pack(side="left", padx=12)

        # 日志面板
        self.log_panel = LogPanel(self, height=14)
        self.log_panel.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def _build_field(self, form, f, row):
        """构建单个表单字段。"""
        lbl = tk.Label(form, text=f.label, bg=theme.BG_CARD, fg=theme.TEXT_DIM,
                       font=theme.font(10), anchor="e", width=14)
        lbl.grid(row=row, column=0, sticky="e", padx=(14, 8), pady=5)

        if f.kind == "combo":
            var = tk.StringVar(value=f.default)
            cb = ttk.Combobox(form, textvariable=var, values=f.options,
                              state="readonly", width=f.width)
            cb.grid(row=row, column=1, sticky="w", pady=5)
            self._vars[f.key] = var
        elif f.kind == "password":
            var = tk.StringVar(value=f.default)
            e = tk.Entry(form, textvariable=var, show="•", width=f.width,
                         bg=theme.BG_INPUT, fg=theme.TEXT, relief="flat",
                         insertbackground=theme.TEXT, font=theme.font(10))
            e.grid(row=row, column=1, sticky="w", pady=5)
            self._vars[f.key] = var
        elif f.kind == "file":
            var = tk.StringVar(value=f.default)
            e = tk.Entry(form, textvariable=var, width=f.width - 10,
                         bg=theme.BG_INPUT, fg=theme.TEXT, relief="flat",
                         insertbackground=theme.TEXT, font=theme.font(10))
            e.grid(row=row, column=1, sticky="w", pady=5)
            b = tk.Button(form, text="浏览…", command=lambda v=var: self._pick_file(v),
                          bg=theme.BG_HOVER, fg=theme.TEXT, relief="flat",
                          activebackground=theme.BORDER, font=theme.font(9), cursor="hand2")
            b.grid(row=row, column=2, sticky="w", padx=6, pady=5)
            self._vars[f.key] = var
        else:  # entry
            var = tk.StringVar(value=f.default)
            e = tk.Entry(form, textvariable=var, width=f.width,
                         bg=theme.BG_INPUT, fg=theme.TEXT, relief="flat",
                         insertbackground=theme.TEXT, font=theme.font(10))
            e.grid(row=row, column=1, sticky="w", pady=5)
            self._vars[f.key] = var

    def _pick_file(self, var):
        path = filedialog.askopenfilename()
        if path:
            var.set(path)

    # ---------- 日志回调 ----------
    def _log_cb(self, level, msg):
        """logger 回调（后台线程触发），切回主线程更新。"""
        if self.active:
            try:
                self.root.after(0, self.log_panel.append, level, msg)
            except Exception:
                pass

    # ---------- 执行 ----------
    def on_show(self):
        self.active = True

    def on_hide(self):
        self.active = False

    def _collect(self):
        """收集表单值为 dict。"""
        vals = {}
        for f in self.fields:
            var = self._vars.get(f.key)
            vals[f.key] = var.get().strip() if var else f.default
        return vals

    def _start(self):
        if self._running:
            return
        vals = self._collect()
        self.log_panel.clear()
        log.info(f"===== {self.title} 开始 =====")
        for f in self.fields:
            if f.kind != "password":
                log.info(f"参数 {f.label}: {vals.get(f.key) or '(空)'}")
        self._set_running(True)
        threading.Thread(target=self._run, args=(vals,), daemon=True).start()

    def _run(self, vals):
        try:
            result = self.run_fn(vals)
            if isinstance(result, dict):
                self.root.after(0, self._show_result, result)
        except Exception as e:
            log.error(f"检测执行异常: {e}")
        finally:
            log.info(f"===== {self.title} 结束 =====")
            self.root.after(0, self._set_running, False)

    def _set_running(self, running):
        self._running = running
        if running:
            self.run_btn.config(state="disabled", text="检测中…", bg=theme.BG_HOVER)
            self.status_lbl.config(text="运行中…", fg=theme.ORANGE)
        else:
            self.run_btn.config(state="normal", text="▶ 开始检测", bg=theme.GREEN_DIM)
            self.status_lbl.config(text="完成", fg=theme.GREEN)

    def _show_result(self, result):
        """结构化展示返回结果（JSON）。"""
        try:
            text = json.dumps(result, ensure_ascii=False, indent=2)
            log.info("结构化结果：\n" + text)
        except Exception:
            pass


# =====================================================================
# 各检测页面构造器
# =====================================================================

def make_tcp_page(parent, root):
    from app.core import tcp_handshake
    fields = [
        Field("目标IP/域名", "host", "", "entry"),
        Field("TCP端口", "port", "443", "entry"),
        Field("应用协议", "protocol", "裸TCP", "combo",
              options=["裸TCP", "HTTP", "SSH", "TLS"]),
    ]
    def run(vals):
        try:
            port = int(vals["port"])
        except ValueError:
            log.error("端口必须是数字")
            return {"error": "端口必须是数字"}
        if not vals["host"]:
            log.error("请输入目标 IP/域名")
            return {"error": "目标为空"}
        return tcp_handshake.run_tcp_app_check(
            vals["host"], port, vals["protocol"])
    return DetectorPage(parent, root, "TCP 应用层握手检测", fields, run,
                        desc="执行 TCP 三次握手并记录 RTT，再按所选协议完成应用层握手（裸TCP/HTTP/SSH/TLS）。")


def make_ssh_page(parent, root):
    from app.core import ssh_check
    fields = [
        Field("目标主机", "host", "", "entry"),
        Field("SSH端口", "port", "22", "entry"),
        Field("用户名", "username", "root", "entry"),
        Field("认证方式", "auth_type", "密码", "combo", options=["密码", "密钥文件", "无(仅连通)"]),
        Field("密码", "password", "", "password"),
        Field("密钥文件", "key_file", "", "file"),
    ]
    def run(vals):
        if not vals["host"]:
            log.error("请输入目标主机")
            return {"error": "目标为空"}
        try:
            port = int(vals["port"])
        except ValueError:
            port = 22
        auth = vals["auth_type"]
        password = vals["password"] if auth == "密码" else None
        key_file = vals["key_file"] if auth == "密钥文件" else None
        return ssh_check.run_ssh_check(
            vals["host"], port, vals["username"], password, key_file)
    return DetectorPage(parent, root, "SSH 连通性检测", fields, run,
                        desc="建立 SSH 连接，完成协议握手，输出版本识别、弱加密算法检测与认证结果。")


def make_https_page(parent, root):
    from app.core import https_check
    fields = [
        Field("目标域名/IP", "host", "", "entry"),
        Field("端口", "port", "443", "entry"),
    ]
    def run(vals):
        if not vals["host"]:
            log.error("请输入目标域名/IP")
            return {"error": "目标为空"}
        try:
            port = int(vals["port"])
        except ValueError:
            port = 443
        return https_check.run_https_check(vals["host"], port)
    return DetectorPage(parent, root, "HTTPS 检测", fields, run,
                        desc="检测 TLS 版本、加密套件、证书信息（签发机构/有效期/SAN/本地信任）、握手耗时、证书链完整性与降级风险。")


def make_doh_page(parent, root):
    from app.core import doh_check
    fields = [
        Field("DoH服务地址", "doh_url", "", "entry"),
        Field("待解析域名", "domain", "www.baidu.com", "entry"),
    ]
    def run(vals):
        if not vals["domain"]:
            log.error("请输入待解析域名")
            return {"error": "域名为空"}
        return doh_check.run_doh_check(vals["domain"], vals["doh_url"])
    return DetectorPage(parent, root, "DoH 加密 DNS 检测", fields, run,
                        desc="默认 https://dns.alidns.com/dns-query，可自定义 DoH 服务。检测连通性、证书校验、解析结果与耗时。")


def make_dot_page(parent, root):
    from app.core import dot_check
    fields = [
        Field("DoT服务器", "server", "", "entry"),
        Field("端口", "port", "853", "entry"),
        Field("待解析域名", "domain", "www.baidu.com", "entry"),
    ]
    def run(vals):
        if not vals["domain"]:
            log.error("请输入待解析域名")
            return {"error": "域名为空"}
        try:
            port = int(vals["port"])
        except ValueError:
            port = 853
        return dot_check.run_dot_check(vals["domain"], vals["server"], port)
    return DetectorPage(parent, root, "DoT 加密 DNS 检测", fields, run,
                        desc="默认 tls://dns.alidns.com:853，可自定义 DoT 服务器。检测 853 端口连通、TLS 握手、解析结果与耗时。")


def make_ping_page(parent, root):
    from app.core import net_health
    fields = [
        Field("目标IP/域名", "host", "", "entry"),
        Field("次数", "count", "4", "entry"),
    ]
    def run(vals):
        if not vals["host"]:
            log.error("请输入目标")
            return {"error": "目标为空"}
        try:
            count = int(vals["count"])
        except ValueError:
            count = 4
        for i in range(count):
            ok, ms, err = net_health.ping(vals["host"], 3)
            if ok:
                log.ok(f"第 {i + 1} 次: {ms} ms")
            else:
                log.error(f"第 {i + 1} 次: {err}")
        return {"done": True}
    return DetectorPage(parent, root, "Ping 测试", fields, run,
                        desc="调用 Windows 原生 ping 检测目标可达性与延迟。")


def make_traceroute_page(parent, root):
    from app.core import advanced
    fields = [Field("目标IP/域名", "host", "", "entry")]
    def run(vals):
        if not vals["host"]:
            log.error("请输入目标")
            return {"error": "目标为空"}
        advanced.traceroute(vals["host"])
        return {"done": True}
    return DetectorPage(parent, root, "路由追踪", fields, run,
                        desc="调用 Windows tracert 逐跳追踪到目标的路径。")


def make_portscan_page(parent, root):
    from app.core import advanced
    fields = [
        Field("目标IP/域名", "host", "", "entry"),
        Field("端口(逗号分隔)", "ports", "", "entry"),
    ]
    def run(vals):
        if not vals["host"]:
            log.error("请输入目标")
            return {"error": "目标为空"}
        ports = None
        if vals["ports"]:
            try:
                ports = [int(p) for p in vals["ports"].replace("，", ",").split(",") if p.strip()]
            except ValueError:
                log.error("端口格式错误")
                return {"error": "端口格式错误"}
        advanced.port_scan(vals["host"], ports)
        return {"done": True}
    return DetectorPage(parent, root, "端口扫描", fields, run,
                        desc="多线程 TCP 连接扫描目标端口（默认扫描常用端口）。")


def make_hostdiscover_page(parent, root):
    from app.core import advanced
    fields = [Field("网段(如192.168.1.0/24)", "subnet", "", "entry")]
    def run(vals):
        if not vals["subnet"]:
            log.error("请输入网段")
            return {"error": "网段为空"}
        advanced.host_discover(vals["subnet"])
        return {"done": True}
    return DetectorPage(parent, root, "主机发现", fields, run,
                        desc="Ping 扫描指定网段，发现存活主机。")


def make_camera_page(parent, root):
    from app.core import advanced
    fields = [Field("目标IP(逗号分隔)", "hosts", "", "entry")]
    def run(vals):
        if not vals["hosts"]:
            log.error("请输入目标 IP")
            return {"error": "目标为空"}
        hosts = [h.strip() for h in vals["hosts"].replace("，", ",").split(",") if h.strip()]
        advanced.camera_scan(hosts)
        return {"done": True}
    return DetectorPage(parent, root, "摄像头扫描", fields, run,
                        desc="探测目标 RTSP/HTTP 常见端口，识别可能的摄像头设备。")


def make_session_page(parent, root):
    from app.core import advanced
    fields = [
        Field("目标IP/域名", "host", "", "entry"),
        Field("端口", "port", "443", "entry"),
        Field("次数", "count", "5", "entry"),
    ]
    def run(vals):
        if not vals["host"]:
            log.error("请输入目标")
            return {"error": "目标为空"}
        try:
            port = int(vals["port"]); count = int(vals["count"])
        except ValueError:
            log.error("端口/次数必须是数字")
            return {"error": "参数错误"}
        advanced.session_test(vals["host"], port, count)
        return {"done": True}
    return DetectorPage(parent, root, "会话测试", fields, run,
                        desc="反复建立 TCP 连接，统计成功率与延迟。")


def make_speed_page(parent, root):
    from app.core import advanced
    fields = []
    def run(vals):
        advanced.speed_test()
        return {"done": True}
    return DetectorPage(parent, root, "速度测试", fields, run,
                        desc="下载测试文件估算带宽速率。")


def make_dhcp_page(parent, root):
    from app.core import advanced
    fields = []
    def run(vals):
        advanced.dhcp_check()
        return {"done": True}
    return DetectorPage(parent, root, "DHCP 检测", fields, run,
                        desc="解析本机 DHCP 配置（服务器/租约）。")


def make_ipconflict_page(parent, root):
    from app.core import advanced
    fields = []
    def run(vals):
        advanced.ip_conflict_check()
        return {"done": True}
    return DetectorPage(parent, root, "IP 冲突检测", fields, run,
                        desc="基于 ARP 表检测重复 IP。")


def make_netstat_page(parent, root):
    """数据抓包（简化）：展示当前网络连接（netstat）。"""
    fields = []
    def run(vals):
        log.info("抓取当前网络连接…")
        try:
            out = syscmd.run_capture(["netstat", "-ano"], timeout=10)
            for line in out.splitlines()[:200]:
                log.info(line)
        except Exception as e:
            log.error(f"抓取失败: {e}")
        return {"done": True}
    return DetectorPage(parent, root, "数据抓包", fields, run,
                        desc="展示当前网络连接（netstat，需管理员权限查看完整 PID）。")


def make_health_page(parent, root):
    """网络健康：综合检测本机网络状态。"""
    fields = []
    def run(vals):
        from app.core import net_health, system_info as si
        log.info(f"本机 IP: {si.get_local_ip()}")
        log.info(f"网关: {si.get_gateway()}")
        log.info(f"DNS: {si.get_dns_servers()}")
        ok, detail = net_health.check_internet()
        for name, is_ok, rtt, err in detail:
            if is_ok:
                log.ok(f"{name} 连通，RTT {rtt:.1f} ms")
            else:
                log.error(f"{name} 不可达: {err}")
        log.ok("网络健康检测完成" if ok else "外网不可达，请检查网络")
        return {"done": True}
    return DetectorPage(parent, root, "网络健康", fields, run,
                        desc="综合检测本机 IP/网关/DNS 与外网连通性。")


def make_security_page(parent, root):
    """安全自测：基础安全检查。"""
    fields = []
    def run(vals):
        log.info("检查 Windows 防火墙状态…")
        try:
            out = syscmd.run_capture(
                ["netsh", "advfirewall", "show", "allprofiles", "state"],
                timeout=10)
            for line in out.splitlines():
                if line.strip():
                    log.info(line.strip())
        except Exception as e:
            log.error(f"检查失败: {e}")
        log.ok("安全自测完成")
        return {"done": True}
    return DetectorPage(parent, root, "安全自测", fields, run,
                        desc="检查防火墙等基础安全状态（需管理员权限）。")


def make_diag_page(parent, root):
    """诊断检测：一键综合诊断。"""
    fields = []
    def run(vals):
        from app.core import net_health
        log.info("开始综合诊断…")
        ok, detail = net_health.check_internet()
        for name, is_ok, rtt, err in detail:
            if is_ok:
                log.ok(f"{name} 连通，RTT {rtt:.1f} ms")
            else:
                log.error(f"{name} 不可达: {err}")
        log.info("诊断完成")
        return {"done": True}
    return DetectorPage(parent, root, "诊断检测", fields, run,
                        desc="一键综合诊断外网连通性。")


def make_analysis_page(parent, root):
    """网络分析：综合分析网络配置。"""
    fields = []
    def run(vals):
        from app.core import system_info as si
        log.info(f"主机名: {si.get_hostname()}")
        log.info(f"所有 IPv4: {si.get_all_ips()}")
        log.info(f"网关: {si.get_gateway()}")
        log.info(f"DNS: {si.get_dns_servers()}")
        try:
            out = syscmd.run_capture(["ipconfig", "/all"], timeout=10)
            log.info("网络接口配置：\n" + out[:2000])
        except Exception as e:
            log.error(f"读取配置失败: {e}")
        return {"done": True}
    return DetectorPage(parent, root, "网络分析", fields, run,
                        desc="综合分析本机网络配置与接口信息。")


def make_iperf_page(parent, root):
    """内网测速：iperf 客户端主动连接服务端测速。"""
    from app.core import iperf_test
    fields = [
        Field("iperf服务端IP", "server", "", "entry"),
        Field("端口", "port", "5201", "entry"),
        Field("时长(秒)", "duration", "10", "entry"),
        Field("方向", "direction", "下载", "combo", options=["下载", "上传"]),
        Field("协议", "proto", "TCP", "combo", options=["TCP", "UDP"]),
    ]

    def run(vals):
        if not vals["server"]:
            log.error("请输入 iperf 服务端 IP")
            return {"error": "服务端为空"}
        try:
            port = int(vals["port"])
            duration = int(vals["duration"])
        except ValueError:
            log.error("端口/时长必须是数字")
            return {"error": "参数错误"}
        reverse = vals["direction"] == "下载"
        udp = vals["proto"] == "UDP"

        cmd_name, _ = iperf_test.find_iperf()
        if cmd_name:
            return iperf_test.run_iperf_test(vals["server"], port, duration, reverse, udp)
        else:
            log.warn("未检测到 iperf3，改用内置 TCP 吞吐量测试（服务端可为任意 TCP 服务）")
            if udp:
                log.warn("内置兜底仅支持 TCP，已按 TCP 测试")
            return iperf_test.run_tcp_throughput(vals["server"], port, duration, reverse)

    return DetectorPage(parent, root, "内网测速 (iperf)", fields, run,
                        desc="主动连接内网 iperf 服务端测速（服务端启动：iperf3 -s -p 5201）。未装 iperf3 时自动用内置 TCP 测速兜底。")
