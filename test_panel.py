import http.client, io, json, os, sys, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["OWNER_USERNAME"] = "boss"; os.environ["OWNER_PASSWORD"] = "OwnerPass123"
from harness import T
H = T(); m = H.m; check = H.check
import gateway, webpanel, monitor
SENT = []
m.bot.send_message = lambda *a, **k: SENT.append((a, k))
gateway.install(m); monitor.start(m); webpanel.install(m, gateway)
m.KEEP_ALIVE_PORT = H.gw_port; gateway.start_gateway(); time.sleep(0.4)
GP = H.gw_port


class S:
    def __init__(self): self.cookie = ""; self.csrf = ""
    def call(self, method, path, body=None, raw=None, fname="f", csrf=True, headers=None):
        h = dict(headers or {})
        if self.cookie: h["Cookie"] = self.cookie
        if csrf and self.csrf: h["X-CSRF"] = self.csrf
        data = None
        if raw is not None:
            data = raw; h["X-Filename"] = fname; h["Content-Type"] = "application/octet-stream"
        elif body is not None:
            data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
        c = http.client.HTTPConnection("127.0.0.1", GP, timeout=30)
        c.request(method, path, body=data, headers=h)
        r = c.getresponse(); b = r.read(); hd = {k.lower(): v for k, v in r.getheaders()}; c.close()
        try: j = json.loads(b)
        except Exception: j = None
        return r.status, j, hd, b
    def login(self, u, p):
        st, j, hd, _ = self.call("POST", "/api/login", {"username": u, "password": p}, csrf=False)
        if st == 200:
            self.cookie = hd["set-cookie"].split(";")[0]; self.csrf = j["csrf"]
        return st, j, hd

def wait(s, pid, cond, secs=45):
    end = time.time() + secs
    while time.time() < end:
        st, j, _, _ = s.call("GET", f"/api/projects/{pid}")
        if st == 200 and cond(j["project"]): return j["project"]
        time.sleep(0.5)
    return None

anon = S()
st, _, hd, body = anon.call("GET", "/")
check("صفحة اللوحة تُخدم", st == 200 and b"Flix Cloud" in body and "frame-ancestors" in hd.get("content-security-policy", ""))
check("لا جلسة → 401", anon.call("GET", "/api/me")[0] == 401)
check("لا جلسة → المشاريع 401", anon.call("GET", "/api/projects")[0] == 401)
st, _, _ = anon.login("boss", "wrong")
check("كلمة مرور خاطئة → 401", st == 401)
owner = S(); st, j, hd = owner.login("boss", "OwnerPass123")
check("دخول المالك", st == 200 and j["user"]["role"] == "owner")
check("الكوكي HttpOnly + SameSite", "HttpOnly" in hd["set-cookie"] and "SameSite=Lax" in hd["set-cookie"], hd["set-cookie"])
check("POST بدون CSRF → 403", owner.call("POST", "/api/admin/accounts", {"username": "x1234"}, csrf=False)[0] == 403)

# إنشاء حسابات — من المالك/المشرف فقط
st, j, _, _ = owner.call("POST", "/api/admin/accounts", {"username": "adm1", "role": "admin", "max_projects": 10})
check("المالك ينشئ مشرفاً بكلمة مرور مولّدة", st == 200 and len(j["password"]) >= 10, j)
adm_pw = j["password"]
admin = S(); check("دخول المشرف", admin.login("adm1", adm_pw)[0] == 200)
st, j, _, _ = admin.call("POST", "/api/admin/accounts", {"username": "user1", "password": "UserPass123", "max_projects": 2})
check("المشرف ينشئ مستخدماً", st == 200, j)
check("المشرف لا ينشئ مشرفاً", admin.call("POST", "/api/admin/accounts", {"username": "adm2", "role": "admin"})[0] == 403)
check("المشرف لا ينشئ مالكاً", admin.call("POST", "/api/admin/accounts", {"username": "own2", "role": "owner"})[0] == 403)
check("اسم مكرر → 409", admin.call("POST", "/api/admin/accounts", {"username": "USER1"})[0] == 409)
check("اسم غير صالح → 400", admin.call("POST", "/api/admin/accounts", {"username": "a b"})[0] == 400)
check("كلمة مرور ضعيفة → 400", admin.call("POST", "/api/admin/accounts", {"username": "weak1", "password": "123"})[0] == 400)
st, j, _, _ = admin.call("GET", "/api/admin/accounts")
own_row = [a for a in j["accounts"] if a["username"] == "boss"][0]
check("المشرف لا يدير المالك", own_row["manageable"] is False and admin.call("PATCH", f"/api/admin/accounts/{own_row['id']}", {"toggle": True})[0] == 403)
user = S(); check("دخول المستخدم", user.login("user1", "UserPass123")[0] == 200)
check("المستخدم لا يدخل لوحة الإدارة", user.call("GET", "/api/admin/accounts")[0] == 403 and user.call("GET", "/api/admin/system")[0] == 403)
check("المستخدم لا ينشئ حسابات", user.call("POST", "/api/admin/accounts", {"username": "hack1234"})[0] == 403)

