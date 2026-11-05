#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)


def load_env(path=os.path.join(ROOT, ".env")):
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8-sig") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln or ln.startswith("#") or "=" not in ln:
                continue
            k, v = ln.split("=", 1)
            k, v = k.replace("export ", "").strip(), v.strip().strip("'\"")
            if k and v and not os.environ.get(k):
                os.environ[k] = v


def ensure_dependency(module, pip_name):
    try:
        __import__(module)
        return True
    except ImportError:
        pass
    print(f"[setup] تثبيت {pip_name} ...", flush=True)
    base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", pip_name]
    for extra in ([], ["--break-system-packages"], ["--user"]):
        if subprocess.run(base + extra).returncode == 0:
            try:
                __import__(module)
                return True
            except ImportError:
                continue
    return False


def main():
    load_env()
    data = os.path.join(ROOT, "data")
    os.makedirs(os.path.join(data, "projects"), exist_ok=True)
    os.environ.setdefault("DB_PATH", os.path.join(data, "hosting_bot.db"))
    os.environ.setdefault("PROJECTS_DIR", os.path.join(data, "projects"))
    os.environ.setdefault("RUNTIME_DIR", os.path.join(ROOT, "runtime"))

    if sys.version_info < (3, 9):
        sys.exit("❌ يلزم Python 3.9 أو أحدث.")
    if not ensure_dependency("telebot", "pyTelegramBotAPI"):
        sys.exit("❌ تعذر تثبيت pyTelegramBotAPI تلقائياً. نفّذ: pip install pyTelegramBotAPI")
    ensure_dependency("psutil", "psutil")

    if ":" not in os.environ.get("BOT_TOKEN", ""):
        sys.exit("❌ لم يتم تحديد BOT_TOKEN.\n   اكتبه في متغيرات البيئة أو في ملف .env: BOT_TOKEN=123456:ABC...")

    import host_core as core
    import gateway
    import webpanel
    import studio
    import tools_cmds

    core.db_init()
    core.db_create_schema()
    core.db_ensure_columns()
    core._ensure_advanced_schema()
    gateway.install(core)
    tools_cmds.install(core, ROOT)
    webpanel.install(core, gateway)
    studio.install(core)
    core.main()


if __name__ == "__main__":
    main()
