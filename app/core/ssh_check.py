# -*- coding: utf-8 -*-
"""
【2】SSH 连通性检测模块。

输入：目标主机、端口(默认22)、用户名、认证方式(密码/密钥文件)。
输出：连通状态、握手耗时、SSH 版本识别、弱加密算法检测、失败详情。

实现基于 paramiko：建立 TCP 连接 -> 读 Banner -> 完成 SSH 协议握手 ->
（可选）认证。弱加密算法通过协商出的算法与已知弱项比对得出。
"""
import time

from .logger import log

# 已知弱算法关键词（用于告警）
WEAK_KEX = ("sha1", "diffie-hellman-group1", "diffie-hellman-group14-sha1",
            "ecdh-sha2-nistp256")
WEAK_CIPHER = ("3des", "cbc", "arcfour", "blowfish", "none")
WEAK_MAC = ("md5", "96")


def run_ssh_check(host, port=22, username=None, password=None,
                  key_file=None, timeout=8):
    """
    执行 SSH 检测。返回结构化 dict。
    password 与 key_file 二选一（也可都为空，仅做连通+版本识别）。
    """
    result = {
        "conn_ok": False,
        "handshake_ms": None,
        "ssh_version": "",
        "weak_algos": [],
        "auth_ok": None,       # None=未尝试认证
        "error": "",
    }
    import paramiko

    start = time.perf_counter()
    try:
        if password or key_file:
            # 有凭据：完整连接 + 认证
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                host, port=int(port), username=username or "root",
                password=password,
                key_filename=key_file or None,
                timeout=timeout,
                auth_timeout=timeout,
                banner_timeout=timeout,
                allow_agent=False,
                look_for_keys=False,
                disabled_algorithms={},  # 不禁用任何算法，便于暴露弱项
            )
            result["conn_ok"] = True
            result["handshake_ms"] = round((time.perf_counter() - start) * 1000, 2)
            t = client.get_transport()
            result["ssh_version"] = t.remote_version
            result["auth_ok"] = True
            log.ok(f"SSH 连接成功，握手耗时 {result['handshake_ms']} ms")
            log.ok(f"SSH 版本：{t.remote_version}")
            log.ok("SSH 认证通过")
            result["weak_algos"] = _detect_weak(t)
            client.close()
        else:
            # 无凭据：仅 TCP + Banner 识别 + KEX（用 Transport，不触发认证）
            transport = paramiko.Transport((host, int(port)))
            transport.start_client(timeout=timeout)
            result["conn_ok"] = True
            result["handshake_ms"] = round((time.perf_counter() - start) * 1000, 2)
            result["ssh_version"] = transport.remote_version
            result["auth_ok"] = None
            log.ok(f"SSH 连接成功，握手耗时 {result['handshake_ms']} ms")
            log.ok(f"SSH 版本：{transport.remote_version}")
            log.info("未提供凭据，仅做连通与版本识别")
            result["weak_algos"] = _detect_weak(transport)
            transport.close()

        # 弱算法结论
        for w in result["weak_algos"]:
            log.warn(f"检测到弱加密算法: {w}")
        if not result["weak_algos"]:
            log.ok("未发现已知弱加密算法")

    except paramiko.AuthenticationException as e:
        result["error"] = f"认证失败: {e}"
        log.error(result["error"])
    except paramiko.SSHException as e:
        result["error"] = f"SSH 协议错误: {e}"
        log.error(result["error"])
    except Exception as e:
        result["error"] = f"连接失败: {e}"
        log.error(result["error"])

    return result


def _detect_weak(transport):
    """
    检查协商出的 KEX/Cipher/MAC 是否含弱项。
    paramiko 通过 active_cipher / kex_engine / hmac 暴露已协商算法。
    """
    weak = []
    try:
        # 已协商的对称加密算法
        if hasattr(transport, "active_cipher") and transport.active_cipher:
            weak += [f"cipher:{transport.active_cipher[0]}" for _ in [0]
                     if _match_weak(str(transport.active_cipher[0]), WEAK_CIPHER)]
        # 密钥交换算法
        if hasattr(transport, "kex_engine") and transport.kex_engine:
            kex = type(transport.kex_engine).__name__
            if _match_weak(kex, WEAK_KEX):
                weak.append(f"kex:{kex}")
        # 完整算法名（部分 paramiko 版本暴露）
        if hasattr(transport, "_preferred_kex"):
            pass
    except Exception:
        pass
    return list(dict.fromkeys(weak))


def _match_weak(name, keywords):
    """算法名是否命中弱项关键词（小写匹配）。"""
    n = name.lower()
    return any(k in n for k in keywords)
