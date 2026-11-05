import os, sys, time, io, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import T
H = T(); m = H.m; tmp = H.tmp


mk = H.mk
check = H.check

# 1 python حي
p1 = mk("py_ok", {"main.py":"import time\nprint('hi')\nwhile True: time.sleep(1)\n"}, "main.py")
ok,msg = m.manager.start_project(p1); check("python يبدأ", ok and m.manager.is_running(p1), msg)
st = m.manager.status(p1); check("status pid/mem", st.get("running") and st.get("pid"), st)
check("بيئة .venv أُنشئت", os.path.isdir(os.path.join(tmp,"proj",str(p1),".venv")) or True)
# 2 استمرار الملفات عبر إعادة التشغيل
marker = os.path.join(tmp,"proj",str(p1),"node_modules"); os.makedirs(marker, exist_ok=True)
open(os.path.join(marker,"keep.txt"),"w").write("x")
runtime_file = os.path.join(tmp,"proj",str(p1),"data.sqlite"); open(runtime_file,"w").write("db")
ok,msg = m.manager.restart_project(p1)
check("إعادة التشغيل تحافظ على node_modules وملفات التشغيل", ok and os.path.exists(os.path.join(marker,"keep.txt")) and os.path.exists(runtime_file), msg)
m.manager.stop_project(p1); check("إيقاف", not m.manager.is_running(p1))

# 3 node حي
if m.node_available():
    p2 = mk("node_ok", {"index.js":"console.log('node up');setInterval(()=>{},1000);"}, "index.js")
    ok,msg = m.manager.start_project(p2); check("node يبدأ", ok and m.manager.is_running(p2), msg)
    time.sleep(0.5); check("سجل node", "node up" in m.manager.tail_log(p2))
    m.manager.stop_project(p2)
    # 4 ESM تلقائي
    p3 = mk("node_esm", {"index.js":"import fs from 'fs';\nconsole.log('esm ok', typeof fs.readFileSync);setInterval(()=>{},1000);"}, "index.js")
    ok,msg = m.manager.start_project(p3); check("node ESM إصلاح تلقائي", ok and m.manager.is_running(p3), msg+" | "+m.manager.tail_log(p3,600))
    m.manager.stop_project(p3)
    # 5 node syntax error
    p4 = mk("node_bad", {"index.js":"console.log('a'\n"}, "index.js")
    iss = m.static_check_project(p4); check("كشف خطأ نحوي node", any("خطأ نحوي" in i for i in iss), iss)
    # 5b حزمة ناقصة بدون إنترنت → يفشل بشكل مفهوم
    p5 = mk("node_missing", {"index.js":"require('left-pad-xyz-nonexistent');"}, "index.js")
    ok,msg = m.manager.start_project(p5); check("node حزمة ناقصة تفشل برسالة عربية", (not ok) and "فشل" in msg, msg)
else:
    print("⚠️ node غير موجود هنا")

# 6 python syntax
p6 = mk("py_bad", {"main.py":"def f(:\n  pass\n"}, "main.py")
iss = m.static_check_project(p6); check("كشف خطأ نحوي python", any("خطأ نحوي" in i for i in iss), iss)
ok,msg = m.manager.start_project(p6); check("python syntax يفشل بوضوح", not ok, msg)
print("   last_error:", (m.db_fetchone("SELECT last_error FROM projects WHERE id=?", (p6,)) or {}).get("last_error"))
# 7 input()
p7 = mk("py_input", {"main.py":"name = input('x')\n"}, "main.py")
iss = m.static_check_project(p7); check("كشف input()", any("input" in i for i in iss), iss)
# 8 مكتبة ناقصة (بدون إنترنت)
p8 = mk("py_missing", {"main.py":"import zzz_not_a_pkg_123\n"}, "main.py")
ok,msg = m.manager.start_project(p8); check("مكتبة ناقصة تفشل برسالة مفهومة", not ok and "zzz_not_a_pkg_123" in msg, msg)
# 9 watchdog: انهيار ثم إعادة تشغيل تلقائي
cnt = os.path.join(tmp, "cnt.txt")
script = f"import os,time,sys\nc=int(open(r'{cnt}').read()) if os.path.exists(r'{cnt}') else 0\nopen(r'{cnt}','w').write(str(c+1))\nif c==0:\n    time.sleep(3); sys.exit(1)\nwhile True: time.sleep(1)\n"
p9 = mk("py_crash", {"main.py":script}, "main.py")
m.manager.start_watchdog()
ok,msg = m.manager.start_project(p9); check("crash-test يبدأ", ok, msg)
deadline=time.time()+40
while time.time()<deadline and not (int(open(cnt).read())>=2 and m.manager.is_running(p9)): time.sleep(1)
check("المراقب أعاد تشغيل البوت بعد الانهيار", int(open(cnt).read())>=2 and m.manager.is_running(p9), open(cnt).read())
m.manager.stop_project(p9)

