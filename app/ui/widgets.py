# -*- coding: utf-8 -*-
"""
自定义 UI 控件模块：环形仪表盘、流量曲线图、统计卡片、日志面板。

全部基于 tk.Canvas / tk.Frame 手绘，统一深色主题，无第三方 UI 依赖。
"""
import tkinter as tk

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import theme


def _fmt_rate(bps):
    """把 bytes/s 格式化为可读速率（KB/s 或 MB/s）。"""
    if bps >= 1024 * 1024:
        return f"{bps / (1024 * 1024):.2f} MB/s"
    return f"{bps / 1024:.1f} KB/s"


class RingGauge(tk.Canvas):
    """环形仪表盘：显示百分比进度环 + 中心数值。"""

    def __init__(self, parent, title, color, size=170, width=16,
                 unit="%"):
        super().__init__(parent, width=size, height=size,
                         bg=theme.BG_CARD, highlightthickness=0)
        self.title = title
        self.color = color
        self.size = size
        self.width = width
        self.unit = unit
        self._value = 0.0
        self._sub = ""
        self._draw()

    def set(self, value, sub=""):
        """更新仪表盘：value 为 0-100，sub 为下方补充说明文字。"""
        self._value = max(0.0, min(100.0, value))
        self._sub = sub
        self._draw()

    def _draw(self):
        self.delete("all")
        pad = self.width + 4
        box = (pad, pad, self.size - pad, self.size - pad)
        # 背景环
        self.create_arc(box, start=90, extent=-359.9, style="arc",
                        outline=theme.BG_HOVER, width=self.width)
        # 进度环（从顶部顺时针）
        extent = -359.9 * (self._value / 100.0)
        if extent < -0.5:
            self.create_arc(box, start=90, extent=extent, style="arc",
                            outline=self.color, width=self.width)
        # 中心百分比
        cx = self.size / 2
        self.create_text(cx, cx - 10, text=f"{self._value:.0f}{self.unit}",
                         fill=theme.TEXT, font=theme.font(22, bold=True))
        # 标题
        self.create_text(cx, cx + 22, text=self.title,
                         fill=theme.TEXT_DIM, font=theme.font(10))
        # 补充文字
        if self._sub:
            self.create_text(cx, cx + 40, text=self._sub,
                             fill=theme.TEXT_FAINT, font=theme.font(8))


class TrafficChart(tk.Canvas):
    """实时上下行流量曲线图。"""

    def __init__(self, parent, height=150, max_points=60):
        super().__init__(parent, height=height, bg=theme.BG_CARD,
                         highlightthickness=0)
        self.height = height
        self.max_points = max_points
        self._down = []   # 下行历史 bytes/s
        self._up = []     # 上行历史 bytes/s
        self._max = 1.0   # 用于归一化
        self._draw()

    def push(self, down, up):
        """压入一组速率采样并重绘。"""
        self._down.append(down)
        self._up.append(up)
        if len(self._down) > self.max_points:
            self._down.pop(0)
            self._up.pop(0)
        peak = max(max(self._down), max(self._up), 1.0)
        self._max = peak * 1.15
        self._draw()

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.height
        if w < 50:
            return
        # 网格线
        for i in range(1, 4):
            y = h * i / 4
            self.create_line(0, y, w, y, fill=theme.BORDER_SOFT)
        # 折线
        n = len(self._down)
        if n < 2:
            self.create_text(w / 2, h / 2, text="采集数据中…",
                             fill=theme.TEXT_FAINT, font=theme.font(10))
            return
        step = w / (self.max_points - 1)
        def poly(data, color):
            pts = []
            for i, v in enumerate(data):
                x = w - (n - 1 - i) * step
                y = h - (v / self._max) * (h - 10) - 5
                pts.append((x, y))
            return pts
        self._line(poly(self._down, theme.DOWN_COLOR), theme.DOWN_COLOR)
        self._line(poly(self._up, theme.UP_COLOR), theme.UP_COLOR)
        # 图例
        cur_down = self._down[-1]
        cur_up = self._up[-1]
        self.create_text(10, 12, anchor="w", fill=theme.DOWN_COLOR,
                         text=f"↓ {_fmt_rate(cur_down)}", font=theme.font(9, bold=True))
        self.create_text(10, 28, anchor="w", fill=theme.UP_COLOR,
                         text=f"↑ {_fmt_rate(cur_up)}", font=theme.font(9, bold=True))

    def _line(self, pts, color):
        """画一条平滑折线（多点连线段）。"""
        for i in range(len(pts) - 1):
            self.create_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
                             fill=color, width=2)


