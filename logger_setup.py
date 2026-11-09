"""Единый logger приложения. Логи сохраняются в data/logs/app.log."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = (Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "PCInfoWeb") if getattr(sys, "frozen", False) else BASE / "data"
LOG_DIR = DATA / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("pc_info")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(threadName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def read_logs(limit=120):
    """Читать последние строки текущего лог-файла (максимум 300)."""
    path = LOG_DIR / "app.log"
    if not path.exists():
        return "Логи ещё пусты."
    # Файл ограничен двумя мегабайтами и безопасен для чтения целиком.
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-min(max(limit, 1), 300):]) or "Логи ещё пусты."