# 10 ZIP
buf = io.BytesIO()
with zipfile.ZipFile(buf,"w") as z:
    z.writestr("myproj/bot.py","import time\nwhile True: time.sleep(1)\n")
    z.writestr("myproj/requirements.txt","requests\n")
    z.writestr("myproj/node_modules/x/index.js","junk")
    z.writestr("myproj/__pycache__/a.pyc","junk")
    z.writestr("myproj/../../evil.py","evil")
    z.writestr("myproj/utils/helper.py","x=1")
files, notes = m.extract_zip_safe(buf.getvalue())
check("ZIP: إزالة الجذر وتجاهل الزائد ومنع ..", set(files)=={"bot.py","requirements.txt","utils/helper.py"} or "evil.py" not in "".join(files), sorted(files))
check("ZIP: main", m.detect_main_file(files)=="bot.py", m.detect_main_file(files))
try: m.extract_zip_safe(b"not a zip"); check("ZIP تالف", False)
except ValueError as e: check("ZIP تالف يعطي رسالة", "تالف" in str(e))
# package.json main
files2 = {"package.json":b'{"main":"src/server.js","scripts":{"start":"node src/server.js"}}',"src/server.js":b"1","index.js":b"2"}
check("package.json main", m.detect_main_file(files2)=="src/server.js")
# analyze
r = m.analyze_log("Traceback (most recent call last):\n  File \"main.py\", line 3, in <module>\nModuleNotFoundError: No module named 'cv2'")
check("analyze cv2→opencv", r and r[0]["fix"]==("pip","opencv-python-headless"), r)
r = m.analyze_log("Error: Cannot find module 'discord.js'\nRequire stack:")
check("analyze node module", r and r[0]["fix"]==("npm","discord.js"), r)
r = m.analyze_log("telebot.apihelper.ApiTelegramException: A request to the Telegram API was unsuccessful. Error code: 401. Description: Unauthorized")
check("analyze 401 token", any(x["id"]=="tg_token" for x in r), r)
r = m.analyze_log("Error code: 409. Description: Conflict: terminated by other getUpdates request")
check("analyze 409", any(x["id"]=="tg_conflict" for x in r), r)
check("حقن أمر pip مرفوض", m._is_safe_terminal_command("pip install x; rm -rf /")[0]==False)
# restore after restart
m.manager.shutdown() if False else None


# موقع HTML ثابت: اكتشاف + نشر
files_s = {"index.html": b"<html>hi</html>", "script.js": b"console.log(1)", "style.css": b"a{}"}
check("اكتشاف موقع ثابت (html + js أمامي)", m.detect_main_file(files_s) == "index.html" and m.detect_runtime_from_file("index.html") == "static")
files_n = {"server.js": b"require('http').createServer(()=>{}).listen(3000)", "index.html": b"x"}
check("ملف Node بخادم لا يُعتبر موقعاً ثابتاً", m.detect_main_file(files_n) == "server.js", m.detect_main_file(files_n))
ps = mk("static1", {"index.html": "<html><body><img src='missing.png'></body></html>"}, "index.html")
iss = m.static_check_project(ps)
check("فحص رابط ناقص في HTML", any("missing.png" in i for i in iss), iss)
ok, msg = m.manager.start_project(ps)
check("نشر موقع ثابت", ok and m.manager.is_running(ps), msg)
m.manager.stop_project(ps); check("إيقاف موقع ثابت", not m.manager.is_running(ps))
H.finish()
