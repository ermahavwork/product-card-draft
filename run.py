#!/usr/bin/env python3
"""Установка и запуск одной командой: python run.py

Создаёт окружение, ставит Django и зависимости, создаёт .env и запускает сервер.
С ключом --frontend заново собирает интерфейс Angular: для этого нужен Node.js 20 или новее.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


def venv_python(os_name: str = os.name) -> Path:
    return VENV / "Scripts" / "python.exe" if os_name == "nt" else VENV / "bin" / "python"


def prepare_env(root: Path = ROOT) -> None:
    if not (root / ".env").exists():
        shutil.copy(root / "env.example", root / ".env")


def build_frontend() -> None:
    npm = shutil.which("npm")
    if not npm:
        sys.exit("Для --frontend нужен Node.js 20 или новее: https://nodejs.org. Без этого ключа используется готовая сборка.")
    subprocess.run([npm, "ci"], cwd=ROOT / "frontend", check=True)
    subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend", check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Установка и запуск сервиса")
    parser.add_argument("--port", default="8000")
    parser.add_argument("--frontend", action="store_true", help="заново собрать интерфейс Angular")
    args = parser.parse_args()

    if sys.version_info < (3, 11):
        sys.exit("Нужен Python 3.11 или новее.")
    if not venv_python().exists():
        print("Создаю окружение .venv")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    print("Устанавливаю Django и зависимости")
    subprocess.run([str(venv_python()), "-m", "pip", "install", "--quiet", "-e", ".[dev]"], cwd=ROOT, check=True)
    prepare_env()
    if args.frontend:
        print("Собираю интерфейс Angular")
        build_frontend()
    print(f"Откройте http://127.0.0.1:{args.port} и выберите модель demo. Остановить сервер: Ctrl+C")
    try:
        subprocess.run([str(venv_python()), "manage.py", "runserver", f"127.0.0.1:{args.port}", "--noreload"], cwd=ROOT, check=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
