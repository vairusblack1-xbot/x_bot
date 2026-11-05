# -*- coding: utf-8 -*-
"""اختبارات ذاتية: تشغّل مشاريع حقيقية (Python/Node/HTML) وتفحص البوابة. لا تحتاج توكن ولا إنترنت."""
import os
import subprocess
import sys


def run(root):
    tests = root
    total_fail = 0
    for name in ("test_engine.py", "test_web.py", "test_panel.py", "test_studio.py", "test_restore.py"):
        path = os.path.join(tests, name)
        if not os.path.exists(path):
            continue
        print(f"\n=== {name} ===", flush=True)
        r = subprocess.run([sys.executable, path], cwd=root)
        total_fail += 1 if r.returncode else 0
    print("\n" + ("✅ كل الاختبارات نجحت" if not total_fail else f"❌ فشلت {total_fail} مجموعة"))
    return 1 if total_fail else 0
