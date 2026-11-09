"""Веб-сайт «Информация о ПК» на PyWebIO. Запуск: python app.py"""
import hmac
import errno
import os
import threading
import time
from datetime import datetime
from html import escape as html_escape
from pathlib import Path

import psutil

from pywebio import start_server
from pywebio.input import input as web_input, PASSWORD, NUMBER
from pywebio.output import (
    put_html, put_scope, use_scope, put_buttons, put_button,
    put_text, put_warning, put_error, put_success, put_file, put_info,
)
from pywebio.session import set_env, register_thread, defer_call

import metrics_history as metrics
from logger_setup import logger, read_logs, LOG_DIR
from pc_stats import (
    quick_stats, fmt_bytes, system_info, cpu_info, memory_info,
    disks_info, network_info, battery_info, gpu_info, monitor_info,
    processes_info, startup_info, folder_info,
)
from features import diagnose, check_network, close_process, cpu_benchmark
from reports import collect_report_data, html_report, text_report

BASE = Path(__file__).resolve().parent
SITE_HTML = (BASE / "assets" / "site.html").read_text(encoding="utf-8")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8080"))
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

PAGES = [
    ("📊 Обзор", "dashboard"), ("🖥 Система", "system"),
    ("⚙️ CPU", "cpu"), ("🧠 RAM", "memory"),
    ("💾 Диски", "disks"), ("🌐 Сеть", "network"),
    ("🎮 GPU", "gpu"), ("📋 Процессы", "processes"),
    ("🚀 Автозагрузка", "startup"), ("📂 Папки", "folder"),
    ("📶 Тест сети", "network_test"), ("🧪 Бенчмарк", "benchmark"),
    ("🩺 Диагностика", "diagnostics"), ("📈 История", "history"),
    ("📑 Отчёты", "reports"), ("📜 Логи", "logs"),
]
LIVE_PAGES = {"dashboard", "cpu", "memory", "network", "gpu"}


def h(text):
    return html_escape(str(text), quote=True)


def section(title, subtitle=""):
    put_html(f'<div class="section-title">{h(title)}</div><div class="section-sub">{h(subtitle)}</div>')


def panel(title, inner):
    return f'<div class="panel"><h3>{h(title)}</h3>{inner}</div>'