# مشروع بايثون
BOT = b"import time\nprint('bot-alive', flush=True)\nwhile True: time.sleep(1)\n"
st, j, _, _ = user.call("POST", "/api/projects/upload?name=" + "%3Cimg%20src%3Dx%3Emybot&start=1", raw=BOT, fname="bot.py")
check("رفع مشروع Python", st == 200 and j["id"], j)
pid = j["id"]
p = wait(user, pid, lambda p: p["running"])
check("تشغيل تلقائي بعد الرفع", p is not None and "<" not in p["name"], p)
time.sleep(0.5)
st, j, _, _ = user.call("GET", f"/api/projects/{pid}/logs")
check("السجل الحي", "bot-alive" in j["log"], j)
st, j, _, _ = user.call("GET", f"/api/projects/{pid}/files")
check("قائمة الملفات", [f["name"] for f in j["files"]] == ["bot.py"])
st, j, _, _ = user.call("GET", f"/api/projects/{pid}/file?name=bot.py")
check("قراءة ملف", "bot-alive" in j["content"])
check("تحرير ملف", user.call("PUT", f"/api/projects/{pid}/file?name=extra.txt", raw=b"hello", fname="extra.txt")[0] == 200
      and user.call("GET", f"/api/projects/{pid}/file?name=extra.txt")[1]["content"] == "hello")
check("منع اجتياز المسار في الملفات", user.call("GET", f"/api/projects/{pid}/file?name=../../etc/passwd")[0] == 400)
st, j, _, _ = user.call("PUT", f"/api/projects/{pid}/settings", {"env": "TOKEN=abc\nX=1"})
check("حفظ .env", st == 200 and "TOKEN=abc" in user.call("GET", f"/api/projects/{pid}")[1]["project"]["env"])
st, j, _, _ = user.call("POST", f"/api/projects/{pid}/exec", {"cmd": "python3 --version"})
check("الطرفية: python --version", "Python" in j["output"], j)
st, j, _, _ = user.call("POST", f"/api/projects/{pid}/exec", {"cmd": "ls; rm -rf /"})
check("الطرفية: رفض الحقن", "غير مسموحة" in j["output"], j)
st, j, _, _ = user.call("GET", f"/api/projects/{pid}/analyze")
check("التحليل", "تحليل المشروع" in j["report"] and "<b>" not in j["report"], j)

# حدود الحساب
html = b"<html><body>site-up</body></html>"
st, j, _, _ = user.call("POST", "/api/projects/upload?name=site&start=1", raw=html, fname="index.html")
check("رفع موقع HTML", st == 200, j)
spid = j["id"]; p = wait(user, spid, lambda p: p["running"] and p.get("url"))
check("الموقع الثابت يحصل على رابط", p is not None, p)
if p:
    path = "/s/" + p["slug"] + "/"
    c = http.client.HTTPConnection("127.0.0.1", GP, timeout=10); c.request("GET", path); r = c.getresponse()
    check("الموقع يُخدم عبر البوابة", r.status == 200 and b"site-up" in r.read()); c.close()
st, j, _, _ = user.call("POST", "/api/projects/upload?name=third", raw=BOT, fname="b.py")
check("حد المشاريع للمستخدم → 403", st == 403, j)

# عزل المستخدمين
st, j, _, _ = owner.call("POST", "/api/projects/upload?name=ownerbot&start=0", raw=BOT, fname="o.py")
opid = j["id"]
check("المستخدم لا يرى مشروع غيره", user.call("GET", f"/api/projects/{opid}")[0] == 404 and user.call("POST", f"/api/projects/{opid}/start")[0] == 404
      and user.call("DELETE", f"/api/projects/{opid}")[0] == 404)
check("قائمة المستخدم لا تحوي مشروع غيره", opid not in [x["id"] for x in user.call("GET", "/api/projects")[1]["projects"]])
check("المشرف يرى مشروع المستخدم", admin.call("GET", f"/api/projects/{pid}")[0] == 200)
check("المشرف: كل المشاريع", {pid, opid} <= {x["id"] for x in admin.call("GET", "/api/projects?all=1")[1]["projects"]})
check("المستخدم لا يستخدم all=1", opid not in [x["id"] for x in user.call("GET", "/api/projects?all=1")[1]["projects"]])

