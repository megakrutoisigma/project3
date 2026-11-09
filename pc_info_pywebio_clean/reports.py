"""Формирование текстовых и HTML-отчётов на стороне Python."""
from datetime import datetime
from html import escape

from pc_stats import (
    system_info, cpu_info, memory_info, disks_info, network_info,
    gpu_info, fmt_bytes, battery_info,
)
from features import diagnose


def collect_report_data(stats):
    return {
        "date": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "summary": stats,
        "system": system_info(), "cpu": cpu_info(), "memory": memory_info(),
        "disks": disks_info(), "network": network_info(), "gpu": gpu_info(),
        "battery": battery_info(), "diagnostics": diagnose(stats),
    }


def text_report(data):
    lines = ["ИНФОРМАЦИЯ О ПК", "=" * 56, f"Дата: {data['date']}"]
    for heading in ("system", "cpu", "memory"):
        lines.extend(["", heading.upper(), "-" * 35])
        lines.extend(f"{k}: {v}" for k, v in data[heading].items())
    lines.extend(["", "ДИСКИ", "-" * 35])
    for d in data["disks"]:
        lines.append(f"{d['device']} | {d['mountpoint']} | {fmt_bytes(d['total'])} | занято {d['percent']}%")
    lines.extend(["", "СЕТЬ", "-" * 35])
    for n in data["network"]:
        lines.append(f"{n['name']} | IP: {n['ip']} | MAC: {n['mac']} | {'работает' if n['up'] else 'отключено'}")
    lines.extend(["", "GPU", "-" * 35])
    for g in data["gpu"]:
        lines.append(f"{g['name']} | Загрузка: {g['load']}% | Температура: {g['temp']}°C")
    lines.extend(["", "ДИАГНОСТИКА", "-" * 35])
    for _, msg in data["diagnostics"]:
        lines.append(f"- {msg}")
    return "\n".join(lines) + "\n"


def html_report(data):
    def table(d):
        return "<table>" + "".join(
            f"<tr><th>{escape(str(k))}</th><td>{escape(str(v))}</td></tr>"
            for k, v in d.items()) + "</table>"
    disk_table = "".join(
        f"<p>{escape(d['device'])} ({escape(d['mountpoint'])}): "
        f"{fmt_bytes(d['total'])}, занято {d['percent']}%</p>" for d in data["disks"]
    )
    msgs = "".join(f"<li>{escape(msg)}</li>" for _, msg in data["diagnostics"])
    return f"""<!doctype html><html lang="ru"><head><meta charset="UTF-8">
<title>Отчёт · Информация о ПК</title><style>
body{{font:16px Arial,sans-serif;background:#0b1220;color:#e7ecf7;padding:35px;max-width:900px;margin:auto}}
h1{{color:#7aa7ff}}h2{{margin-top:35px;color:#c9d8ff}}
table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:11px;border-bottom:1px solid #344058}}
th{{width:40%;color:#a9b9d4}}li{{margin:9px 0}}
</style></head><body>
<h1>Информация о ПК</h1><p>Отчёт сформирован: {escape(data['date'])}</p>
<h2>Система</h2>{table(data['system'])}
<h2>Процессор</h2>{table(data['cpu'])}
<h2>Память</h2>{table(data['memory'])}
<h2>Диски</h2>{disk_table or 'Нет доступных дисков'}
<h2>Диагностика</h2><ul>{msgs}</ul>
</body></html>"""
