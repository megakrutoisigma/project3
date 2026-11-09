"""Сбор системных данных. Базовые библиотеки: platform, sys, os, psutil."""
import ctypes
import getpass
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

from logger_setup import logger

# Первый вызов cpu_percent(None) готовит счётчики для следующих замеров.
psutil.cpu_percent(interval=None)


def fmt_bytes(n):
    if n is None:
        return "Нет данных"
    v = float(n)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if abs(v) < 1024 or unit == "ТБ":
            return f"{v:.1f} {unit}"
        v /= 1024


def quick_stats():
    """Быстрый снимок, выполняется в фоне каждые 5 секунд."""
    memory = psutil.virtual_memory()
    net = psutil.net_io_counters()
    disk = psutil.disk_usage(Path.home().anchor or os.sep)
    result = {
        "cpu": round(psutil.cpu_percent(interval=None), 1),
        "ram": round(memory.percent, 1),
        "disk": round(disk.percent, 1),
        "net_sent": int(net.bytes_sent) if net else 0,
        "net_recv": int(net.bytes_recv) if net else 0,
        "processes": len(psutil.pids()),
        "uptime_s": max(0, int(time.time() - psutil.boot_time())),
        "memory_used": memory.used,
        "memory_total": memory.total,
    }
    return result


def system_info():
    u = platform.uname()
    return {
        "Имя компьютера": u.node,
        "Операционная система": f"{u.system} {u.release}",
        "Версия ОС": u.version,
        "Архитектура": u.machine,
        "Процессор": u.processor or platform.processor() or "Нет данных",
        "Python": sys.version.split()[0],
        "Интерпретатор Python": sys.executable,
        "Разрядность Python": "64-bit" if sys.maxsize > 2**32 else "32-bit",
        "Текущий пользователь": getpass.getuser(),
        "Рабочая папка": os.getcwd(),
        "Дата запуска ОС": datetime.fromtimestamp(psutil.boot_time()).strftime("%d.%m.%Y %H:%M:%S"),
    }


def cpu_temperature():
    """Датчик CPU, если ОС и psutil умеют читать температуру."""
    if not hasattr(psutil, "sensors_temperatures"):
        return "Недоступно"
    try:
        sensors = psutil.sensors_temperatures() or {}
        for group, entries in sensors.items():
            for item in entries:
                label = (group + " " + (item.label or "")).lower()
                if any(key in label for key in ("coretemp", "k10temp", "cpu", "package", "tdie")):
                    if item.current is not None:
                        return f"{item.current:.1f} °C"
    except (OSError, RuntimeError, AttributeError, NotImplementedError):
        pass
    return "Недоступно"


def cpu_info():
    freq = psutil.cpu_freq()
    return {
        "Физических ядер": psutil.cpu_count(logical=False) or "Нет данных",
        "Логических ядер": psutil.cpu_count(logical=True) or "Нет данных",
        "Частота сейчас": f"{freq.current:.0f} МГц" if freq else "Не поддерживается",
        "Максимальная частота": f"{freq.max:.0f} МГц" if freq and freq.max else "Не поддерживается",
        "Нагрузка": f"{psutil.cpu_percent(interval=0.1):.1f} %",
        "Температура": cpu_temperature(),
        "По ядрам, %": ", ".join(str(round(x)) for x in psutil.cpu_percent(interval=0.1, percpu=True)),
    }


def memory_info():
    v = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "Всего RAM": fmt_bytes(v.total),
        "Используется": fmt_bytes(v.used),
        "Доступно": fmt_bytes(v.available),
        "Загрузка RAM": f"{v.percent:.1f} %",
        "Файл подкачки": fmt_bytes(swap.total),
        "Использовано подкачки": fmt_bytes(swap.used),
        "Загрузка подкачки": f"{swap.percent:.1f} %",
    }


def disks_info():
    parts = []
    seen = set()
    for part in psutil.disk_partitions(all=False):
        if part.mountpoint in seen:
            continue
        seen.add(part.mountpoint)
        try:
            d = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError) as exc:
            logger.debug("Диск пропущен %s: %s", part.device, exc)
            continue
        parts.append({
            "device": part.device, "mountpoint": part.mountpoint,
            "fstype": part.fstype or "?", "total": d.total,
            "used": d.used, "free": d.free, "percent": d.percent,
        })
    return parts


def network_info():
    result = []
    addresses = psutil.net_if_addrs()
    for name, stats in psutil.net_if_stats().items():
        ads = addresses.get(name, [])
        ipv4 = [a.address for a in ads if a.family == socket.AF_INET]
        mac = [a.address for a in ads if a.family == psutil.AF_LINK]
        result.append({
            "name": name, "up": stats.isup, "speed": stats.speed,
            "ip": ", ".join(ipv4) or "Нет", "mask": ", ".join(a.netmask or "" for a in ads if a.family == socket.AF_INET) or "Нет",
            "mac": ", ".join(mac) or "Нет",
        })
    return result


