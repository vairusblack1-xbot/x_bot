# -*- coding: utf-8 -*-
"""
لوحة الويب — موقع إدارة الاستضافة (مثل HostBot لكن أقوى):
- الحسابات تُنشأ من المالك/المشرفين فقط (لا تسجيل عام).
- جلسات آمنة (كوكي HttpOnly + CSRF) وكلمات مرور PBKDF2 وحماية من تخمين كلمة المرور.
- مشاريع: رفع (ملف/ZIP)، تشغيل/إيقاف/إعادة، سجل حي، ملفات + محرر، طرفية، .env، تحليل.
- لوحة المالك/المشرف: الحسابات، كل المشاريع، موارد النظام، سجل العمليات، الإعدادات.
تعمل فوق بوابة الويب نفسها (نفس المنفذ)، بدون أي خدمة خارجية.
"""
import hashlib
import hmac
import html as _html
import json
import os
import re
import secrets
import shutil
import threading
import time
import urllib.parse

C = None
G = None  # gateway
_HERE = os.path.dirname(os.path.abspath(__file__))
SESSION_SECS = 7 * 86400
PBKDF_ITERS = 150_000
_fails: dict = {}
_fails_lock = threading.Lock()
_busy: set = set()
_results: dict = {}
_disk_cache: dict = {}
_html_cache = {"mtime": 0, "data": b""}


class ApiError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status, self.msg = status, msg


# ============================================================ قاعدة البيانات
def init_schema():
    C.db_execute(
        "CREATE TABLE IF NOT EXISTS web_accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE COLLATE NOCASE,"
        "pass_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', tg_id INTEGER, user_id INTEGER NOT NULL DEFAULT 0,"
        "max_projects INTEGER NOT NULL DEFAULT 3, disabled INTEGER NOT NULL DEFAULT 0, created_by TEXT, note TEXT,"
        "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, last_login TIMESTAMP)")
    C.db_execute(
        "CREATE TABLE IF NOT EXISTS web_sessions (token_hash TEXT PRIMARY KEY, account_id INTEGER NOT NULL, csrf TEXT NOT NULL,"
        "expires INTEGER NOT NULL, ip TEXT, created INTEGER NOT NULL)")
    C.db_execute(
        "CREATE TABLE IF NOT EXISTS web_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        "account TEXT, action TEXT, detail TEXT)")


def audit(who, action, detail=""):
    try:
        C.db_execute("INSERT INTO web_audit (account, action, detail) VALUES (?,?,?)", (who, action, (detail or "")[:300]))
        C.db_execute("DELETE FROM web_audit WHERE id < (SELECT MAX(id) FROM web_audit) - 2000")
    except Exception:
        pass


# ============================================================ كلمات المرور والحسابات
def hash_pw(pw: str) -> str:
    salt = secrets.token_hex(8)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), PBKDF_ITERS).hex()
    return f"pbkdf2${PBKDF_ITERS}${salt}${dk}"


def check_pw(pw: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), int(it)).hex()
        return hmac.compare_digest(got, dk)
    except Exception:
        return False


def gen_password() -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def create_account(username, password, role="user", tg_id=None, max_projects=3, note="", created_by="system") -> dict:
    username = (username or "").strip()
    if not re.match(r"^[A-Za-z0-9_.-]{3,32}$", username):
        raise ApiError(400, "اسم المستخدم: 3-32 حرفاً إنجليزياً/أرقام/._-")
    if C.db_fetchone("SELECT 1 AS x FROM web_accounts WHERE username=?", (username,)):
        raise ApiError(409, "اسم المستخدم مستخدم بالفعل")
    password = password or gen_password()
    if len(password) < 8:
        raise ApiError(400, "كلمة المرور 8 أحرف على الأقل")
    if role not in ("owner", "admin", "user"):
        raise ApiError(400, "دور غير صالح")
    try:
        tg_id = int(tg_id) if tg_id not in (None, "", 0) else None
    except (TypeError, ValueError):
        raise ApiError(400, "معرّف تيليجرام يجب أن يكون رقماً")
    aid = C.db_execute_returning_id(
        "INSERT INTO web_accounts (username, pass_hash, role, tg_id, user_id, max_projects, note, created_by) VALUES (?,?,?,?,0,?,?,?)",
        (username, hash_pw(password), role, tg_id, int(max_projects), (note or "")[:200], created_by))
    uid = tg_id if tg_id else -aid
    C.db_execute("UPDATE web_accounts SET user_id=? WHERE id=?", (uid, aid))
    C.db_execute("INSERT OR IGNORE INTO users (id, first_name, username, approved, max_bots) VALUES (?,?,?,1,?)",
                 (uid, username, username, max(int(max_projects), 1)))
    return {"id": aid, "username": username, "password": password, "user_id": uid}


