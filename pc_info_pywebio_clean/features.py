"""Диагностика, инструменты сети, управление выбранным процессом, тест CPU."""
import hashlib
import os
import re
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

import psutil

from logger_setup import logger
from pc_stats import battery_info, disks_info, fmt_bytes


def diagnose(stats):
    messages = []
    if stats["cpu"] >= 90:
        messages.append(("danger", "CPU загружен на 90% или выше. Проверьте тяжёлые процессы."))
    elif stats["cpu"] >= 75:
        messages.append(("warning", "Повышенная загрузка процессора."))
    if stats["ram"] >= 90:
        messages.append(("danger", "Мало свободной оперативной памяти."))
    elif stats["ram"] >= 80:
        messages.append(("warning", "Оперативная память загружена более чем на 80%."))
    critical_disks = [d for d in disks_info() if d["percent"] >= 90]
    for d in critical_disks:
        messages.append(("danger", f"Диск {d['mountpoint']} почти заполнен: {d['percent']:.0f}%."))
    bat = battery_info()
    if bat is not None and not bat["plugged"] and bat["percent"] < 20:
        messages.append(("warning", f"Батарея: {bat['percent']}%. Подключите зарядку."))
    if stats["processes"] > 350:
        messages.append(("info", "Запущено много процессов. Это не обязательно ошибка."))
    if not messages:
        messages.append(("success", "Критических проблем по доступным показателям не обнаружено."))
    # Это простые правила, не медицинский «ИИ» и не аппаратная диагностика SMART.
    return messages


def check_network(host="example.com", port=443):
    """Диагностика DNS + TCP + ping без shell=True."""
    host = host.strip()
    if not re.fullmatch(r"[A-Za-z0-9.:-]{1,253}", host) or host.startswith("-"):
        raise ValueError("Недопустимое имя хоста")
    # Если передали URL, не выполняем произвольные внешние команды.
    if "/" in host or "@" in host:
        raise ValueError("Укажите домен без http:// и слэшей")
    result = {"host": host, "dns": [], "tcp_ms": None, "ping": ""}
    started = time.perf_counter()
    resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    result["dns_ms"] = round((time.perf_counter() - started) * 1000, 1)
    result["dns"] = sorted({a[4][0] for a in resolved})
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=4):
            result["tcp_ms"] = round((time.perf_counter() - started) * 1000, 1)
    except (OSError, TimeoutError) as exc:
        result["tcp_error"] = str(exc)
    args = ["ping", "-n" if sys.platform == "win32" else "-c", "2", host]
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=8, shell=False,
                           encoding="oem" if sys.platform == "win32" else "utf-8",
                           errors="replace")
        result["ping"] = (p.stdout or p.stderr)[-1600:]
    except (OSError, subprocess.TimeoutExpired):
        result["ping"] = "Системная команда ping недоступна или истекло время ожидания."
    logger.info("Диагностика сети: %s, TCP %s мс", host, result["tcp_ms"])
    return result


def close_process(pid):
    """Завершить только выбранный PID. Вызывается после явного подтверждения."""
    pid = int(pid)
    forbidden = {0, 1, 4, os.getpid(), os.getppid()}
    if pid in forbidden or pid < 1:
        raise PermissionError("Этот системный процесс завершать нельзя")
    proc = psutil.Process(pid)
    name = proc.name()
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except psutil.TimeoutExpired:
        logger.warning("Процесс %s (%s) не завершился в течение 3 секунд", pid, name)
        return f"Запрос завершения отправлен процессу {name} (PID {pid}), он ещё работает."
    logger.warning("Пользователь завершил процесс %s (PID %s)", name, pid)
    return f"Процесс {name} (PID {pid}) завершён."


def cpu_benchmark(rounds=60000):
    """Короткий ограниченный тест CPU. Значение служит для сравнения прогонов."""
    rounds = min(max(rounds, 1000), 100000)
    started = time.perf_counter()
    data = b"pc-info-benchmark"
    for _ in range(rounds):
        data = hashlib.sha256(data).digest()
    seconds = time.perf_counter() - started
    logger.info("CPU тест: %s циклов, %.3f с", rounds, seconds)
    return {"rounds": rounds, "seconds": seconds,
            "score": round(rounds / max(seconds, 0.000001)), "checksum": data.hex()[:16]}
