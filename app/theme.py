# -*- coding: utf-8 -*-
"""
主题模块：集中管理整个应用的颜色、字体等视觉常量。
深色科技运维面板风格 —— 参考 GitHub Dark / 运维大屏配色。
状态颜色规范：绿色=正常，橙色=警告，红色=故障。
"""

# ---------- 基础背景色 ----------
BG          = "#0d1117"   # 全局最深背景
BG_SIDE     = "#0b0e14"   # 左侧导航栏背景
BG_CARD     = "#161b22"   # 卡片背景
BG_CARD_HI  = "#1c2128"   # 卡片悬停/强调
BG_INPUT    = "#0d1117"   # 输入框背景
BG_HOVER    = "#21262d"   # 列表/菜单悬停

# ---------- 边框 / 分隔 ----------
BORDER      = "#30363d"   # 边框线
BORDER_SOFT = "#21262d"

# ---------- 文字 ----------
TEXT        = "#c9d1d9"   # 主文字
TEXT_DIM    = "#8b949e"   # 次要文字
TEXT_FAINT  = "#6e7681"   # 更弱文字
TEXT_ACCENT = "#58a6ff"   # 强调/链接蓝

# ---------- 状态色（绿/橙/红规范） ----------
GREEN       = "#3fb950"   # 正常
GREEN_DIM   = "#238636"
ORANGE      = "#f0883e"   # 警告
ORANGE_DIM  = "#d29922"
RED         = "#f85149"   # 故障
RED_DIM     = "#da3633"

# ---------- 仪表盘/图表配色 ----------
CPU_COLOR   = "#58a6ff"   # CPU 环形蓝
MEM_COLOR   = "#3fb950"   # 内存环形绿
DISK_COLOR  = "#f0883e"   # 磁盘环形橙
UP_COLOR    = "#3fb950"   # 上行流量曲线
DOWN_COLOR  = "#58a6ff"   # 下行流量曲线

# ---------- 字体 ----------
FONT_FAMILY = "Microsoft YaHei UI"   # 微软雅黑 UI，Windows 自带
FONT_MONO   = "Consolas"             # 等宽字体，用于日志/数值


def font(size=10, bold=False, mono=False):
    """快捷构造字体元组，避免到处重复写字体族名。"""
    fam = FONT_MONO if mono else FONT_FAMILY
    import tkinter.font as tkfont
    return (fam, size, "bold") if bold else (fam, size)