class StatCard(tk.Frame):
    """信息卡片：标题 + 大数值 + 状态色小字。"""

    def __init__(self, parent, title, value="--", color=theme.TEXT,
                 sub="", sub_color=None):
        super().__init__(parent, bg=theme.BG_CARD, highlightbackground=theme.BORDER,
                         highlightthickness=1, bd=0)
        self._pad()
        tk.Label(self, text=title, bg=theme.BG_CARD, fg=theme.TEXT_DIM,
                 font=theme.font(10)).pack(anchor="w")
        self.val_lbl = tk.Label(self, text=value, bg=theme.BG_CARD, fg=color,
                                font=theme.font(20, bold=True))
        self.val_lbl.pack(anchor="w", pady=(4, 0))
        self.sub_lbl = tk.Label(self, text=sub, bg=theme.BG_CARD,
                                fg=sub_color or theme.TEXT_FAINT,
                                font=theme.font(9))
        self.sub_lbl.pack(anchor="w")

    def _pad(self):
        # 内边距
        self.grid_columnconfigure(0, weight=1)

    def set(self, value, color=None, sub=None, sub_color=None):
        self.val_lbl.config(text=value, fg=color or self.val_lbl.cget("fg"))
        # 长文本（IPv6 地址等）自动缩小字号，避免被卡片截断
        n = len(str(value))
        if n > 32:
            self.val_lbl.config(font=theme.font(9, bold=True))
        elif n > 20:
            self.val_lbl.config(font=theme.font(11, bold=True))
        else:
            self.val_lbl.config(font=theme.font(20, bold=True))
        if sub is not None:
            self.sub_lbl.config(text=sub, fg=sub_color or theme.TEXT_FAINT)


class LogPanel(tk.Frame):
    """
    日志面板：实时滚动输出 + 分级着色 + 保存 txt。
    通过 append(level, msg) 供全局 logger 回调驱动。
    """

    def __init__(self, parent, height=12, on_save=None):
        super().__init__(parent, bg=theme.BG_CARD)
        # 标题栏
        bar = tk.Frame(self, bg=theme.BG_CARD)
        bar.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(bar, text="检测日志", bg=theme.BG_CARD, fg=theme.TEXT,
                 font=theme.font(11, bold=True)).pack(side="left")
        self.save_btn = tk.Button(
            bar, text="保存日志", command=self._save,
            bg=theme.BG_HOVER, fg=theme.TEXT, relief="flat", bd=0,
            activebackground=theme.BORDER, activeforeground=theme.TEXT,
            font=theme.font(9), padx=10, pady=2, cursor="hand2")
        self.save_btn.pack(side="right")

        # 日志文本框
        self.text = tk.Text(self, height=height, bg=theme.BG,
                            fg=theme.TEXT, relief="flat", bd=0,
                            font=theme.font(9, mono=True),
                            insertbackground=theme.TEXT,
                            wrap="none", state="disabled", padx=8, pady=6)
        scroll = tk.Scrollbar(self, command=self.text.yview, bg=theme.BG_HOVER)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)

        # 级别 -> 颜色
        self._color_map = {
            "info": theme.TEXT,
            "ok": theme.GREEN,
            "warn": theme.ORANGE,
            "err": theme.RED,
        }
        self._tag_setup()
        self.on_save = on_save

    def _tag_setup(self):
        for lvl, color in self._color_map.items():
            self.text.tag_configure(lvl, foreground=color)

    def append(self, level, msg):
        """追加一行日志（供 logger 回调）。"""
        self.text.configure(state="normal")
        import time
        ts = time.strftime("%H:%M:%S")
        self.text.insert("end", f"[{ts}] {msg}\n", level)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def _save(self):
        """保存日志到本地 txt。"""
        from tkinter import filedialog
        from app.core.logger import log
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("文本文件", "*.txt")],
            initialfile="netops-log.txt")
        if not path:
            return
        saved = log.save(path)
        if saved:
            self.append("ok", f"日志已保存到 {saved}")
            if self.on_save:
                self.on_save(saved)
        else:
            self.append("warn", "暂无日志可保存")