def table(headers, rows):
    head = "".join(f"<th>{h(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{h(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    if not rows:
        body = f'<tr><td colspan="{len(headers)}">Нет доступных данных</td></tr>'
    return f'<table class="data-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def kv_table(values):
    return table(["Параметр", "Значение"], list(values.items()))


def stat_card(label, value, hint, percent=None):
    fill = ""
    if percent is not None:
        percent = max(0, min(float(percent), 100))
        cls = " high" if percent >= 85 else ""
        fill = f'<div class="progressline"><div class="progressfill{cls}" style="width:{percent:.1f}%"></div></div>'
    return f'<div class="metric"><div class="eyebrow">{h(label)}</div>' \
           f'<div class="number">{h(value)}</div>{fill}<div class="hint">{h(hint)}</div></div>'


def chart_svg(values, color="#6fb2ff", max_value=100, unit="%"):
    """SVG на Python. Отдельный JS и сторонние CDN не нужны."""
    values = [float(v) for v in values]
    if not values:
        return '<div class="state state-info">История ещё собирается. Данные появятся через несколько секунд.</div>'
    w, height, padx, pady = 600, 170, 12, 12
    if len(values) == 1:
        values = [values[0], values[0]]
    upper = max(max_value, max(values) * 1.15, 1)
    points = []
    for i, value in enumerate(values):
        x = padx + i / (len(values) - 1) * (w - 2 * padx)
        y = height - pady - min(value / upper, 1) * (height - 2 * pady)
        points.append((x, y))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    fill = f"{padx},{height-pady} {line} {w-padx},{height-pady}"
    guides = "".join(f'<line x1="0" y1="{y}" x2="600" y2="{y}" stroke="#233550" stroke-dasharray="4 6"/>' for y in (44, 85, 127))
    return (f'<svg class="svg-chart" viewBox="0 0 {w} {height}" preserveAspectRatio="none" role="img" aria-label="График значений">'
            f'{guides}<polygon points="{fill}" fill="{color}" opacity=".10"/>'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="3" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{points[-1][0]:.1f}" cy="{points[-1][1]:.1f}" r="4" fill="{color}"/>'
            f'</svg><div class="legend">Текущее значение: <b>{values[-1]:.1f}{h(unit)}</b> '
            f'· {len(values)} замеров · обновление каждые 5 секунд</div>')


def alerts_html(stats):
    return "".join(f'<div class="state state-{kind}">{h(message)}</div>' for kind, message in diagnose(stats))


def network_speed(history):
    if len(history) < 2:
        return "Измеряется…", "Измеряется…"
    a, b = history[-2:]
    sec = max(0.001, b["timestamp"] - a["timestamp"])
    rx = max(0, b["net_recv"] - a["net_recv"]) / sec
    tx = max(0, b["net_sent"] - a["net_sent"]) / sec
    return f"{fmt_bytes(rx)}/с", f"{fmt_bytes(tx)}/с"


def render_dashboard(s, hist):
    rx, tx = network_speed(hist)
    hrs, mins = divmod(s["uptime_s"] // 60, 60)
    metrics = "".join([
        stat_card("Процессор", f'{s["cpu"]:.0f}%', "Нагрузка CPU", s["cpu"]),
        stat_card("Оперативная память", f'{s["ram"]:.0f}%', f'{fmt_bytes(s["memory_used"])} / {fmt_bytes(s["memory_total"])}', s["ram"]),
        stat_card("Системный диск", f'{s["disk"]:.0f}%', "Занято пространства", s["disk"]),
        stat_card("Процессы", str(s["processes"]), f"Время работы: {hrs} ч {mins} мин"),
    ])
    charts = (
        panel("⚡ История загрузки CPU", chart_svg([p["cpu"] for p in hist], "#62b5ff")) +
        panel("🧠 История использования RAM", chart_svg([p["ram"] for p in hist], "#5fe0b3"))
    )
    net = panel("🌐 Сетевая активность", kv_table({
        "Получение": rx, "Отправка": tx,
        "Всего получено с запуска ОС": fmt_bytes(s["net_recv"]),
        "Всего отправлено с запуска ОС": fmt_bytes(s["net_sent"]),
    }))
    return (f'<div class="metric-grid">{metrics}</div>'
            f'<div class="two-grid">{charts}</div>'
            f'<div class="two-grid">{net}{panel("🩺 Быстрая диагностика", alerts_html(s))}</div>'
            f'<div class="legend">Последнее обновление: {datetime.now():%H:%M:%S}. '
            'Показатели относятся к компьютеру, на котором запущен Python.</div>')


def render_live(page):
    s = quick_stats()
    hist = metrics.history(120)
    if page == "dashboard":
        return render_dashboard(s, hist)
    if page == "cpu":
        return '<div class="metric-grid">' + stat_card("CPU", f'{s["cpu"]}%', "Текущая нагрузка", s["cpu"]) + '</div>' + \
            '<div class="two-grid">' + panel("CPU за последние 10 минут", chart_svg([x["cpu"] for x in hist])) + \
            panel("Детали процессора", kv_table(cpu_info())) + '</div>'
    if page == "memory":
        return '<div class="metric-grid">' + stat_card("RAM", f'{s["ram"]}%', "Текущая загрузка", s["ram"]) + '</div>' + \
            '<div class="two-grid">' + panel("RAM за последние 10 минут", chart_svg([x["ram"] for x in hist], "#52e5b7")) + \
            panel("Детали RAM и подкачки", kv_table(memory_info())) + '</div>'
    if page == "network":
        rx, tx = network_speed(hist)
        return '<div class="metric-grid">' + stat_card("Приём", rx, "Скорость входящего трафика") + \
               stat_card("Передача", tx, "Скорость исходящего трафика") + '</div>' + \
               panel("Сетевые интерфейсы", table(["Адаптер", "Статус", "IPv4", "Маска", "MAC", "Мбит/с"], [
                   (a["name"], "Работает" if a["up"] else "Отключён", a["ip"], a["mask"], a["mac"], a["speed"])
                   for a in network_info()]))
    if page == "gpu":
        gpus = gpu_info()
        if not gpus:
            return '<div class="state state-warning">Не получилось прочитать GPU. NVIDIA: установите рабочий драйвер с nvidia-smi. Для других GPU часть показателей недоступна.</div>'
        return "".join(panel(g["name"], kv_table({
            "Загрузка GPU": g["load"] + "%" if g["load"] != "—" else "Недоступно",
            "Температура": g["temp"] + " °C" if g["temp"] != "—" else "Недоступно",
            "Видеопамять": g["vram_used"] + " / " + g["vram_total"] + " МБ" if g["vram_total"] != "—" else "Недоступно",
        })) for g in gpus)
    return ""


def start_sampler(stop):
    """Один фоновый сборщик на весь сайт (не на каждого посетителя)."""
    last_alert = {}
    while not stop.is_set():
        try:
            s = quick_stats()
            metrics.save(s)
            for key in ("cpu", "ram", "disk"):
                if s[key] >= 95 and time.time() - last_alert.get(key, 0) > 300:
                    msg = f"Высокая нагрузка: {key.upper()} {s[key]}%"
                    logger.warning(msg)
                    last_alert[key] = time.time()
        except Exception:
            logger.exception("Ошибка при сохранении метрик")
        stop.wait(5)


def main():
    set_env(title="Информация о ПК · PyWebIO", auto_scroll_bottom=False)
    if APP_PASSWORD:
        for attempt in range(3):
            password = web_input("Пароль для входа в мониторинг", type=PASSWORD, required=True)
            if hmac.compare_digest((password or "").encode("utf-8"), APP_PASSWORD.encode("utf-8")):
                logger.info("Успешная авторизация в веб-панели")
                break
            put_error("Неверный пароль")
            logger.warning("Неверный пароль при входе в веб-панель")
        else:
            put_error("Слишком много неудачных попыток. Обновите страницу позже.")
            return

    put_html(SITE_HTML)
    put_html('<div class="nav-label">Разделы приложения</div>')
    page_lock = threading.RLock()
    state = {"page": "dashboard", "proc_search": "", "proc_sort": "cpu"}
    stop = threading.Event()

    def refresh_current_live():
        with page_lock:
            page = state["page"]
            if page in LIVE_PAGES:
                with use_scope("live", clear=True):
                    try:
                        put_html(render_live(page))
                    except Exception:
                        logger.exception("Ошибка обновления раздела %s", page)
                        put_error("Не получилось обновить показатели. Проверьте журнал ошибок.")

    def pages_handler(page):
        with page_lock:
            state["page"] = page
            logger.info("Открыт раздел сайта: %s", page)
            with use_scope("screen", clear=True):
                try:
                    render_page(page)
                except Exception:
                    logger.exception("Ошибка отображения раздела %s", page)
                    put_error("Ошибка отображения. Подробности в логах.")

    def show_processes():
        procs = processes_info(35, state["proc_search"], state["proc_sort"])
        put_html(panel("Процессы (ТОП)", table(["PID", "Название", "CPU", "RAM"], [
            (p["pid"], p["name"], f'{p["cpu"]:.1f} %', fmt_bytes(p["memory"])) for p in procs
        ])))
        put_html('<div class="legend">Первое измерение нагрузки отдельного процесса может показывать 0%. Нажмите «Обновить» через несколько секунд.</div>')

    def process_search():
        value = web_input("Найти процесс по названию (пусто = все)", value=state["proc_search"], required=False)
        state["proc_search"] = (value or "")[:120]
        pages_handler("processes")

    def process_sort(sort):
        state["proc_sort"] = sort
        pages_handler("processes")

    def terminate_process():
        pid = web_input("PID процесса для завершения", type=NUMBER, required=True,
                        validate=lambda value: None if value > 0 and float(value).is_integer()
                        else "Введите целый положительный PID")
        if pid is None:
            return
        confirm = web_input(f"Чтобы завершить PID {pid}, введите: ЗАВЕРШИТЬ", required=True)
        if confirm != "ЗАВЕРШИТЬ":
            put_warning("Отменено: подтверждение не совпало.")
            return
        try:
            message = close_process(int(pid))
            put_success(message)
        except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied, PermissionError, OSError) as exc:
            logger.warning("Завершение PID %s отклонено: %s", pid, exc)
            put_error(f"Не удалось завершить: {exc}")

    def scan_folder():
        folder = web_input("Укажите путь к папке на компьютере с запущенным Python", value=str(Path.home()), required=True)
        if not folder:
            return
        with use_scope("result", clear=True):
            try:
                put_info("Сканирование ограничено 12 000 файлами, чтобы сайт не зависал на огромных дисках.")
                res = folder_info(folder)
                put_html(panel("Результаты сканирования", kv_table({
                    "Путь": res["path"], "Файлы": res["files"], "Подпапки": res["folders"],
                    "Общий размер": fmt_bytes(res["total"]),
                    "Результат": "Неполный: достигнут лимит" if res["truncated"] else "Полный",
                }) + table(["Размер", "Крупнейшие файлы"], [(fmt_bytes(size), path) for size, path in res["biggest"]])))
                logger.info("Просканирована папка: %s", res["path"])
            except (OSError, ValueError, PermissionError) as exc:
                logger.warning("Ошибка обхода папки: %s", exc)
                put_error(f"Сканирование не удалось: {exc}")

    def net_test():
        host = web_input("Хост для проверки, например example.com", value="example.com", required=True)
        if not host:
            return
        with use_scope("result", clear=True):
            try:
                put_info("Выполняется DNS, TCP-подключение и ping…")
                r = check_network(host)
                put_html(panel("Проверка сети", kv_table({
                    "Хост": r["host"], "IP-адреса": ", ".join(r["dns"]),
                    "Время DNS": f'{r["dns_ms"]} мс',
                    "TCP 443": f'{r["tcp_ms"]} мс' if r["tcp_ms"] is not None else r.get("tcp_error", "Нет соединения"),
                }) + f'<div class="codebox">{h(r["ping"])}</div>'))
            except (OSError, ValueError, TimeoutError) as exc:
                logger.warning("Ошибка проверки сети: %s", exc)
                put_error(f"Нет ответа: {exc}")

    def benchmark():
        with use_scope("result", clear=True):
            try:
                r = cpu_benchmark()
                put_html(panel("Результаты теста CPU", kv_table({
                    "SHA-256 вычислений": r["rounds"],
                    "Время": f'{r["seconds"]:.3f} с',
                    "Оценка": f'{r["score"]:,} операций/с',
                    "Контрольная сумма": r["checksum"],
                }) + '<div class="state state-info">Условный тест для сравнения одинаковых запусков, не профессиональный бенчмарк.</div>'))
            except Exception:
                logger.exception("Бенчмарк завершился с ошибкой")
                put_error("Ошибка теста, подробности в логах.")

    def clear_history():
        confirm = web_input("Для сброса временной истории введите ОЧИСТИТЬ", required=True)
        if confirm == "ОЧИСТИТЬ":
            metrics.clear_history()
            put_success("История удалена")
            pages_handler("history")
        else:
            put_warning("Очистка отменена")

    def render_page(page):
        if page in LIVE_PAGES:
            names = {"dashboard": ("Панель мониторинга", "Состояние ПК обновляется каждые 3 секунды."),
                     "cpu": ("Процессор", "Нагрузка и частота ядер."),
                     "memory": ("Оперативная память", "RAM, файл подкачки и история."),
                     "network": ("Сетевые интерфейсы", "IP, MAC и скорость передачи данных."),
                     "gpu": ("Видеокарта", "Наличие датчиков зависит от оборудования и драйверов.")}
            section(*names[page])
            put_scope("live")
            refresh_current_live()
        elif page == "system":
            section("Сведения о системе", "Данные из platform, sys, os и psutil.")
            put_html('<div class="two-grid">' + panel("Информация об ОС", kv_table(system_info())) +
                     panel("Монитор и батарея", kv_table({
                         **monitor_info(), "Батарея": (
                             str(battery_info()["percent"]) + "%" if battery_info() else "Не обнаружена"),
                         "Зарядка": ("Да" if battery_info()["plugged"] else "Нет") if battery_info() else "—",
                         "Остаток заряда": (f"{battery_info()['remaining'] // 60} минут"
                             if battery_info() and battery_info()["remaining"] is not None else "—"),
                     })) + '</div>')
        elif page == "disks":
            section("Диски и разделы", "Объём, файловая система, занятое и свободное пространство.")
            disks = disks_info()
            cards = "".join(stat_card(d["mountpoint"], f'{d["percent"]:.0f}%',
                                    f'{fmt_bytes(d["free"])} свободно', d["percent"]) for d in disks)
            put_html('<div class="metric-grid">' + cards + '</div>')
            put_html(panel("Все разделы", table(["Устройство", "Точка монтирования", "Тип", "Всего", "Свободно"], [
                (d["device"], d["mountpoint"], d["fstype"], fmt_bytes(d["total"]), fmt_bytes(d["free"])) for d in disks
            ])))
        elif page == "processes":
            section("Диспетчер процессов", "Поиск, сортировка и завершение по PID после подтверждения.")
            put_buttons([
                ("🔎 Найти", "search"), ("↻ Обновить", "refresh"),
                ("По CPU", "cpu"), ("По RAM", "ram"), ("⛔ Завершить по PID", "kill")
            ], onclick=lambda choice: {
                "search": process_search, "refresh": lambda: pages_handler("processes"),
                "cpu": lambda: process_sort("cpu"), "ram": lambda: process_sort("ram"),
                "kill": terminate_process,
            }[choice](), serial_mode=True)
            put_html(f'<div class="legend">Фильтр: {h(state["proc_search"] or "все процессы")}. Сортировка: {h(state["proc_sort"])}</div>')
            show_processes()
        elif page == "startup":
            section("Автозагрузка", "Список приложений, запускающихся при входе в систему. Только просмотр.")
            items = startup_info()
            put_html(panel("Записи автозагрузки", table(["Название", "Команда / путь", "Источник"], [
                (x["name"], x["command"], x["source"]) for x in items
            ])))
        elif page == "folder":
            section("Анализ папок", "Поиск крупных файлов и подсчёт размера папки.")
            put_button("📂 Выбрать папку", onclick=scan_folder)
            put_scope("result")
        elif page == "network_test":
            section("Диагностика интернета", "Проверить DNS, TCP-подключение и ping.")
            put_button("📶 Запустить проверку сети", onclick=net_test)
            put_scope("result")
        elif page == "benchmark":
            section("Бенчмарк CPU", "Короткий локальный тест вычисления SHA-256.")
            put_info("Тест ограничен 60 000 операциями. Не запускает длительную стресс-нагрузку.")
            put_button("🧪 Запустить тест", onclick=benchmark)
            put_scope("result")
        elif page == "diagnostics":
            section("Автоматическая диагностика", "Проверка пороговых значений и состояние батареи.")
            s = quick_stats()
            put_html(panel("Проверка состояния", alerts_html(s)))
            put_html(panel("Снимок системы", kv_table({
                "CPU": f'{s["cpu"]}%', "RAM": f'{s["ram"]}%', "Диск": f'{s["disk"]}%',
                "Процессы": s["processes"], "Время": datetime.now().strftime("%H:%M:%S"),
            })))
            put_button("↻ Проверить повторно", onclick=lambda: pages_handler("diagnostics"))
        elif page == "history":
            section("История мониторинга", "Последние 10 минут в памяти: замер каждые 5 секунд. При закрытии программы история исчезает, на диск не записывается.")
            hist = metrics.history(120)
            put_html('<div class="two-grid">' + panel("График CPU", chart_svg([x["cpu"] for x in hist])) +
                     panel("График RAM", chart_svg([x["ram"] for x in hist], "#4dd5aa")) + '</div>')
            put_html(panel("Последние записи", table(["Время", "CPU", "RAM", "Диск", "Процессы"], [
                (datetime.fromtimestamp(x["timestamp"]).strftime("%H:%M:%S"),
                 f'{x["cpu"]:.1f}%', f'{x["ram"]:.1f}%', f'{x["disk"]:.1f}%', x["processes"])
                for x in reversed(hist[-30:])
            ])))
            put_buttons([("↻ Обновить", "refresh"), ("🗑 Очистить историю", "clear")],
                        onclick=lambda x: pages_handler("history") if x == "refresh" else clear_history(),
                        serial_mode=True)
        elif page == "reports":
            section("Экспорт отчётов", "TXT и самостоятельная HTML-страница, которую можно открыть без PyWebIO.")
            data = collect_report_data(quick_stats())
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            put_info("Отчёты формируются непосредственно при открытии раздела.")
            put_file(f"pc_report_{now}.txt", text_report(data).encode("utf-8-sig"), label="📥 Скачать TXT-отчёт")
            put_file(f"pc_report_{now}.html", html_report(data).encode("utf-8"), label="📥 Скачать HTML-отчёт")
            logger.info("Пользователь открыл экспорт отчётов")
        elif page == "logs":
            section("Журнал событий", "RotatingFileHandler, уровни INFO/WARNING/ERROR.")
            put_html(panel("Последние 120 строк", f'<div class="codebox">{h(read_logs(120))}</div>'))
            path = LOG_DIR / "app.log"
            if path.exists():
                put_file("app.log", path.read_bytes(), label="📥 Скачать app.log")
            put_button("↻ Обновить логи", onclick=lambda: pages_handler("logs"))
        else:
            put_error("Неизвестный раздел")

    put_buttons([{"label": label, "value": key} for label, key in PAGES],
                onclick=pages_handler, outline=True, group=False, serial_mode=True)
    put_scope("screen")
    pages_handler("dashboard")
    put_html('<div class="info-foot">Информация о ПК • Python + psutil + PyWebIO • '
             'Панель показывает компьютер, где запущен сервер. '
             'Не публикуйте сервер в интернете без полноценной защиты.</div>')

    def refresh_loop():
        while not stop.wait(3):
            if state["page"] in LIVE_PAGES:
                try:
                    refresh_current_live()
                except Exception:
                    logger.exception("Ошибка фонового обновления страницы")

    t = threading.Thread(target=refresh_loop, name="BrowserRefresher", daemon=True)
    register_thread(t)
    t.start()

    @defer_call
    def cleanup():
        stop.set()
        logger.info("Веб-сессия закрыта")


def run():
    if HOST not in ("127.0.0.1", "localhost", "::1") and not APP_PASSWORD:
        raise SystemExit("Для доступа по локальной сети установите APP_PASSWORD. Без пароля разрешён только 127.0.0.1.")
    stop = threading.Event()
    threading.Thread(target=start_sampler, args=(stop,), daemon=True, name="MetricsSampler").start()
    logger.info("Сайт запускается на http://%s:%d", HOST, PORT)
    try:
        start_server(main, host=HOST, port=PORT, auto_open_webbrowser=True,
                     cdn=False, debug=False)
    except KeyboardInterrupt:
        logger.info("Сервер остановлен пользователем")
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE or getattr(exc, "winerror", None) == 10048:
            raise SystemExit(
                f"Порт {PORT} уже занят. Возможно, программа уже запущена.\n"
                f"Откройте http://127.0.0.1:{PORT} в браузере или остановите "
                "предыдущий запуск клавишами Ctrl+C в его окне."
            ) from None
        raise
    finally:
        stop.set()


if __name__ == "__main__":
    run()
