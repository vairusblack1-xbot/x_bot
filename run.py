#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مشرف التشغيل 24/7:  python run.py
  - يشغّل app.py ويعيد تشغيله تلقائياً عند أي انهيار (تأخير تصاعدي).
  - python run.py --check      فحص جاهزية السيرفر
  - python run.py --selftest   اختبارات ذاتية حقيقية
  - python run.py --direct     تشغيل app.py مباشرة بدون مشرف
"""
import os
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)


def supervise():
    os.makedirs(os.path.join(ROOT, "data", "logs"), exist_ok=True)
    logf = os.path.join(ROOT, "data", "logs", "supervisor.log")
    state = {"p": None, "stop": False}

    def say(msg):
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
        print(line, flush=True)
        try:
            with open(logf, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            if os.path.getsize(logf) > 2 * 1024 * 1024:
                os.replace(logf, logf + ".1")
        except OSError:
            pass

    def stop(sig, frm):
        state["stop"] = True
        if state["p"] and state["p"].poll() is None:
            state["p"].send_signal(signal.SIGTERM)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    delay = 3
    while not state["stop"]:
        t0 = time.time()
        say("تشغيل app.py ...")
        state["p"] = subprocess.Popen([sys.executable, "-u", os.path.join(ROOT, "app.py")], cwd=ROOT)
        rc = state["p"].wait()
        if state["stop"] or rc == 0:
            say(f"انتهى (code={rc})")
            break
        up = time.time() - t0
        delay = 3 if up > 120 else min(60, delay * 2)
        say(f"app.py توقف (code={rc}) بعد {up:.0f}ث — إعادة التشغيل بعد {delay}ث")
        for _ in range(delay):
            if state["stop"]:
                return
            time.sleep(1)


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--check":
        import app
        app.load_env()
        import diagnostics
        print(diagnostics.format_report(diagnostics.run_checks(ROOT)))
    elif arg == "--selftest":
        import selftest
        sys.exit(selftest.run(ROOT))
    elif arg == "--direct":
        import app
        app.main()
    else:
        supervise()


if __name__ == "__main__":
    main()