def ensure_owner():
    if C.db_fetchone("SELECT 1 AS x FROM web_accounts WHERE role='owner'"):
        return
    user = os.environ.get("OWNER_USERNAME") or "owner"
    pw = os.environ.get("OWNER_PASSWORD") or ""
    generated = not pw
    acc = create_account(user, pw or gen_password(), "owner", C.ADMIN_ID, 999, "المالك", "system") if True else None
    if generated:
        # نضع كلمة مرور مولّدة ونُبلغ المالك على تيليجرام + السجل
        newpw = gen_password()
        C.db_execute("UPDATE web_accounts SET pass_hash=? WHERE id=?", (hash_pw(newpw), acc["id"]))
        C.log.warning("Web panel owner created: username=%s password=%s (غيّرها بعد الدخول)", user, newpw)
        try:
            C.bot.send_message(C.ADMIN_ID, f"🔐 <b>لوحة الويب جاهزة</b>\nالمستخدم: <code>{user}</code>\nكلمة المرور: <code>{newpw}</code>\n"
                                           "غيّرها بعد أول دخول. لاسترجاعها لاحقاً: /webpass")
        except Exception:
            pass


# ============================================================ الجلسات
def _cookie(h, name):
    for part in (h.headers.get("Cookie") or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""


def _secure(h) -> bool:
    return (h.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip() == "https" or G.public_base()[0].startswith("https")


def auth(h):
    tok = _cookie(h, "fxs")
    if not tok:
        return None
    th = hashlib.sha256(tok.encode()).hexdigest()
    row = C.db_fetchone(
        "SELECT s.token_hash, s.csrf, s.expires, a.id AS aid, a.username, a.role, a.user_id, a.disabled, a.max_projects, a.tg_id "
        "FROM web_sessions s JOIN web_accounts a ON a.id=s.account_id WHERE s.token_hash=?", (th,))
    now = int(time.time())
    if not row or row["expires"] < now or row["disabled"]:
        return None
    if row["expires"] - now < SESSION_SECS - 3600:
        C.db_execute("UPDATE web_sessions SET expires=? WHERE token_hash=?", (now + SESSION_SECS, th))
    return row


def _client_ip(h):
    xf = h.headers.get("X-Forwarded-For", "")
    return (xf.split(",")[0].strip() if xf else h.client_address[0]) or "?"


def login(h, data):
    username = str(data.get("username") or "").strip()
    pw = str(data.get("password") or "")
    ip = _client_ip(h)
    keys = [f"{ip}|{username.lower()}", f"ip|{ip}"]
    now = time.time()
    with _fails_lock:
        for k in keys:
            cnt, first = _fails.get(k, (0, now))
            if now - first > 600:
                _fails.pop(k, None)
                continue
            if cnt >= (5 if "|" in k and not k.startswith("ip|") else 25):
                raise ApiError(429, "محاولات كثيرة. حاول بعد 10 دقائق.")
    acc = C.db_fetchone("SELECT * FROM web_accounts WHERE username=?", (username,))
    ok = bool(acc) and not acc["disabled"] and check_pw(pw, acc["pass_hash"])
    if not acc:
        check_pw(pw, "pbkdf2$%d$00$00" % PBKDF_ITERS)  # توحيد زمن الاستجابة
    if not ok:
        with _fails_lock:
            for k in keys:
                cnt, first = _fails.get(k, (0, now))
                _fails[k] = (cnt + 1, first if cnt else now)
        audit(username[:40], "login_failed", ip)
        raise ApiError(401, "بيانات الدخول غير صحيحة" if not (acc and acc["disabled"]) else "الحساب معطّل")
    with _fails_lock:
        for k in keys:
            _fails.pop(k, None)
    tok, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(16)
    t = int(time.time())
    C.db_execute("INSERT INTO web_sessions (token_hash, account_id, csrf, expires, ip, created) VALUES (?,?,?,?,?,?)",
                 (hashlib.sha256(tok.encode()).hexdigest(), acc["id"], csrf, t + SESSION_SECS, ip, t))
    C.db_execute("DELETE FROM web_sessions WHERE expires < ?", (t,))
    C.db_execute("UPDATE web_accounts SET last_login=CURRENT_TIMESTAMP WHERE id=?", (acc["id"],))
    audit(username, "login", ip)
    cookie = f"fxs={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_SECS}" + ("; Secure" if _secure(h) else "")
    return {"user": _pub(acc), "csrf": csrf}, {"Set-Cookie": cookie}


def _pub(a):
    return {"id": a["id"] if "id" in a else a.get("aid"), "username": a["username"], "role": a["role"], "tg_id": a.get("tg_id")}


# ============================================================ المشاريع
def _disk_mb(pid):
    c = _disk_cache.get(pid)
    if c and time.time() - c[1] < 120:
        return c[0]
    total = 0
    for root, _, files in os.walk(os.path.join(C.PROJECTS_DIR, str(pid))):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    v = round(total / 1048576, 1)
    _disk_cache[pid] = (v, time.time())
    return v


def _is_staff(a):
    return a["role"] in ("owner", "admin")


def get_project(a, pid, owner_only=False):
    p = C.db_fetchone("SELECT * FROM projects WHERE id=?", (pid,))
    if not p or not (p["user_id"] == a["user_id"] or _is_staff(a)):
        raise ApiError(404, "المشروع غير موجود")
    return p


def proj_json(p, full=False):
    pid = p["id"]
    st = C.manager.status(pid)
    site = C.db_fetchone("SELECT slug, kind, hits, public FROM web_sites WHERE project_id=?", (pid,))
    out = {"id": pid, "name": p["name"], "main_file": p.get("main_file") or "", "runtime": C.detect_runtime_from_file(p.get("main_file") or "") if p.get("main_file") else (p.get("runtime") or "python"),
           "running": bool(st.get("running")), "busy": pid in _busy, "last_error": p.get("last_error") or ""}
    if site:
        out["url"] = G.site_url(site["slug"])[0]
        out.update(slug=site["slug"], hits=site["hits"], public=bool(site["public"]))
    if full:
        files = C.db_fetchall("SELECT filename FROM project_files WHERE project_id=? ORDER BY filename", (pid,))
        env = C.db_fetchone("SELECT content FROM project_files WHERE project_id=? AND filename='.env'", (pid,))
        out.update(status=st, disk_mb=_disk_mb(pid), files=[f["filename"] for f in files],
                   env=bytes(env["content"]).decode("utf-8", "replace") if env else "")
    return out


def _async(pid, fn):
    if pid in _busy:
        raise ApiError(409, "هناك عملية جارية على هذا المشروع")
    _busy.add(pid)

    def run():
        try:
            _results[pid] = (*fn(), time.time())
        except Exception as e:  # noqa
            C.log.exception("panel action")
            _results[pid] = (False, str(e)[:200], time.time())
        finally:
            _busy.discard(pid)
    threading.Thread(target=run, daemon=True, name=f"panel-{pid}").start()


def create_project(a, name, filename, raw, start=True):
    name = re.sub(r"[^\w .-]", "", name or "", flags=re.UNICODE).strip()[:40] or "project"
    if a["role"] == "user":
        cnt = (C.db_fetchone("SELECT COUNT(*) AS c FROM projects WHERE user_id=?", (a["user_id"],)) or {}).get("c", 0)
        if cnt >= a["max_projects"]:
            raise ApiError(403, f"وصلت للحد الأقصى من المشاريع ({a['max_projects']}). اطلب زيادته من المشرف.")
    if not raw:
        raise ApiError(400, "الملف فارغ")
    if len(raw) > 60 * 1024 * 1024:
        raise ApiError(413, "الملف أكبر من 60MB")
    fn = os.path.basename(filename or "file").strip()
    low = fn.lower()
    pid = C.db_execute_returning_id(
        "INSERT INTO projects (user_id, name, main_file, approved, energy_exempt) VALUES (?,?,?,1,1)", (a["user_id"], name, ""))
    try:
        if low.endswith(".zip"):
            main, rt, n, notes = C.store_project_from_zip(pid, raw)
        else:
            if not low.endswith((".py", ".js", ".mjs", ".cjs", ".ts", ".html", ".htm")):
                raise ApiError(400, "النوع غير مدعوم. ارفع .py أو .js أو .html أو .zip")
            safe = C._safe_rel(fn)
            C.store_project_files(pid, {safe: raw})
            main, rt = safe, C.detect_runtime_from_file(safe)
        C.db_execute("UPDATE projects SET main_file=?, runtime=? WHERE id=?", (main, rt, pid))
    except ApiError:
        _delete_project(pid)
        raise
    except ValueError as e:
        _delete_project(pid)
        raise ApiError(400, str(e))
    issues = [re.sub(r"<[^>]+>", "", _html.unescape(i)) for i in C.static_check_project(pid)]
    audit(a["username"], "project_create", f"#{pid} {name}")
    if start:
        _async(pid, lambda: C.manager.start_project(pid))
    return pid, issues


def _delete_project(pid):
    try:
        C.manager.stop_project(pid)
    except Exception:
        pass
    C.manager.processes.pop(pid, None)
    shutil.rmtree(os.path.join(C.PROJECTS_DIR, str(pid)), ignore_errors=True)
    for q in ("DELETE FROM web_sites WHERE project_id=?", "DELETE FROM project_files WHERE project_id=?", "DELETE FROM projects WHERE id=?"):
        try:
            C.db_execute(q, (pid,))
        except Exception:
            pass
    if G:
        G._invalidate()


# ============================================================ طلبات HTTP
def _body(h, limit):
    n = int(h.headers.get("Content-Length") or 0)
    if n > limit:
        h.close_connection = True
        raise ApiError(413, "الحجم أكبر من المسموح")
    buf, left = [], n
    while left > 0:
        c = h.rfile.read(min(65536, left))
        if not c:
            break
        buf.append(c)
        left -= len(c)
    return b"".join(buf)


def _json_body(h):
    raw = _body(h, 1024 * 1024)
    if not raw:
        return {}
    try:
        d = json.loads(raw.decode("utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        raise ApiError(400, "JSON غير صالح")


def _jr(h, obj, status=200, extra=None, head=False):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    ex = {"Cache-Control": "no-store", "X-Frame-Options": "DENY"}
    ex.update(extra or {})
    h._send(status, body, "application/json; charset=utf-8", extra=ex, head=head)


def _page(h, head):
    path = os.path.join(_HERE, "panel.html")
    try:
        m = os.path.getmtime(path)
        if m != _html_cache["mtime"]:
            _html_cache.update(mtime=m, data=open(path, "rb").read())
    except OSError:
        return h._err(500, "ملف اللوحة مفقود", "panel.html غير موجود بجوار البرنامج.", "🛠", head)
    h._send(200, _html_cache["data"], "text/html; charset=utf-8", head=head, extra={
        "Cache-Control": "no-cache", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin",
        "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"})


def handle(h, path, head=False) -> bool:
    """يرجع True إن كان الطلب للوحة."""
    if path in ("/", "/login", "/app", "/panel") and h.command in ("GET", "HEAD"):
        _page(h, head)
        return True
    if path == "/favicon.ico":
        h._send(204, b"", head=head)
        return True
    if not path.startswith("/api/"):
        return False
    try:
        out, extra = api(h, h.command, urllib.parse.urlsplit(h.path))
        _jr(h, out, 200, extra, head)
    except ApiError as e:
        _jr(h, {"error": e.msg}, e.status)
    except Exception:
        C.log.exception("panel api")
        _jr(h, {"error": "خطأ داخلي"}, 500)
    return True


def api(h, method, sp):
    path = sp.path
    q = {k: v[0] for k, v in urllib.parse.parse_qs(sp.query).items()}
    if path == "/api/login" and method == "POST":
        return login(h, _json_body(h))
    a = auth(h)
    if not a:
        h.close_connection = True
        raise ApiError(401, "غير مسجّل الدخول")
    if method != "GET" and not hmac.compare_digest(h.headers.get("X-CSRF", ""), a["csrf"]):
        h.close_connection = True
        raise ApiError(403, "رمز الحماية غير صالح — أعد تحميل الصفحة")
    if path == "/api/me":
        return {"user": _pub(a), "csrf": a["csrf"]}, None
    if path == "/api/logout" and method == "POST":
        C.db_execute("DELETE FROM web_sessions WHERE token_hash=?", (a["token_hash"],))
        return {"ok": True}, {"Set-Cookie": "fxs=; Path=/; Max-Age=0; HttpOnly"}
    if path == "/api/password" and method == "POST":
        d = _json_body(h)
        acc = C.db_fetchone("SELECT pass_hash FROM web_accounts WHERE id=?", (a["aid"],))
        if not check_pw(str(d.get("old") or ""), acc["pass_hash"]):
            raise ApiError(403, "كلمة المرور الحالية غير صحيحة")
        if len(str(d.get("new") or "")) < 8:
            raise ApiError(400, "كلمة المرور الجديدة 8 أحرف على الأقل")
        C.db_execute("UPDATE web_accounts SET pass_hash=? WHERE id=?", (hash_pw(d["new"]), a["aid"]))
        C.db_execute("DELETE FROM web_sessions WHERE account_id=? AND token_hash<>?", (a["aid"], a["token_hash"]))
        audit(a["username"], "password_change")
        return {"ok": True}, None
    if path.startswith("/api/admin/"):
        if not _is_staff(a):
            raise ApiError(403, "للمشرفين فقط")
        return admin_api(h, method, path, q, a), None
    if path == "/api/projects" and method == "GET":
        if q.get("all") and _is_staff(a):
            rows = C.db_fetchall("SELECT p.*, COALESCE(w.username, u.first_name, '?') AS owner FROM projects p LEFT JOIN web_accounts w ON w.user_id=p.user_id "
                                 "LEFT JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT 500")
            return {"projects": [dict(proj_json(r), owner=r["owner"]) for r in rows]}, None
        rows = C.db_fetchall("SELECT * FROM projects WHERE user_id=? ORDER BY id DESC", (a["user_id"],))
        return {"projects": [proj_json(r) for r in rows]}, None
    if path == "/api/projects/upload" and method == "POST":
        fname = urllib.parse.unquote(h.headers.get("X-Filename", "file"))
        raw = _body(h, 61 * 1024 * 1024)
        pid, issues = create_project(a, q.get("name", ""), fname, raw, q.get("start") == "1")
        return {"id": pid, "issues": issues}, None
    m = re.match(r"^/api/projects/(\d+)(?:/(\w+))?$", path)
    if not m:
        raise ApiError(404, "غير موجود")
    pid, sub = int(m.group(1)), m.group(2)
    p = get_project(a, pid)
    if sub is None:
        if method == "GET":
            r = proj_json(p, True)
            res = _results.get(pid)
            if res and time.time() - res[2] < 30:
                r["last_result"] = {"ok": res[0], "message": res[1]}
            return {"project": r}, None
        if method == "DELETE":
            _delete_project(pid)
            audit(a["username"], "project_delete", f"#{pid} {p['name']}")
            return {"ok": True}, None
    if sub in ("start", "restart") and method == "POST":
        fn = (lambda: C.manager.start_project(pid)) if sub == "start" else (lambda: C.manager.restart_project(pid))
        _async(pid, fn)
        audit(a["username"], f"project_{sub}", f"#{pid}")
        return {"message": "بدأت العملية... قد تستغرق ثوانٍ إن كانت هناك مكتبات للتثبيت"}, None
    if sub == "stop" and method == "POST":
        C.manager.stop_project(pid)
        audit(a["username"], "project_stop", f"#{pid}")
        return {"message": "تم الإيقاف"}, None
    if sub == "logs" and method == "GET":
        return {"log": C.manager.tail_log(pid, min(int(q.get("n") or 8000), 60000))}, None
    if sub == "install" and method == "POST":
        ok, report = C.install_dependencies(pid, True)
        return {"ok": ok, "report": re.sub(r"<[^>]+>", "", _html.unescape(report))}, None
    if sub == "analyze" and method == "GET":
        import analyzer
        return {"report": re.sub(r"<[^>]+>", "", _html.unescape(analyzer.analyze_project(C, pid)))}, None
    if sub == "exec" and method == "POST":
        d = _json_body(h)
        return {"output": C.run_project_terminal_command(pid, str(d.get("cmd") or ""), 60, a["user_id"])}, None
    if sub == "files" and method == "GET":
        rows = C.db_fetchall("SELECT filename, size_bytes FROM project_files WHERE project_id=? ORDER BY filename", (pid,))
        return {"files": [{"name": r["filename"], "size": r["size_bytes"]} for r in rows]}, None
    if sub in ("file", "upload"):
        name = C._safe_rel(q.get("name", ""))
        if not name:
            raise ApiError(400, "اسم الملف غير صالح")
        if sub == "file" and method == "GET":
            r = C.db_fetchone("SELECT content, size_bytes FROM project_files WHERE project_id=? AND filename=?", (pid, name))
            if not r:
                raise ApiError(404, "الملف غير موجود")
            if r["size_bytes"] > 300_000:
                raise ApiError(400, "الملف كبير للعرض")
            try:
                return {"content": bytes(r["content"]).decode("utf-8")}, None
            except UnicodeDecodeError:
                raise ApiError(400, "ملف ثنائي لا يمكن عرضه")
        if sub == "file" and method == "PUT":
            C.store_project_files(pid, {name: _body(h, 1024 * 1024)})
            audit(a["username"], "file_edit", f"#{pid} {name}")
            return {"ok": True}, None
        if sub == "file" and method == "DELETE":
            C.db_execute("DELETE FROM project_files WHERE project_id=? AND filename=?", (pid, name))
            return {"ok": True}, None
        if sub == "upload" and method == "POST":
            raw = _body(h, 61 * 1024 * 1024)
            if name.lower().endswith(".zip"):
                files, _ = C.extract_zip_safe(raw)
                C.store_project_files(pid, files)
            else:
                C.store_project_files(pid, {name: raw})
            return {"ok": True}, None
    if sub == "settings" and method == "PUT":
        d = _json_body(h)
        if "env" in d:
            env = str(d["env"])
            if env.strip():
                C.store_project_files(pid, {".env": env.encode("utf-8")})
            else:
                C.db_execute("DELETE FROM project_files WHERE project_id=? AND filename='.env'", (pid,))
        mf = d.get("main_file")
        if mf and mf != p.get("main_file"):
            if not C.db_fetchone("SELECT 1 AS x FROM project_files WHERE project_id=? AND filename=?", (pid, mf)):
                raise ApiError(400, "الملف الرئيسي غير موجود")
            C.db_execute("UPDATE projects SET main_file=?, runtime=? WHERE id=?", (mf, C.detect_runtime_from_file(mf), pid))
        site = C.db_fetchone("SELECT slug FROM web_sites WHERE project_id=?", (pid,))
        if site:
            if d.get("slug") and d["slug"] != site["slug"]:
                ok, msg = G.set_slug(pid, str(d["slug"]).lower())
                if not ok:
                    raise ApiError(400, msg)
            if d.get("public") is not None:
                C.db_execute("UPDATE web_sites SET public=? WHERE project_id=?", (1 if d["public"] else 0, pid))
                G._invalidate()
        audit(a["username"], "project_settings", f"#{pid}")
        return {"ok": True}, None
    raise ApiError(404, "غير موجود")


# ============================================================ واجهات الإدارة
def _manageable(actor, acc):
    if acc["role"] == "owner":
        return False
    return actor["role"] == "owner" or acc["role"] == "user"


def admin_api(h, method, path, q, a):
    if path == "/api/admin/accounts":
        if method == "GET":
            rows = C.db_fetchall("SELECT * FROM web_accounts ORDER BY id")
            out = []
            for r in rows:
                cnt = (C.db_fetchone("SELECT COUNT(*) AS c FROM projects WHERE user_id=?", (r["user_id"],)) or {}).get("c", 0)
                out.append({"id": r["id"], "username": r["username"], "role": r["role"], "tg_id": r["tg_id"], "disabled": r["disabled"],
                            "max_projects": r["max_projects"], "projects": cnt, "last_login": r["last_login"], "manageable": _manageable(a, r)})
            return {"accounts": out}
        if method == "POST":
            d = _json_body(h)
            role = d.get("role", "user")
            if role == "owner" or (role == "admin" and a["role"] != "owner"):
                raise ApiError(403, "لا تملك صلاحية إنشاء هذا الدور")
            acc = create_account(d.get("username"), d.get("password"), role, d.get("tg_id"), int(d.get("max_projects") or 3), d.get("note", ""), a["username"])
            audit(a["username"], "account_create", f"{acc['username']} ({role})")
            return {"username": acc["username"], "password": acc["password"]}
    m = re.match(r"^/api/admin/accounts/(\d+)$", path)
    if m:
        acc = C.db_fetchone("SELECT * FROM web_accounts WHERE id=?", (int(m.group(1)),))
        if not acc or not _manageable(a, acc):
            raise ApiError(403, "لا تملك صلاحية على هذا الحساب")
        if method == "PATCH":
            d = _json_body(h)
            if d.get("toggle"):
                C.db_execute("UPDATE web_accounts SET disabled=? WHERE id=?", (0 if acc["disabled"] else 1, acc["id"]))
                C.db_execute("DELETE FROM web_sessions WHERE account_id=?", (acc["id"],))
                audit(a["username"], "account_toggle", acc["username"])
            if "max_projects" in d:
                C.db_execute("UPDATE web_accounts SET max_projects=? WHERE id=?", (max(0, int(d["max_projects"])), acc["id"]))
            if d.get("reset"):
                pw = gen_password()
                C.db_execute("UPDATE web_accounts SET pass_hash=? WHERE id=?", (hash_pw(pw), acc["id"]))
                C.db_execute("DELETE FROM web_sessions WHERE account_id=?", (acc["id"],))
                audit(a["username"], "account_reset", acc["username"])
                return {"username": acc["username"], "password": pw}
            return {"ok": True}
        if method == "DELETE":
            if acc["user_id"] < 0:  # حساب ويب فقط: نحذف مشاريعه
                for r in C.db_fetchall("SELECT id FROM projects WHERE user_id=?", (acc["user_id"],)):
                    _delete_project(r["id"])
            C.db_execute("DELETE FROM web_sessions WHERE account_id=?", (acc["id"],))
            C.db_execute("DELETE FROM web_accounts WHERE id=?", (acc["id"],))
            audit(a["username"], "account_delete", acc["username"])
            return {"ok": True}
    if path == "/api/admin/system" and method == "GET":
        import monitor
        try:
            stats = monitor.sample() if monitor.C else {"cpu": 0.0, "ram_used": 0.0, "ram_total": 0.0, "disk_free": 0.0, "disk_total": 0.0}
        except Exception:
            stats = {"cpu": 0.0, "ram_used": 0.0, "ram_total": 0.0, "disk_free": 0.0, "disk_total": 0.0}
        cnt = lambda q_: (C.db_fetchone(q_) or {}).get("c", 0)
        return {"stats": stats, "projects": cnt("SELECT COUNT(*) AS c FROM projects"),
                "running": sum(1 for hp in list(C.manager.processes.values()) if hp.is_alive()),
                "accounts": cnt("SELECT COUNT(*) AS c FROM web_accounts"), "requests": G._gateway["total"],
                "public_url": G.public_base()[0], "public_url_setting": C.get_setting("public_url") or ""}
    if path == "/api/admin/audit" and method == "GET":
        return {"rows": C.db_fetchall("SELECT ts, account, action, detail FROM web_audit ORDER BY id DESC LIMIT 200")}
    if path == "/api/admin/settings" and method == "POST":
        if a["role"] != "owner":
            raise ApiError(403, "للمالك فقط")
        d = _json_body(h)
        u = str(d.get("public_url") or "").strip().rstrip("/")
        if u and not re.match(r"^https?://[A-Za-z0-9._:-]+$", u):
            raise ApiError(400, "رابط غير صالح. مثال: https://my-app.onrender.com")
        C.set_setting("public_url", u)
        C.db_execute("UPDATE web_sites SET announced_url=NULL")
        G._invalidate()
        audit(a["username"], "set_public_url", u)
        return {"ok": True}
    raise ApiError(404, "غير موجود")


# ============================================================ أوامر تيليجرام للمالك
def register_commands():
    bot = C.bot

    def owner_only(m):
        return m.from_user.id == C.ADMIN_ID

    @bot.message_handler(commands=["web", "panel"])
    def cmd_web(m):
        if C.msg_seen(m):
            return
        bot.send_message(m.chat.id, f"🌐 <b>لوحة الويب</b>\n{C.html_escape(G.public_base()[0])}\n"
                                    "الدخول بحساب يُنشئه لك المالك/المشرف. اطلب حسابك منهم.")

    @bot.message_handler(commands=["webpass"])
    def cmd_webpass(m):
        if C.msg_seen(m) or not owner_only(m):
            return
        acc = C.db_fetchone("SELECT id, username FROM web_accounts WHERE role='owner' ORDER BY id LIMIT 1")
        if not acc:
            return
        pw = gen_password()
        C.db_execute("UPDATE web_accounts SET pass_hash=?, disabled=0 WHERE id=?", (hash_pw(pw), acc["id"]))
        C.db_execute("DELETE FROM web_sessions WHERE account_id=?", (acc["id"],))
        base = G.public_base()[0]
        bot.send_message(m.chat.id, f"🔐 <b>لوحة الويب</b>\n{C.html_escape(base)}\nالمستخدم: <code>{acc['username']}</code>\nكلمة المرور: <code>{pw}</code>")

    @bot.message_handler(commands=["webadd"])
    def cmd_webadd(m):
        if C.msg_seen(m) or not owner_only(m):
            return
        a = (m.text or "").split()
        if len(a) < 2:
            return bot.send_message(m.chat.id, "الاستخدام: <code>/webadd اسم_المستخدم [admin|user] [عدد_المشاريع]</code>")
        try:
            role = a[2] if len(a) > 2 and a[2] in ("admin", "user") else "user"
            mx = int(a[3]) if len(a) > 3 else 3
            acc = create_account(a[1], None, role, None, mx, "", "telegram-owner")
        except ApiError as e:
            return bot.send_message(m.chat.id, f"❌ {e.msg}")
        audit("telegram-owner", "account_create", f"{a[1]} ({role})")
        bot.send_message(m.chat.id, f"✅ تم إنشاء الحساب\n{C.html_escape(G.public_base()[0])}\nالمستخدم: <code>{acc['username']}</code>\nكلمة المرور: <code>{acc['password']}</code>")

    @bot.message_handler(commands=["webusers"])
    def cmd_webusers(m):
        if C.msg_seen(m) or not owner_only(m):
            return
        rows = C.db_fetchall("SELECT username, role, disabled FROM web_accounts ORDER BY id")
        bot.send_message(m.chat.id, "👥 <b>حسابات الويب</b>\n" + "\n".join(
            f"{'🔴' if r['disabled'] else '🟢'} <code>{r['username']}</code> · {r['role']}" for r in rows))


def install(core, gateway):
    global C, G
    C, G = core, gateway
    init_schema()
    ensure_owner()
    orig_root = gateway.Handler._root

    def _root(self, path, head=False):
        if handle(self, path, head):
            return
        orig_root(self, path, head)

    gateway.Handler._root = _root
    register_commands()
    core.log.info("Web panel installed")
