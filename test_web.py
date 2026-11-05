import http.client, io, json, os, socket, sys, threading, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import T, free_port
H = T(); m = H.m; check = H.check; mk = H.mk
import gateway, diagnostics, monitor, analyzer
SENT = []
m.bot.send_message = lambda *a, **k: SENT.append((a, k))
gateway.install(m)
m.KEEP_ALIVE_PORT = H.gw_port
gateway.start_gateway(); time.sleep(0.5)
GP = H.gw_port


def req(method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", GP, timeout=20)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse(); data = r.read()
    hd = {k.lower(): v for k, v in r.getheaders()}
    c.close()
    return r.status, hd, data


def wait_site(pid, secs=40):
    end = time.time() + secs
    while time.time() < end:
        row = m.db_fetchone("SELECT * FROM web_sites WHERE project_id=?", (pid,))
        if row: return row
        time.sleep(0.5)
    return None


# ---------- أساسيات ----------
st, hd, body = req("GET", "/health")
check("/health يعمل", st == 200 and json.loads(body)["status"] == "ok")
st, _, body = req("GET", "/")
check("الصفحة الرئيسية", st == 200 and "Cloud".encode() in body)
st, _, body = req("GET", "/s/nope-1234/")
check("موقع غير موجود → 404 بالعربي", st == 404 and "الموقع غير موجود".encode() in body)

# ---------- موقع ثابت ----------
html = '<html><head><title>t</title><link rel="stylesheet" href="/style.css"></head><body>static-home<img src="logo.png"></body></html>'
ps = mk("My Static", {"index.html": html, "style.css": "body{color:red}", "logo.png": b"\x89PNG0123456789",
                      "sub/index.html": "sub-home", "404.html": "custom-404", ".env": "SECRET=1", "data.db": b"x"}, "index.html")
ok, msg = m.manager.start_project(ps)
check("نشر موقع ثابت", ok, msg)
row = wait_site(ps, 5)
check("تسجيل رابط للموقع الثابت", row and row["kind"] == "static", row)
slug = row["slug"]; P = f"/s/{slug}"
st, hd, body = req("GET", P + "/")
check("الصفحة الرئيسية للموقع الثابت", st == 200 and b"static-home" in body and "text/html" in hd["content-type"])
st, hd, _ = req("GET", P)
check("إعادة توجيه بدون شرطة", st == 301 and hd["location"] == P + "/")
st, hd, body = req("GET", P + "/style.css")
check("CSS بنوع صحيح", st == 200 and "text/css" in hd["content-type"])
st, _, body = req("GET", P + "/sub/")
check("مجلد فرعي index", st == 200 and body == b"sub-home")
st, hd, _ = req("GET", P + "/sub")
check("مجلد بدون شرطة → 301", st == 301)
st, _, body = req("GET", P + "/nothing.html")
check("404 مخصصة", st == 404 and body == b"custom-404")
st, _, _ = req("GET", P + "/.env")
check("منع .env", st == 404)
st, _, _ = req("GET", P + "/data.db")
check("منع .db", st == 404)
st, _, _ = req("GET", P + "/..%2f..%2f..%2fetc/passwd")
check("منع اجتياز المسار %2f", st == 404)
st, _, _ = req("GET", P + "/%2e%2e/%2e%2e/etc/passwd")
check("منع اجتياز المسار %2e%2e", st == 404)
st, hd, body = req("GET", P + "/logo.png", headers={"Range": "bytes=0-3"})
check("Range → 206", st == 206 and body == b"\x89PNG" and hd["content-range"].startswith("bytes 0-3/"))
st, hd, _ = req("GET", P + "/logo.png")
etag = hd["etag"]
st, _, _ = req("GET", P + "/logo.png", headers={"If-None-Match": etag})
check("ETag → 304", st == 304)
st, hd, body = req("HEAD", P + "/style.css")
check("HEAD بدون جسم", st == 200 and body == b"" and int(hd["content-length"]) == len("body{color:red}"))

# ---------- تطبيق Python (Flask-like عبر http.server) ----------
PYAPP = r'''
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class H(BaseHTTPRequestHandler):
    def _s(self, code, body, ctype="text/html", extra=()):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        for k, v in extra: self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        p = self.path
        if p == "/": self._s(200, b'<html><head></head><body><a href="/about">a</a><img src="/img.png"><form action="/post"></form></body></html>')
        elif p == "/redir": self._s(302, b"", extra=[("Location", "/about")])
        elif p == "/about": self._s(200, b"about-page", "text/plain")
        elif p.startswith("/hdr"): self._s(200, (self.headers.get("X-Forwarded-Prefix","") + "|" + self.headers.get("X-Forwarded-Host","")).encode(), "text/plain")
        elif p == "/cookie": self._s(200, b"c", "text/plain", [("Set-Cookie", "a=b; Path=/; HttpOnly")])
        elif p == "/q?x=1&y=2": self._s(200, b"query-ok", "text/plain")
        else: self._s(404, b"nf", "text/plain")
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); d = self.rfile.read(n)
        self._s(200, b"echo:" + d, "text/plain")
    def log_message(self, *a): pass
ThreadingHTTPServer(("127.0.0.1", int(os.environ["PORT"])), H).serve_forever()
'''
pp = mk("pyweb", {"app.py": PYAPP}, "app.py")
ok, msg = m.manager.start_project(pp)
check("تشغيل تطبيق Python ويب", ok, msg)
row = wait_site(pp)
check("اكتشاف تطبيق الويب وتسجيل رابط", row and row["kind"] == "app", row)
sp = row["slug"]; PP = f"/s/{sp}"
time.sleep(0.5)
st, hd, body = req("GET", PP + "/")
txt = body.decode()
check("الصفحة تصل عبر البروكسي", st == 200 and "<a href=" in txt)
check("إصلاح الروابط المطلقة (href/src/action)", f'href="{PP}/about"' in txt and f'src="{PP}/img.png"' in txt and f'action="{PP}/post"' in txt, txt)
check("حقن سكربت fetch/XHR", "window.fetch" in txt)
st, hd, _ = req("GET", PP + "/redir")
check("إصلاح Location", st == 302 and hd["location"] == f"{PP}/about", hd)
st, _, body = req("GET", PP + "/hdr")
check("ترويسة X-Forwarded-Prefix", body.decode().startswith(PP + "|"), body)
st, hd, _ = req("GET", PP + "/cookie")
check("إصلاح مسار الكوكي", f"Path={PP}/" in hd["set-cookie"], hd)
st, _, body = req("GET", PP + "/q?x=1&y=2")
check("تمرير query string", body == b"query-ok")
st, _, body = req("POST", PP + "/post", body=b"hello-body", headers={"Content-Type": "text/plain"})
check("POST + جسم الطلب", body == b"echo:hello-body")
big = os.urandom(3 * 1024 * 1024)
st, _, body = req("POST", PP + "/upload", body=big)
check("رفع 3MB عبر البروكسي", body == b"echo:" + big)
st, _, body = req("GET", PP + "/missing")
check("تمرير 404 من التطبيق", st == 404 and body == b"nf")

# خاص / تعطيل الإصلاح
m.db_execute("UPDATE web_sites SET rewrite=0 WHERE project_id=?", (pp,)); gateway._invalidate()
st, _, body = req("GET", PP + "/")
check("تعطيل إعادة كتابة الروابط", b'href="/about"' in body)
m.db_execute("UPDATE web_sites SET rewrite=1, public=0 WHERE project_id=?", (pp,)); gateway._invalidate()
st, _, _ = req("GET", PP + "/")
check("موقع خاص → 403", st == 403)
m.db_execute("UPDATE web_sites SET public=1 WHERE project_id=?", (pp,)); gateway._invalidate()

# تغيير الاسم
ok, msg = gateway.set_slug(pp, "my-new-name")
check("تغيير slug", ok, msg)
st, _, body = req("GET", "/s/my-new-name/about")
check("الاسم الجديد يعمل", st == 200 and body == b"about-page")
st, _, _ = req("GET", PP + "/about")
check("الاسم القديم لا يعمل", st == 404)
check("رفض slug محجوز", not gateway.set_slug(pp, "admin")[0])
check("رفض slug مكرر", not gateway.set_slug(pp, slug)[0])
PP = "/s/my-new-name"

# نطاق فرعي
m.set_setting("public_domain", "example.test"); gateway._invalidate()
st, _, body = req("GET", "/about", headers={"Host": "my-new-name.example.test"})
check("نطاق فرعي: بدون بادئة", st == 200 and body == b"about-page")
st, _, body = req("GET", "/", headers={"Host": f"{slug}.example.test"})
check("نطاق فرعي لموقع ثابت", st == 200 and b"static-home" in body)
url, local = gateway.site_url("my-new-name")
check("الرابط بنطاق فرعي", url == "http://my-new-name.example.test/" or url == "https://my-new-name.example.test/", url)
m.set_setting("public_domain", "")

# إيقاف → 503
m.manager.stop_project(pp); gateway._port_cache.clear(); time.sleep(0.5)
st, _, body = req("GET", PP + "/")
check("مشروع متوقف → 503 بالعربي", st == 503 and "متوقف".encode() in body)
m.manager.stop_project(ps)
st, _, body = req("GET", P + "/")
check("موقع ثابت متوقف → 503", st == 503)
ok, _ = m.manager.start_project(ps)
st, _, body = req("GET", P + "/")
check("إعادة نشر الموقع الثابت", st == 200 and b"static-home" in body)

# ---------- تطبيق بمنفذ ثابت (لا يستخدم PORT) ----------
hp_port = free_port()
HARD = f'''
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        b = b"hardcoded-ok"; self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
HTTPServer(("0.0.0.0", {hp_port}), H).serve_forever()
'''
ph = mk("hard", {"main.py": HARD}, "main.py")
ok, msg = m.manager.start_project(ph)
row = wait_site(ph)
check("اكتشاف منفذ ثابت داخل الكود", row is not None, msg)
if row:
    time.sleep(0.5)
    st, _, body = req("GET", f"/s/{row['slug']}/")
    check("عمل التطبيق ذو المنفذ الثابت عبر البوابة", body == b"hardcoded-ok", body)
m.manager.stop_project(ph)

# ---------- Node: ويب + WebSocket ----------
if m.node_available():
    NODE = r'''
const http = require('http'); const crypto = require('crypto');
const s = http.createServer((req, res) => {
  if (req.method === 'POST') { let n = 0; req.on('data', d => n += d.length); req.on('end', () => { res.end('len:' + n); }); return; }
  res.setHeader('Content-Type', 'text/html'); res.end('<html><head></head><body><a href="/x">node-ok</a></body></html>');
});
s.on('upgrade', (req, socket) => {
  const key = req.headers['sec-websocket-key'];
  const acc = crypto.createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
  socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + acc + '\r\n\r\n');
  socket.on('data', d => socket.write(d));
});
s.listen(process.env.PORT, '127.0.0.1');
'''
    pn = mk("nodeweb", {"index.js": NODE}, "index.js")
    ok, msg = m.manager.start_project(pn)
    check("تشغيل تطبيق Node ويب", ok, msg)
    row = wait_site(pn)
    check("اكتشاف تطبيق Node", row is not None)
    if row:
        PN = f"/s/{row['slug']}"
        time.sleep(0.5)
        st, _, body = req("GET", PN + "/")
        check("Node عبر البوابة + إصلاح الروابط", b"node-ok" in body and f'href="{PN}/x"'.encode() in body, body)
        st, _, body = req("POST", PN + "/up", body=big)
        check("رفع 3MB إلى Node", body == f"len:{len(big)}".encode(), body)
        s = socket.create_connection(("127.0.0.1", GP), timeout=10)
        s.sendall((f"GET {PN}/ws HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += s.recv(4096)
        check("WebSocket: 101 Switching Protocols", b"101" in buf.split(b"\r\n")[0])
        s.sendall(b"ping-bytes"); echo = s.recv(100)
        check("WebSocket: نفق ثنائي الاتجاه", echo == b"ping-bytes", echo)
        s.close()
    m.manager.stop_project(pn)
else:
    print("⚠️ node غير موجود — تخطي اختبارات Node")

# ---------- ZIP لموقع ثابت ----------
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("site/index.html", "<html>zip-site</html>"); z.writestr("site/script.js", "console.log(1)"); z.writestr("site/css/a.css", "a{}")
pz = mk("zipsite", {"x": "y"}, "x")
main, rt, n, notes = m.store_project_from_zip(pz, buf.getvalue())
check("ZIP موقع ثابت: main=index.html و runtime=static", main == "index.html" and rt == "static" and n == 3, (main, rt, n))

# ---------- الأوامر والأدوات ----------
text, links = gateway.links_text(1)
check("/links يعرض الروابط", "my-new-name" in text and "زيارة" in text)
sent = " ".join(str(c) for c in SENT)
check("إبلاغ المالك بالرابط تلقائياً", "موقعك جاهز" in sent)
gateway._flush_hits()
hits = m.db_fetchone("SELECT hits FROM web_sites WHERE project_id=?", (ps,))["hits"]
check("عدّاد الزيارات يُحفظ", hits > 0, hits)
rep = diagnostics.format_report(diagnostics.run_checks(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), m))
check("diagnostics يعمل", "Python" in rep and "Node" in rep)
monitor.start(m)
check("monitor.sample", monitor.sample()["ram_total"] >= 0)
check("monitor.summary", "موارد السيرفر" in monitor.summary_html())
ra = analyzer.analyze_project(m, pp)
check("analyzer للتطبيق", "تحليل المشروع" in ra and "ويب" in ra, ra)
ra2 = analyzer.analyze_project(m, ps)
check("analyzer للموقع الثابت", "موقع HTML ثابت" in ra2)
H.finish()
