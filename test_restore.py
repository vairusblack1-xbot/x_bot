import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import T
H = T(); m = H.m
pid = H.mk("a", {"main.py": "import time\nwhile True: time.sleep(1)\n"}, "main.py")
ok, msg = m.manager.start_project(pid)
H.check("البوت يبدأ", ok, msg)
m.manager.shutdown()
H.check("بعد إيقاف الاستضافة يبقى وسم التشغيل للاستعادة", m.db_fetchone("SELECT is_running r FROM projects WHERE id=?", (pid,))["r"] == 1)
m.manager = m.ProcessManager()
m.manager.restore_running(); time.sleep(6)
H.check("الاستعادة التلقائية بعد إعادة تشغيل الاستضافة", m.manager.is_running(pid))
H.finish()
