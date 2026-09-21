# -*- coding: utf-8 -*-
"""
日志模块：统一的日志记录、分级、实时回调与本地 txt 保存。

设计要点：
- 所有检测线程通过 Logger.log() 输出，携带级别与颜色。
- UI 通过 add_listener() 注册回调，收到日志后刷新滚动文本框（主线程执行）。
- save() 将完整日志（含时间戳）写入本地 txt，用于审计留存。
"""
import os
import time
import threading

# 日志级别 -> (显示前缀, 状态色)
LEVEL_INFO = "INFO"
LEVEL_OK = "OK"
LEVEL_WARN = "WARN"
LEVEL_ERR = "ERROR"

_LEVEL_STYLE = {
    LEVEL_INFO: ("[信息]", "info"),
    LEVEL_OK:   ("[正常]", "ok"),
    LEVEL_WARN: ("[警告]", "warn"),
    LEVEL_ERR:  ("[故障]", "err"),
}


class Logger:
    """线程安全的日志记录器。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._listeners = []      # [(callback, )] 供 UI 实时刷新
        self._lines = []          # 完整日志行，供保存 txt 使用

    def add_listener(self, fn):
        """注册实时回调。fn(level, text) 由调用方负责切回主线程。"""
        with self._lock:
            self._listeners.append(fn)

    def _emit(self, level, msg):
        ts = time.strftime("%H:%M:%S")
        prefix, style = _LEVEL_STYLE.get(level, _LEVEL_STYLE[LEVEL_INFO])
        line = f"[{ts}] {prefix} {msg}"
        with self._lock:
            self._lines.append((level, msg, ts))
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(level, msg)
            except Exception:
                pass
        return line

    def info(self, msg):
        return self._emit(LEVEL_INFO, msg)

    def ok(self, msg):
        return self._emit(LEVEL_OK, msg)

    def warn(self, msg):
        return self._emit(LEVEL_WARN, msg)

    def error(self, msg):
        return self._emit(LEVEL_ERR, msg)

    def clear(self):
        with self._lock:
            self._lines.clear()

    def history(self):
        """返回完整历史日志 [(level, msg, ts), ...]，供日志审计页回放。"""
        with self._lock:
            return list(self._lines)

    def save(self, path):
        """将完整日志保存到本地 txt 文件。返回保存路径或 None。"""
        try:
            with self._lock:
                lines = list(self._lines)
            if not lines:
                return None
            with open(path, "w", encoding="utf-8") as f:
                f.write("=" * 60 + "\n")
                f.write(f"NetOps Panel 检测日志\n")
                f.write(f"导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                for level, msg, ts in lines:
                    prefix, _ = _LEVEL_STYLE.get(level, _LEVEL_STYLE[LEVEL_INFO])
                    f.write(f"[{ts}] {prefix} {msg}\n")
            return path
        except Exception as e:
            return None

    @property
    def count(self):
        with self._lock:
            return len(self._lines)


# 全局单例日志器，所有模块共用
log = Logger()
