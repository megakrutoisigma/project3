from datetime import datetime
import os
import platform
import time
import getpass
import sys

import psutil
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")
logger.add("pcinfo.log", rotation="5 MB", retention="7 days", level="DEBUG", backtrace=False, diagnose=False)

GB = 1024 ** 3

def system_info():
    logger.info("collect: system")
    print("=== СИСТЕМА ===")
    print("ОС:", platform.system(), platform.release())
    print("Архитектура:", platform.machine())
    print("Имя ПК:", platform.node())
    print("Пользователь:", getpass.getuser())
    print("Python:", platform.python_version())
    print("Текущая папка:", os.getcwd())

def cpu_info():
    logger.info("collect: cpu")
    print("\n=== ПРОЦЕССОР ===")
    print("Модель:", platform.processor() or "N/A")
    print("Ядер (физ / лог):", psutil.cpu_count(logical=False), "/", psutil.cpu_count(logical=True))
    freq = psutil.cpu_freq()
    if freq:
        print("Частота (текущая):", f"{round(freq.current)} МГц")
    print("Загрузка CPU (1s):", f"{psutil.cpu_percent(interval=1)} %")

def ram_info():
    logger.info("collect: ram")
    m = psutil.virtual_memory()
    print("\n=== ПАМЯТЬ ===")
    print("Всего:", f"{m.total/GB:.1f} ГБ", "Занято:", f"{m.used/GB:.1f} ГБ", f"({m.percent}%)")

def disks_info():
    logger.info("collect: disks")
    print("\n=== ДИСКИ ===")
    for part in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError) as e:
            logger.debug(f"skip disk {part.device} ({part.mountpoint}): {e}")
            print(f"{part.device} (монтировано в {part.mountpoint}) — недоступно")
            continue
        print(f"{part.device} (монтировано в {part.mountpoint}) — Всего: {u.total/GB:.1f} ГБ, Занято: {u.percent} %")

def network_info():
    logger.info("collect: network")
    n = psutil.net_io_counters()
    print("\n=== СЕТЬ ===")
    print("Отправлено:", f"{n.bytes_sent/1024**2:.1f} МБ", "Получено:", f"{n.bytes_recv/1024**2:.1f} МБ")

def battery_info():
    logger.info("collect: battery")
    print("\n=== БАТАРЕЯ ===")
    bat = psutil.sensors_battery()
    if not bat:
        print("Батарея: нет")
    else:
        print("Заряд:", f"{bat.percent:.0f} %", "Заряжается:", "Да" if bat.power_plugged else "Нет")

def uptime_info():
    logger.info("collect: uptime")
    boot = psutil.boot_time()
    uptime_s = int(time.time() - boot)
    print("\n=== ВРЕМЯ РАБОТЫ ===")
    print("Загружен:", datetime.fromtimestamp(boot).strftime("%d.%m.%Y %H:%M"))
    print("Время работы:", f"{uptime_s//3600} ч {(uptime_s%3600)//60} мин")

def top_processes(top=5):
    logger.info("collect: processes")
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(0.5)
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            cpu = p.cpu_percent(None)
            mem = p.info.get("memory_info")
            mem_mb = (mem.rss / 1024 ** 2) if mem else 0
            name = p.info.get("name") or "?"
            procs.append((name, cpu, mem_mb))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    procs.sort(key=lambda x: x[1], reverse=True)
    print("\n=== ТОП ПО CPU ===")
    for name, cpu, mem in procs[:top]:
        print(f"{name}: {cpu:.1f} %, {mem:.0f} МБ")

    procs.sort(key=lambda x: x[2], reverse=True)
    print("\n=== ТОП ПО ПАМЯТИ ===")
    for name, cpu, mem in procs[:top]:
        print(f"{name}: {mem:.0f} МБ, {cpu:.1f} %")

def show_all():
    logger.info("show all")
    print("Отчёт —", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    system_info()
    cpu_info()
    ram_info()
    disks_info()
    network_info()
    battery_info()
    uptime_info()
    top_processes()

MENU = {
    "1": ("Система", system_info),
    "2": ("CPU", cpu_info),
    "3": ("Память", ram_info),
    "4": ("Диски", disks_info),
    "5": ("Сеть", network_info),
    "6": ("Батарея", battery_info),
    "7": ("Время работы", uptime_info),
    "8": ("Процессы (топ)", top_processes),
    "9": ("Весь отчёт", show_all),
    "0": ("Выход", None),
}

def main():
    logger.info("app started")
    while True:
        print("\n=== МЕНЮ ===")
        for key, (label, _) in MENU.items():
            print(key + ". " + label)
        choice = input("Выберите пункт: ").strip()
        logger.info(f"user choice: {choice}")
        if choice == "0":
            logger.info("exit by user")
            print("Выход.")
            break
        entry = MENU.get(choice)
        if not entry:
            print("Неверный выбор.")
            continue
        entry[1]()
        input("\nНажмите Enter для продолжения...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("exit (KeyboardInterrupt)")
        print("\nВыход по Ctrl+C")