def battery_info():
    try:
        b = psutil.sensors_battery()
    except (OSError, NotImplementedError):
        b = None
    if b is None:
        return None
    return {
        "percent": round(b.percent, 1),
        "plugged": bool(b.power_plugged),
        "remaining": b.secsleft if b.secsleft is not None and b.secsleft >= 0 else None,
    }


def gpu_info():
    """NVIDIA: нагрузка, температура и VRAM. Другие GPU: ограниченные данные."""
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            p = subprocess.run([
                exe, "--query-gpu=name,utilization.gpu,temperature.gpu,memory.total,memory.used",
                "--format=csv,noheader,nounits",
            ], capture_output=True, text=True, timeout=4, check=True)
            result = []
            for line in p.stdout.strip().splitlines():
                values = [x.strip() for x in line.split(",")]
                if len(values) == 5:
                    result.append(dict(zip(("name", "load", "temp", "vram_total", "vram_used"), values)))
            if result:
                return result
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            logger.info("Не удалось прочитать nvidia-smi: %s", exc)
    # Только имя видеокарты через системную команду Windows (без стороннего WMI).
    if sys.platform == "win32":
        try:
            cmd = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            if cmd.stdout.strip():
                return [{"name": x.strip(), "load": "—", "temp": "—", "vram_total": "—", "vram_used": "—"}
                        for x in cmd.stdout.splitlines() if x.strip()]
        except (OSError, subprocess.SubprocessError):
            pass
    return []


def monitor_info():
    """Разрешение основного монитора (Windows)."""
    if sys.platform != "win32":
        return {"Разрешение": "Доступно для Windows", "Частота": "Зависит от ОС"}
    try:
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        refresh = "Недоступна"
        try:
            cmd = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty CurrentRefreshRate"],
                capture_output=True, text=True, timeout=4, check=True,
            )
            rates = [int(x.strip()) for x in cmd.stdout.splitlines() if x.strip().isdigit()]
            plausible = [x for x in rates if 24 <= x <= 500]
            if plausible:
                refresh = f"{plausible[0]} Гц (по данным драйвера)"
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
        return {"Разрешение": f"{w} × {h}", "Частота": refresh}
    except (AttributeError, OSError):
        return {"Разрешение": "Нет данных", "Частота": "Нет данных"}


def processes_info(top=25, search="", sort="cpu"):
    """Процессы с PID, CPU и RAM; без доступа к чужим файлам."""
    result = []
    for p in psutil.process_iter(attrs=["pid", "name", "memory_info"]):
        try:
            name = p.info.get("name") or "Неизвестно"
            if search and search.casefold() not in name.casefold():
                continue
            memory = p.info.get("memory_info")
            result.append({
                "pid": p.pid, "name": name,
                "cpu": round(p.cpu_percent(interval=None), 1),
                "memory": memory.rss if memory else 0,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    result.sort(key=lambda row: row["memory"] if sort == "ram" else row["cpu"], reverse=True)
    return result[:max(1, min(top, 200))]


def startup_info():
    """Показывает автозагрузку без внесения изменений в систему."""
    items = []
    if sys.platform == "win32":
        import winreg
        for root, name in [(winreg.HKEY_CURRENT_USER, "Пользователь"),
                           (winreg.HKEY_LOCAL_MACHINE, "Все пользователи")]:
            try:
                with winreg.OpenKey(root, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                    i = 0
                    while True:
                        try:
                            entry, value, _ = winreg.EnumValue(key, i)
                            items.append({"name": entry, "command": str(value), "source": name})
                            i += 1
                        except OSError:
                            break
            except PermissionError:
                logger.info("Нет доступа к автозагрузке: %s", name)
            except OSError:
                continue
    elif sys.platform.startswith("linux"):
        path = Path.home() / ".config" / "autostart"
        for file in sorted(path.glob("*.desktop")):
            items.append({"name": file.stem, "command": str(file), "source": "Autostart"})
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "LaunchAgents"
        for file in sorted(path.glob("*.plist")):
            items.append({"name": file.stem, "command": str(file), "source": "LaunchAgents"})
    return items


def folder_info(folder, max_files=12000):
    """Обход папки с ограничением, без чтения содержимого файлов."""
    root = Path(folder).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("Указанная папка не существует")
    total = 0
    files = 0
    dirs = 0
    biggest = []
    truncated = False
    for base, dirnames, filenames in os.walk(root, followlinks=False):
        dirs += len(dirnames)
        for filename in filenames:
            files += 1
            if files > max_files:
                truncated = True
                break
            path = Path(base) / filename
            try:
                if path.is_symlink():
                    continue
                size = path.stat().st_size
            except (OSError, PermissionError):
                continue
            total += size
            biggest.append((size, str(path)))
            biggest.sort(reverse=True)
            if len(biggest) > 15:
                biggest.pop()
        if truncated:
            break
    return {"path": str(root), "files": min(files, max_files), "folders": dirs,
            "total": total, "biggest": biggest[:10], "truncated": truncated}
