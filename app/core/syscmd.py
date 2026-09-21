# -*- coding: utf-8 -*-
"""
Windows 系统命令调用辅助模块。

统一解决两个问题：
1. 子进程控制台窗口闪现 —— 加 CREATE_NO_WINDOW 标志隐藏；
2. 中文乱码 —— 自动检测输出编码（UTF-8 / GBK / GB18030），
   不再固定按 GBK 解码（系统开启 UTF-8 代码页时命令会输出 UTF-8）。
"""
import subprocess

# Windows 专用：隐藏子进程控制台窗口；其他平台回退为 0
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def decode(data):
    """
    自动检测 Windows 命令输出编码并解码为 str。
    依次尝试 UTF-8 / GBK / GB18030，兜底用 UTF-8 + replace。
    """
    if not data:
        return ""
    if isinstance(data, str):
        return data
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def run_capture(cmd, timeout=10):
    """运行命令并返回解码后的 stdout 文本（不弹窗）。失败返回空串。"""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        return decode(proc.stdout)
    except Exception:
        return ""


def run(cmd, timeout=10):
    """运行命令并返回 (returncode, stdout_text)。"""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        return proc.returncode, decode(proc.stdout)
    except Exception:
        return -1, ""


def run_stream(cmd, line_cb, timeout=None):
    """
    流式运行命令：每读到一行就回调 line_cb(line)。
    用于 tracert 等逐跳输出的命令，实现实时滚动显示。
    返回 returncode（或 -1）。
    """
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        return -1
    try:
        for raw in iter(proc.stdout.readline, b""):
            line = decode(raw).rstrip("\r\n")
            if line_cb:
                try:
                    line_cb(line)
                except Exception:
                    pass
        proc.stdout.close()
        return proc.wait()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        return -1