# تشغيل/إيقاف/حذف
check("إيقاف", user.call("POST", f"/api/projects/{pid}/stop")[0] == 200 and not user.call("GET", f"/api/projects/{pid}")[1]["project"]["running"])
user.call("POST", f"/api/projects/{pid}/start"); p = wait(user, pid, lambda p: p["running"])
check("إعادة التشغيل", p is not None)
check("حذف مشروع", user.call("DELETE", f"/api/projects/{pid}")[0] == 200 and user.call("GET", f"/api/projects/{pid}")[0] == 404)
st, j, _, _ = user.call("POST", "/api/projects/upload?name=again&start=0", raw=BOT, fname="b.py")
check("بعد الحذف يتاح مشروع جديد", st == 200, j)

# ZIP
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("w/index.html", "<html>zip-web</html>"); z.writestr("w/a.css", "a{}")
st, j, _, _ = owner.call("POST", "/api/projects/upload?name=zipsite&start=1", raw=buf.getvalue(), fname="w.zip")
zp = wait(owner, j["id"], lambda p: p["running"])
check("رفع ZIP لموقع", st == 200 and zp is not None and zp["runtime"] == "static", zp)
st, j, _, _ = owner.call("POST", "/api/projects/upload?name=bad&start=0", raw=b"x", fname="evil.exe")
check("رفض أنواع غير مدعومة", st == 400, j)
st, j, _, _ = owner.call("POST", "/api/projects/upload?name=bad&start=0", raw=b"not a zip", fname="x.zip")
check("رفض ZIP تالف برسالة", st == 400 and "تالف" in j["error"], j)

# تعطيل/إعادة تعيين/حذف الحسابات
st, j, _, _ = admin.call("GET", "/api/admin/accounts")
u1 = [a for a in j["accounts"] if a["username"] == "user1"][0]
check("المشرف يعطّل مستخدماً", admin.call("PATCH", f"/api/admin/accounts/{u1['id']}", {"toggle": True})[0] == 200)
check("جلسة المعطّل تنتهي", user.call("GET", "/api/me")[0] == 401)
check("المعطّل لا يدخل", S().login("user1", "UserPass123")[0] == 401)
admin.call("PATCH", f"/api/admin/accounts/{u1['id']}", {"toggle": True})
st, j, _, _ = admin.call("PATCH", f"/api/admin/accounts/{u1['id']}", {"reset": True})
check("إعادة تعيين كلمة المرور", st == 200 and S().login("user1", j["password"])[0] == 200 and S().login("user1", "UserPass123")[0] == 401)
check("حذف الحساب يحذف مشاريعه", admin.call("DELETE", f"/api/admin/accounts/{u1['id']}")[0] == 200
      and m.db_fetchone("SELECT COUNT(*) AS c FROM projects WHERE user_id=?", (-u1["id"],))["c"] == 0)

# أمان
for i in range(5): S().login("adm1", "bad" + str(i))
st, j, _ = S().login("adm1", adm_pw)
check("حماية التخمين → 429", st == 429, (st, j))
check("غير المالك لا يغيّر الرابط العام", admin.call("POST", "/api/admin/settings", {"public_url": "https://x.example.com"})[0] == 403)
check("المالك يغيّر الرابط العام", owner.call("POST", "/api/admin/settings", {"public_url": "https://my-host.example.com"})[0] == 200
      and gateway.site_url("abc-1234")[0] == "https://my-host.example.com/s/abc-1234/")
check("رابط عام غير صالح", owner.call("POST", "/api/admin/settings", {"public_url": "javascript:alert(1)"})[0] == 400)
st, j, _, _ = owner.call("GET", "/api/admin/system")
check("حالة النظام", st == 200 and "cpu" in j["stats"] and j["accounts"] >= 2, j)
st, j, _, _ = owner.call("GET", "/api/admin/audit")
actions = {r["action"] for r in j["rows"]}
check("سجل العمليات", {"login", "account_create", "project_create"} <= actions and "login_failed" in actions, actions)
st, j, _, _ = owner.call("POST", "/api/password", {"old": "OwnerPass123", "new": "short"})
check("كلمة مرور جديدة قصيرة مرفوضة", st == 400)
check("تغيير كلمة المرور", owner.call("POST", "/api/password", {"old": "OwnerPass123", "new": "NewOwnerPass99"})[0] == 200 and S().login("boss", "NewOwnerPass99")[0] == 200)
check("الخروج", owner.call("POST", "/api/logout")[0] == 200 and owner.call("GET", "/api/me")[0] == 401)
check("/health ما زال يعمل", anon.call("GET", "/health")[0] == 200)
H.finish()
