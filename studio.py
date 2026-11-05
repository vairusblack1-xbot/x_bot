# -*- coding: utf-8 -*-
"""
استوديو الستايل (Style Studio) — تغيير شكل البوت كله من تيليجرام أو من ملفات JSON:
  • 11 ستايل جاهز + ستايلات مخصصة من themes.json
  • تحرير أي زر: النص / الأيقونة / اللون / الإخفاء / الترتيب / عدد الأعمدة
  • تخصيص الإطار: الاقتباس، الرموز، الأسهم، الفواصل، شريط التقدم، المؤشرات
  • معاينة حية قبل التطبيق، تراجع، تصدير/استيراد JSON
  • زر «السورس»: فيديو مموّه (Spoiler) + نص اقتباس + أزرار روابط
  • أدوات: عد تنازلي، شاشات متحركة، ترمنال — وإضافات plugin_*.py
المالك فقط (ADMIN_ID). كل شيء محلي بدون أي خدمة خارجية.
"""
import copy
import glob
import hashlib
import html as _html
import importlib.util
import io
import json
import os
import re
import sys
import threading
import time
from contextlib import contextmanager

C = None
_HERE = os.path.dirname(os.path.abspath(__file__))
_tl = threading.local()
_lock = threading.RLock()
_cache = {"cfg": None, "ts": 0.0}
_REG: dict = {}          # callback_data -> {"t": النص الأصلي}
_SCREENS: dict = {}      # مفتاح الشاشة -> {"name":..., "cds":[...]}
_dirty = {"v": False}
_pending: dict = {}
_ctx: dict = {}
_plugins: list = []
_custom_presets: dict = {}

# ============================================================ الخيارات
LABELS = ["{t}", "➤ {t}", "❯ {t}", "▸ {t}", "« {t} »", "⟦ {t} ⟧", "[ {t} ]", "✦ {t} ✦", "• {t}", "{t} ‹", "≋ {t}", "⌁ {t}"]
QUOTES = ["blockquote", "expandable", "bar", "pre", "none"]
BULLETS = ["•", "◆", "▸", "➤", "✦", "◉", "›", "▪"]
DIVIDERS = ["━", "─", "═", "┄", "▬", "✦", "·", "▁"]
ARROWS = ["➤", "❯", "➜", "»", "▸", "⟶", "⇒"]
BARS = ["▰▱", "█░", "■□", "●○", "▮▯", "⣿⣀", "▓░"]
SPINS = ["braille", "dots", "arrows", "moon", "clock", "bounce", "pulse"]
COLORS = ["original", "all_primary", "all_success", "all_danger", "roles", "cycle"]
KNOB_OPTIONS = {"label": LABELS, "quote": QUOTES, "bullet": BULLETS, "divider": DIVIDERS, "arrow": ARROWS,
                "bar": BARS, "spin": SPINS, "colors": COLORS, "cols_main": [0, 1, 2, 3], "strip_emoji": [False, True]}
KNOB_NAMES = {"label": "شكل الأزرار", "quote": "إطار النص", "bullet": "رمز النقاط", "divider": "الفاصل", "arrow": "السهم",
              "bar": "شريط التقدم", "spin": "المؤشر المتحرك", "colors": "ألوان الأزرار", "cols_main": "أعمدة القائمة الرئيسية",
              "strip_emoji": "حذف الإيموجي من الأزرار"}
QUOTE_NAMES = {"blockquote": "اقتباس", "expandable": "اقتباس قابل للطي", "bar": "شريط جانبي", "pre": "صندوق كود", "none": "بدون"}
COLOR_NAMES = {"original": "الأصلي", "all_primary": "أزرق", "all_success": "أخضر", "all_danger": "أحمر", "roles": "ذكي حسب الوظيفة", "cycle": "متدرّج"}
DEFAULT_KNOBS = {"label": "{t}", "quote": "blockquote", "bullet": "•", "divider": "━", "arrow": "➤", "bar": "▰▱", "spin": "braille",
                 "colors": "original", "cols_main": 0, "strip_emoji": False, "header": "", "footer": ""}

PRESETS = {
    "classic": {"name": "🎯 كلاسيك", "knobs": {}},
    "ocean": {"name": "🌊 محيط", "knobs": {"label": "≋ {t}", "bullet": "◦", "bar": "●○", "spin": "moon", "colors": "all_primary", "divider": "┄"}},
    "forest": {"name": "🌲 غابة", "knobs": {"label": "▸ {t}", "bullet": "▪", "bar": "■□", "colors": "all_success", "divider": "─"}},
    "sunset": {"name": "🌅 غروب", "knobs": {"label": "❯ {t}", "bullet": "◆", "bar": "▓░", "spin": "pulse", "colors": "all_danger", "arrow": "❯"}},
    "night": {"name": "🌙 ليلي", "knobs": {"label": "{t} ‹", "bullet": "›", "spin": "moon", "colors": "all_primary", "quote": "bar", "divider": "·"}},
    "gold": {"name": "👑 ذهبي", "knobs": {"label": "✦ {t} ✦", "bullet": "✦", "divider": "═", "colors": "roles", "bar": "█░", "quote": "expandable"}},
    "rose": {"name": "🌹 وردي", "knobs": {"label": "• {t}", "bullet": "◉", "colors": "cycle", "bar": "●○", "spin": "pulse", "arrow": "➜"}},
    "cyber": {"name": "⚡ سايبر", "knobs": {"label": "⟦ {t} ⟧", "bullet": "▸", "bar": "▮▯", "spin": "braille", "colors": "roles", "divider": "▬", "arrow": "⇒", "cols_main": 2}},
    "neon": {"name": "💠 نيون", "knobs": {"label": "⌁ {t}", "bullet": "◆", "bar": "▰▱", "colors": "cycle", "divider": "━", "spin": "dots"}},
    "terminal": {"name": "💻 ترمنال", "knobs": {"label": "[ {t} ]", "bullet": "›", "quote": "pre", "bar": "█░", "spin": "bounce", "colors": "all_success",
                                               "divider": "─", "strip_emoji": True, "arrow": "»", "cols_main": 1}},
    "minimal": {"name": "⚪ بسيط", "knobs": {"label": "{t}", "bullet": "·", "quote": "none", "strip_emoji": True, "divider": "─", "colors": "original", "cols_main": 1}},
}

SPIN_FRAMES = {"braille": list("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"), "dots": ["·  ", "·· ", "···", " ··", "  ·", "   "], "arrows": list("←↖↑↗→↘↓↙"),
               "moon": list("🌑🌒🌓🌔🌕🌖🌗🌘"), "clock": list("🕛🕐🕑🕒🕓🕔🕕🕖🕗🕘🕙🕚"),
               "bounce": ["[=   ]", "[ =  ]", "[  = ]", "[   =]", "[  = ]", "[ =  ]"], "pulse": list("○◔◑◕●◕◑◔")}

DEFAULT_SOURCE = ("<b>📦 عن السورس</b>\n\nاستضافة بوتات ومواقع (Python · Node.js · HTML) مع لوحة تحكم كاملة.\n"
                  "• رفع مشاريع ZIP وتشغيلها تلقائياً\n• روابط للمواقع ولوحة ويب\n• مراقبة 24/7 وإصلاح ذاتي للأخطاء")

_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200d\u2300-\u23FF\u2190-\u21FF\u25A0-\u25FF]+")


def default_cfg():
    return {"preset": "classic", "over": {}, "buttons": {}, "order": {}, "cols": {},
            "custom": [{"id": "source", "text": "📦 السورس", "kind": "source"}],
            "source": {"text": "", "file_id": "", "kind": "", "spoiler": True, "urls": []}}


# ============================================================ التخزين
def cfg():
    now = time.time()
    with _lock:
        if _cache["cfg"] is not None and now - _cache["ts"] < 4:
            return _cache["cfg"]
        try:
            d = json.loads(C.get_setting("ui_cfg") or "{}")
        except Exception:
            d = {}
        base = default_cfg()
        base.update({k: v for k, v in d.items() if k in base})
        _cache.update(cfg=base, ts=now)
        return base


def save_cfg(d, snapshot=True):
    with _lock:
        if snapshot:
            try:
                hist = json.loads(C.get_setting("ui_hist") or "[]")
            except Exception:
                hist = []
            hist.append(C.get_setting("ui_cfg") or "{}")
            C.set_setting("ui_hist", json.dumps(hist[-10:]))
        C.set_setting("ui_cfg", json.dumps(d, ensure_ascii=False))
        _cache.update(cfg=d, ts=time.time())


def all_presets():
    p = dict(PRESETS)
    p.update(_custom_presets)
    return p


def load_custom_presets():
    _custom_presets.clear()
    path = os.path.join(_HERE, "themes.json")
    try:
        data = json.load(open(path, encoding="utf-8"))
        for k, v in (data.get("presets") or data).items():
            if isinstance(v, dict) and isinstance(v.get("knobs"), dict) and re.match(r"^[a-z0-9_]{2,20}$", k) and k not in PRESETS:
                _custom_presets[k] = {"name": str(v.get("name") or k)[:30], "knobs": _clean_knobs(v["knobs"]), "custom": True}
    except FileNotFoundError:
        pass
    except Exception:
        C.log.exception("themes.json")


def _clean_knobs(k):
    out = {}
    for name, val in (k or {}).items():
        if name in KNOB_OPTIONS and val in KNOB_OPTIONS[name]:
            out[name] = val
        elif name in ("header", "footer") and isinstance(val, str):
            out[name] = val[:200]
        elif name == "label" and isinstance(val, str) and "{t}" in val and len(val) <= 30:
            out[name] = val
    return out


@contextmanager
def preview(preset=None, over=None):
    prev = getattr(_tl, "ov", None)
    _tl.ov = {"preset": preset, "over": over or {}}
    try:
        yield
    finally:
        _tl.ov = prev


def knobs():
    ov = getattr(_tl, "ov", None)
    c = cfg()
    pid = (ov or {}).get("preset") or c["preset"]
    k = dict(DEFAULT_KNOBS)
    k.update(all_presets().get(pid, PRESETS["classic"])["knobs"])
    k.update(c["over"] if not ov or ov.get("preset") is None else {})
    if ov:
        k.update(ov.get("over") or {})
    return k


# ============================================================ تحويل الأزرار
_NO_DECOR = {"noop", "noop_sig"}
_DANGER = ("del", "stop", "ban", "reject", "cancel", "remove", "clear", "kill", "block")
_SUCCESS = ("start", "new", "add", "approve", "save", "ok", "upload", "confirm", "install", "run", "restart", "yes", "source")


def _cd_of(btn):
    cd = getattr(btn, "callback_data", None)
    if cd:
        return str(cd)
    url = getattr(btn, "url", None)
    return "u:" + hashlib.sha1(str(url or btn.text).encode()).hexdigest()[:8]


def role_style(cd, orig):
    c = cd.lower()
    if c.startswith(("back", "adm_panel")) or "home" in c:
        return "primary"
    if any(w in c for w in _DANGER):
        return "danger"
    if any(w in c for w in _SUCCESS):
        return "success"
    return orig or "primary"


def decorate_button(btn):
    try:
        cd = _cd_of(btn)
        text = btn.text
        if cd not in _NO_DECOR and not cd.startswith("ui:") or cd in ("ui:source",) or cd.startswith("ui:cb:"):
            if cd not in _REG and len(_REG) < 600:
                _REG[cd] = {"t": text}
                _dirty["v"] = True
        c = cfg()
        ov = c["buttons"].get(cd) or {}
        k = knobs()
        if ov.get("text"):
            text = ov["text"]
        elif k["strip_emoji"] and cd not in _NO_DECOR:
            stripped = _EMOJI_RE.sub("", text).strip()
            text = stripped or text
        if ov.get("icon"):
            text = f"{ov['icon']} {text}"
        if cd not in _NO_DECOR and not ov.get("text"):
            text = k["label"].replace("{t}", text)
        btn.text = text[:60]
        st = ov.get("color")
        cur = btn.__dict__.get("style")
        if st in ("primary", "success", "danger"):
            btn.__dict__["style"] = st
        elif st == "none":
            btn.__dict__.pop("style", None)
        elif k["colors"] in ("all_primary", "all_success", "all_danger") and cd not in _NO_DECOR:
            btn.__dict__["style"] = k["colors"][4:]
        elif k["colors"] == "roles" and cd not in _NO_DECOR:
            btn.__dict__["style"] = role_style(cd, cur)
        if ov.get("hide") and not (cd.startswith("ui:") and cd not in ("ui:source",) and not cd.startswith("ui:cb:")) and cd != "back_main":
            btn.__dict__["_ui_hidden"] = True
    except Exception:
        C.log.exception("decorate_button")


def _screen_name(cds, tag):
    if tag == "main":
        return "القائمة الرئيسية"
    if tag == "admin":
        return "لوحة الأدمن"
    first = next((_REG.get(c, {}).get("t") for c in cds if c in _REG), "شاشة")
    return f"شاشة: {first[:22]}"


def process_markup(markup):
    try:
        types = C.types
        if not isinstance(markup, types.InlineKeyboardMarkup):
            return markup
        rows = list(getattr(markup, "keyboard", []) or [])
        flat = [b for r in rows for b in r]
        if not flat:
            return markup
        cds = [_cd_of(b) for b in flat]
        tag = markup.__dict__.get("_ui_screen")
        key = tag or hashlib.sha1("|".join(sorted(cds)).encode()).hexdigest()[:8]
        if not getattr(_tl, "ov", None):
            scr = _SCREENS.get(key)
            if scr is None and len(_SCREENS) < 80:
                _SCREENS[key] = {"name": _screen_name(cds, tag), "cds": list(cds)}
                _dirty["v"] = True
            elif scr is not None:
                new = [c for c in cds if c not in scr["cds"]]
                if new and (tag or len(scr["cds"]) < 40):
                    for c_new in new:
                        i = cds.index(c_new)
                        prev = next((x for x in reversed(cds[:i]) if x in scr["cds"]), None)
                        scr["cds"].insert(scr["cds"].index(prev) + 1 if prev else 0, c_new)
                    _dirty["v"] = True
        c, k = cfg(), knobs()
        flat = [b for b in flat if not b.__dict__.get("_ui_hidden")]
        order = c["order"].get(key)
        if order and not getattr(_tl, "ov", None):
            pos = {cd: i for i, cd in enumerate(order)}
            idx = {id(b): i for i, b in enumerate(flat)}
            flat.sort(key=lambda b: (pos.get(_cd_of(b), 10_000 + idx[id(b)])))
        if k["colors"] == "cycle":
            cyc = ["primary", "success", "danger"]
            for i, b in enumerate(flat):
                if _cd_of(b) not in _NO_DECOR and not (c["buttons"].get(_cd_of(b)) or {}).get("color"):
                    b.__dict__["style"] = cyc[i % 3]
        cols = c["cols"].get(key) or (k["cols_main"] if tag == "main" else 0)
        if cols:
            out, row = [], []
            for b in flat:
                if len(b.text) > 24 and cols > 1 or _cd_of(b) in _NO_DECOR and b.text.startswith(("━", "⚡", "👑", "👤")):
                    if row:
                        out.append(row)
                        row = []
                    out.append([b])
                    continue
                row.append(b)
                if len(row) >= cols:
                    out.append(row)
                    row = []
            if row:
                out.append(row)
            markup.keyboard = out
        else:
            # نحافظ على الصفوف الأصلية بعد إزالة المخفي/إعادة الترتيب
            keep = {id(b) for b in flat}
            if order and not getattr(_tl, "ov", None):
                markup.keyboard = _rechunk(flat, rows)
            else:
                markup.keyboard = [r for r in ([b for b in r if id(b) in keep] for r in rows) if r]
        return markup
    except Exception:
        C.log.exception("process_markup")
        return markup


def _rechunk(flat, rows):
    width = max((len(r) for r in rows), default=1)
    out, row = [], []
    for b in flat:
        row.append(b)
        if len(row) >= width:
            out.append(row)
            row = []
    if row:
        out.append(row)
    return out


# ============================================================ النصوص (إطار الرسائل)
_DIV_RE = re.compile(r"^[━─═▬—\-_▁·┄]{3,}$")


def decorate_text(s, k):
    out = []
    for ln in s.split("\n"):
        st = ln.strip()
        if st.startswith("• "):
            ln = ln.replace("• ", k["bullet"] + " ", 1)
        elif _DIV_RE.match(st):
            ln = k["divider"] * min(len(st), 18)
        out.append(ln)
    return "\n".join(out)


def styled_bq(text):
    if text is None:
        return text
    s = str(text).strip()
    if not s:
        return text
    k = knobs()
    if s.startswith("<blockquote"):
        return s
    s = decorate_text(s, k)
    if k["header"]:
        s = f"{_html.escape(k['header'])}\n{s}"
    if k["footer"]:
        s = f"{s}\n{_html.escape(k['footer'])}"
    mode = k["quote"]
    if mode == "blockquote":
        return f"<blockquote>{s}</blockquote>"
    if mode == "expandable":
        return f"<blockquote expandable>{s}</blockquote>" if (len(s) > 280 or s.count("\n") > 5) else f"<blockquote>{s}</blockquote>"
    if mode == "bar":
        return "\n".join("┃ " + ln for ln in s.split("\n"))
    if mode == "pre":
        plain = _html.unescape(re.sub(r"<[^>]+>", "", s))
        return f"<pre>{_html.escape(plain)}</pre>"
    return s


# ============================================================ الأدوات (Kit)
def progress_bar(pct, width=12, style="▰▱"):
    pct = max(0, min(100, pct))
    f = round(pct / 100 * width)
    return style[0] * f + style[1] * (width - f)


def fmt_time(sec):
    sec = max(0, int(sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def terminal_box(title, lines, prompt="$"):
    body = "\n".join(f"│ {ln}" for ln in lines)
    plain = f"┌─[ ● ● ● ]─ {title}\n{body}\n└─ {prompt} _"
    return f"<pre>{_html.escape(plain)}</pre>"


def sample_block(k=None):
    k = k or knobs()
    d = k["divider"] * 14
    return (f"<b>معاينة الستايل</b>\n{d}\n{k['bullet']} نقطة أولى\n{k['bullet']} نقطة ثانية\n{k['arrow']} سهم للانتقال\n"
            f"{progress_bar(65, 12, k['bar'])} 65%\n⏱ {fmt_time(754)} · {SPIN_FRAMES[k['spin']][0]} جارٍ العمل\n{d}")


def run_countdown(chat_id, seconds, title="عد تنازلي", done_text="✅ انتهى الوقت!", on_done=None):
    seconds = max(3, min(int(seconds), 6 * 3600))
    step = 2 if seconds <= 60 else 5 if seconds <= 600 else 15
    k = knobs()
    bot = C.bot

    def render(rem):
        pct = 100 - rem * 100 / seconds
        return f"⏳ <b>{_html.escape(title)}</b>\n{progress_bar(pct, 14, k['bar'])} {int(pct)}%\n⏱ <code>{fmt_time(rem)}</code>"

    def run():
        try:
            msg = bot.send_message(chat_id, render(seconds))
            end = time.time() + seconds
            while True:
                rem = end - time.time()
                if rem <= 0:
                    break
                time.sleep(min(step, max(rem, 0.2)))
                rem = max(0, end - time.time())
                if rem <= 0:
                    break
                try:
                    bot.edit_message_text(render(rem), chat_id, msg.message_id)
                except Exception:
                    pass
            try:
                bot.edit_message_text(f"{done_text}\n{progress_bar(100, 14, k['bar'])} 100%", chat_id, msg.message_id)
            except Exception:
                pass
            if on_done:
                on_done()
        except Exception:
            C.log.exception("countdown")
    threading.Thread(target=run, daemon=True, name="ui-countdown").start()


def run_animation(chat_id, name="braille", text="جارٍ التحميل", seconds=6, final=None):
    frames = SPIN_FRAMES.get(name) or SPIN_FRAMES["braille"]
    k = knobs()
    bot = C.bot

    def run():
        try:
            msg = bot.send_message(chat_id, f"{frames[0]} {text}")
            n = max(2, int(seconds / 1.2))
            for i in range(1, n + 1):
                time.sleep(1.2)
                try:
                    bot.edit_message_text(f"{frames[i % len(frames)]} {text}\n{progress_bar(i * 100 / n, 12, k['bar'])}", chat_id, msg.message_id)
                except Exception:
                    pass
            bot.edit_message_text(final or f"✅ تم\n{progress_bar(100, 12, k['bar'])}", chat_id, msg.message_id)
        except Exception:
            C.log.exception("animation")
    threading.Thread(target=run, daemon=True, name="ui-anim").start()


def terminal_status():
    lines = []
    try:
        import monitor
        s = monitor.sample() if monitor.C else {}
        if s:
            lines += [f"cpu      {s['cpu']:.0f}%", f"ram      {s['ram_used']:.0f}/{s['ram_total']:.0f} MB", f"disk     {s['disk_free']:.0f} MB free"]
    except Exception:
        pass
    run = sum(1 for hp in list(C.manager.processes.values()) if hp.is_alive())
    lines += [f"running  {run} project(s)", f"uptime   {fmt_time(time.time() - C._START_TS)}"]
    return terminal_box("flix@host", lines, "status")


# ============================================================ السورس
def source_kb():
    kb = C.types.InlineKeyboardMarkup(row_width=1)
    for t, u in (cfg()["source"].get("urls") or [])[:4]:
        kb.add(C.types.InlineKeyboardButton(t[:40], url=u))
    kb.add(C.types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    return kb


def source_caption():
    s = cfg()["source"]
    txt = s.get("text") or DEFAULT_SOURCE
    return f"<blockquote>{txt}</blockquote>"[:1020]


def send_source(chat_id):
    s = cfg()["source"]
    kb, cap = source_kb(), source_caption()
    bot = C.bot

    def run():
        try:
            if s.get("file_id"):
                kw = dict(caption=cap, parse_mode="HTML", reply_markup=kb)
                kind = s.get("kind") or "video"
                try:
                    if kind == "animation":
                        bot.send_animation(chat_id, s["file_id"], has_spoiler=bool(s.get("spoiler")), **kw)
                    elif kind == "photo":
                        bot.send_photo(chat_id, s["file_id"], has_spoiler=bool(s.get("spoiler")), **kw)
                    else:
                        bot.send_video(chat_id, s["file_id"], has_spoiler=bool(s.get("spoiler")), supports_streaming=True, **kw)
                except TypeError:
                    getattr(bot, {"animation": "send_animation", "photo": "send_photo"}.get(kind, "send_video"))(chat_id, s["file_id"], **kw)
            else:
                bot.send_message(chat_id, cap, parse_mode="HTML", reply_markup=kb)
        except Exception:
            C.log.exception("send_source")
            try:
                bot.send_message(chat_id, cap, parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass
    threading.Thread(target=run, daemon=True, name="ui-source").start()


# ============================================================ واجهة الاستوديو
def is_owner(uid):
    return uid == C.ADMIN_ID


def _kb(rows):
    kb = C.types.InlineKeyboardMarkup(row_width=2)
    for r in rows:
        kb.row(*[C.types.InlineKeyboardButton(t, callback_data=d) for t, d in r])
    return kb


def _show(call, text, rows):
    kb = _kb(rows)
    try:
        C.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="HTML")
    except Exception:
        try:
            C.bot.send_message(call.message.chat.id, text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass


def screen_home(call):
    c, k = cfg(), knobs()
    pname = all_presets().get(c["preset"], PRESETS["classic"])["name"]
    text = (f"🎨 <b>استوديو الستايل</b>\n\nالستايل الحالي: <b>{pname}</b>\nعدد الأزرار المكتشفة: {len(_REG)} · الشاشات: {len(_SCREENS)}\n\n"
            f"{sample_block(k)}")
    rows = [[("🎭 الستايلات الجاهزة (11)", "ui:pre")], [("🔘 الأزرار والترتيب", "ui:scr"), ("🧩 تخصيص الإطار", "ui:knob")],
            [("✏️ النصوص", "ui:txt:0"), ("🎬 السورس", "ui:src")], [("🧰 الأدوات", "ui:tools"), ("👁 معاينة شاملة", "ui:full")],
            [("➕ زر مخصص", "ui:cadd"), ("📤 تصدير / 📥 استيراد", "ui:io")], [("↩️ تراجع", "ui:undo"), ("♻️ إعادة ضبط", "ui:reset")],
            [("✖️ إغلاق", "ui:close")]]
    _show(call, text, rows)


def screen_presets(call):
    ps = all_presets()
    cur = cfg()["preset"]
    ids = list(ps)
    rows, row = [], []
    for pid in ids:
        row.append((("✅ " if pid == cur else "") + ps[pid]["name"], f"ui:pv:{pid}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([("🔄 إعادة قراءة themes.json", "ui:reload")])
    rows.append([("🔙 رجوع", "ui:home")])
    _show(call, "🎭 <b>اختر ستايلاً</b>\nاضغط على أي ستايل لمعاينته قبل التطبيق.\nالستايلات المخصصة تُقرأ من ملف <code>themes.json</code>.", rows)


def screen_preview(call, pid):
    ps = all_presets()
    if pid not in ps:
        return screen_presets(call)
    with preview(pid):
        sample = styled_bq(sample_block(knobs()))
    k = {**DEFAULT_KNOBS, **ps[pid]["knobs"]}
    desc = " · ".join([f"أزرار: <code>{_html.escape(k['label'])}</code>", f"ألوان: {COLOR_NAMES[k['colors']]}", f"إطار: {QUOTE_NAMES[k['quote']]}"])
    text = f"👁 <b>{ps[pid]['name']}</b>\n{desc}\n\n{sample}"
    _show(call, text, [[("✅ تطبيق", f"ui:ap:{pid}"), ("📋 معاينة القائمة", f"ui:pvm:{pid}")], [("🔙 الستايلات", "ui:pre")]])


def apply_preset(pid):
    c = cfg()
    c = copy.deepcopy(c)
    c["preset"] = pid
    c["over"] = {}
    save_cfg(c)


def preview_menu(chat_id, pid):
    with preview(pid):
        kb = C.main_menu_markup(True)
        kb = process_markup(kb)
        text = styled_bq(f"<b>معاينة القائمة الرئيسية</b>\n{all_presets()[pid]['name']}")
    C.bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")


def screen_knobs(call):
    c, k = cfg(), knobs()
    rows = []
    for name, label in KNOB_NAMES.items():
        v = k[name]
        shown = {"quote": QUOTE_NAMES, "colors": COLOR_NAMES}.get(name, {}).get(v, v)
        if name == "cols_main":
            shown = "أصلي" if not v else v
        if name == "strip_emoji":
            shown = "نعم" if v else "لا"
        rows.append([(f"{label}: {shown}", f"ui:kn:{name}")])
    rows.append([("📝 ترويسة النص", "ui:kh:header"), ("📝 تذييل النص", "ui:kh:footer")])
    rows.append([("🔙 رجوع", "ui:home")])
    _show(call, "🧩 <b>تخصيص الإطار</b>\nكل ضغطة تنتقل للخيار التالي — ويُطبَّق فوراً على كل البوت.\n\n" + sample_block(k), rows)


def cycle_knob(name):
    opts = KNOB_OPTIONS.get(name)
    if not opts:
        return
    c = copy.deepcopy(cfg())
    cur = knobs()[name]
    nxt = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else opts[0]
    c["over"][name] = nxt
    save_cfg(c)


def screen_screens(call):
    rows = []
    items = sorted(_SCREENS.items(), key=lambda kv: (kv[0] not in ("main", "admin"), kv[1]["name"]))
    _ctx[call.from_user.id] = {"screens": [k for k, _ in items]}
    for i, (key, s) in enumerate(items[:24]):
        rows.append([(f"{s['name']} ({len(s['cds'])})", f"ui:sc:{i}")])
    rows.append([("🔙 رجوع", "ui:home")])
    _show(call, "🔘 <b>الشاشات</b>\nاختر شاشة لترتيب أزرارها أو إخفاء/تعديل أي زر.\n"
                "<i>الشاشات تظهر هنا بعد أن يفتحها أي مستخدم مرة واحدة.</i>", rows)


def _scr_by_idx(uid, i):
    keys = _ctx.get(uid, {}).get("screens", [])
    return keys[i] if 0 <= i < len(keys) else None


def screen_edit(call, key):
    s = _SCREENS.get(key)
    if not s:
        return screen_screens(call)
    c = cfg()
    order = c["order"].get(key) or s["cds"]
    cds = [x for x in order if x in s["cds"]] + [x for x in s["cds"] if x not in order]
    _ctx.setdefault(call.from_user.id, {})["cur"] = (key, cds)
    rows = []
    for i, cd in enumerate(cds[:30]):
        ov = c["buttons"].get(cd) or {}
        name = ov.get("text") or _REG.get(cd, {}).get("t") or cd
        mark = "🚫 " if ov.get("hide") else ""
        rows.append([(f"{mark}{name[:22]}", f"ui:be:{i}"), ("⬆️", f"ui:mv:{i}:u"), ("⬇️", f"ui:mv:{i}:d"), ("🚫" if not ov.get("hide") else "👁", f"ui:mv:{i}:h")])
    cols = c["cols"].get(key, 0)
    rows.append([(f"📐 الأعمدة: {cols or 'أصلي'}", "ui:cols")])
    rows.append([("🔙 الشاشات", "ui:scr")])
    _show(call, f"🔘 <b>{s['name']}</b>\n⬆️⬇️ لتغيير الترتيب · 🚫 إخفاء · اضغط اسم الزر لتعديل نصه/لونه/أيقونته.", rows)


def move_button(uid, i, act):
    key, cds = _ctx[uid]["cur"]
    c = copy.deepcopy(cfg())
    if act in ("u", "d"):
        j = i - 1 if act == "u" else i + 1
        if 0 <= j < len(cds):
            cds[i], cds[j] = cds[j], cds[i]
        c["order"][key] = cds
    elif act == "h":
        cd = cds[i]
        if cd == "back_main" or (cd.startswith("ui:") and cd != "ui:source" and not cd.startswith("ui:cb:")):
            return False
        ov = c["buttons"].setdefault(cd, {})
        ov["hide"] = not ov.get("hide")
    save_cfg(c)
    return True


def screen_button(call, i):
    uid = call.from_user.id
    key, cds = _ctx[uid]["cur"]
    cd = cds[i]
    ov = cfg()["buttons"].get(cd) or {}
    orig = _REG.get(cd, {}).get("t", cd)
    colors = {"": "الأصلي", "primary": "🔵 أزرق", "success": "🟢 أخضر", "danger": "🔴 أحمر", "none": "⚪ بدون"}
    _ctx[uid]["btn"] = cd
    text = (f"🔘 <b>تعديل زر</b>\nالأصل: {_html.escape(orig)}\nالنص الحالي: {_html.escape(ov.get('text') or '—')}\nالأيقونة: {ov.get('icon') or '—'}\n"
            f"اللون: {colors.get(ov.get('color') or '')}\nالحالة: {'🚫 مخفي' if ov.get('hide') else '✅ ظاهر'}\n<code>{_html.escape(cd)}</code>")
    _show(call, text, [[("✏️ تغيير النص", "ui:bt:text"), ("😀 أيقونة", "ui:bt:icon")], [("🎨 تغيير اللون", "ui:bt:color")], [("↩️ استرجاع الأصل", "ui:bt:reset")], [("🔙 رجوع", "ui:rs")]])


def button_action(uid, act):
    cd = _ctx[uid]["btn"]
    c = copy.deepcopy(cfg())
    ov = c["buttons"].setdefault(cd, {})
    if act == "color":
        order = ["", "primary", "success", "danger", "none"]
        cur = ov.get("color") or ""
        ov["color"] = order[(order.index(cur) + 1) % len(order)] if cur in order else ""
        if not ov["color"]:
            ov.pop("color")
    elif act == "reset":
        c["buttons"].pop(cd, None)
    save_cfg(c)


def screen_texts(call, page):
    keys = sorted((C._I18N.get("ar") or {}).keys())
    per = 8
    page = max(0, min(page, (len(keys) - 1) // per))
    _ctx[call.from_user.id] = {**_ctx.get(call.from_user.id, {}), "tkeys": keys}
    rows = []
    for i in range(page * per, min(len(keys), (page + 1) * per)):
        k = keys[i]
        custom = C.get_setting(f"text_ar_{k}")
        rows.append([(("✏️ " if custom else "") + k[:28], f"ui:te:{i}")])
    nav = []
    if page > 0:
        nav.append(("◀️", f"ui:txt:{page - 1}"))
    nav.append((f"{page + 1}/{(len(keys) - 1) // per + 1}", "ui:txt:%d" % page))
    if (page + 1) * per < len(keys):
        nav.append(("▶️", f"ui:txt:{page + 1}"))
    rows += [nav, [("🔙 رجوع", "ui:home")]]
    _show(call, "✏️ <b>نصوص البوت</b>\nاختر رسالة لتغيير نصها (العربية). ✏️ = معدّلة.", rows)


def screen_text_key(call, i):
    keys = _ctx.get(call.from_user.id, {}).get("tkeys", [])
    if not 0 <= i < len(keys):
        return screen_texts(call, 0)
    k = keys[i]
    cur = C.get_setting(f"text_ar_{k}") or (C._I18N.get("ar") or {}).get(k, "")
    _ctx[call.from_user.id]["tkey"] = k
    _show(call, f"✏️ <b>{_html.escape(k)}</b>\n\n<code>{_html.escape(cur[:900])}</code>\n\nيدعم HTML بسيط (&lt;b&gt; &lt;i&gt; &lt;code&gt;) والمتغيرات الموجودة في النص كما هي.",
          [[("✏️ تغيير النص", "ui:tt:set"), ("↩️ استرجاع الأصل", "ui:tt:reset")], [("🔙 رجوع", "ui:txt:0")]])


def screen_tools(call):
    k = knobs()
    rows = [[("⏳ عد تنازلي 30 ثانية", "ui:t:cd30"), ("⏳ دقيقتان", "ui:t:cd120")], [("🎞 شاشة متحركة", "ui:t:anim"), (f"🔁 المؤشر: {k['spin']}", "ui:ks")],
            [("💻 ترمنال الحالة", "ui:t:term"), ("📦 تجربة السورس", "ui:t:src")]]
    if _plugins:
        rows.append([(f"🧩 الإضافات ({len(_plugins)})", "ui:t:plug")])
    rows.append([("🔙 رجوع", "ui:home")])
    _show(call, "🧰 <b>الأدوات</b>\nكلها حقيقية وتتأثر بالستايل الحالي. لإضافة أدوات جديدة ضع ملف <code>plugin_اسم.py</code> بجوار البوت.", rows)


def screen_source(call):
    s = cfg()["source"]
    media = {"video": "🎬 فيديو", "animation": "🎞 GIF", "photo": "🖼 صورة"}.get(s.get("kind"), "— لا يوجد")
    text = (f"🎬 <b>زر السورس</b>\nالوسائط: {media}\nالتمويه (Spoiler): {'✅ مفعّل' if s.get('spoiler') else '❌'}\nأزرار الروابط: {len(s.get('urls') or [])}\n\n"
            f"<b>النص:</b>\n{source_caption()}")
    _show(call, text, [[("📹 تعيين الفيديو", "ui:sa:media"), ("📝 تعديل النص", "ui:sa:text")], [(f"🌫 التمويه: {'إيقاف' if s.get('spoiler') else 'تشغيل'}", "ui:sa:spoiler"), ("🔗 أزرار الروابط", "ui:sa:urls")],
                       [("🗑 حذف الفيديو", "ui:sa:delmedia"), ("🧪 تجربة", "ui:t:src")], [("🔙 رجوع", "ui:home")]])


def ask(uid, kind, prompt, back, call, **extra):
    _pending[uid] = {"kind": kind, "back": back, **extra, "ts": time.time()}
    C.bot.send_message(call.message.chat.id, prompt + "\n\n<i>أرسل /cancel للإلغاء.</i>", parse_mode="HTML")


# ============================================================ المعالجات
def on_callback(call):
    uid = call.from_user.id
    d = call.data or ""
    try:
        if d == "ui:source":
            C.bot.answer_callback_query(call.id)
            return send_source(call.message.chat.id)
        if d.startswith("ui:cb:"):
            cb = next((x for x in cfg()["custom"] if x["id"] == d[6:]), None)
            if cb and cb.get("kind") == "popup":
                return C.bot.answer_callback_query(call.id, (cb.get("value") or "")[:190], show_alert=True)
            if cb and cb.get("kind") == "source":
                C.bot.answer_callback_query(call.id)
                return send_source(call.message.chat.id)
            return C.bot.answer_callback_query(call.id)
        if not is_owner(uid):
            return C.bot.answer_callback_query(call.id, "للمالك فقط", show_alert=True)
        p = d.split(":")
        a = p[1] if len(p) > 1 else "home"
        C.bot.answer_callback_query(call.id)
        _pending.pop(uid, None)
        if a == "home":
            return screen_home(call)
        if a == "close":
            return C.bot.delete_message(call.message.chat.id, call.message.message_id)
        if a == "pre":
            return screen_presets(call)
        if a == "pv":
            return screen_preview(call, p[2])
        if a == "ap":
            apply_preset(p[2])
            return screen_home(call)
        if a == "pvm":
            return preview_menu(call.message.chat.id, p[2])
        if a == "reload":
            load_custom_presets()
            return screen_presets(call)
        if a == "knob":
            return screen_knobs(call)
        if a == "kn":
            cycle_knob(p[2])
            return screen_knobs(call)
        if a == "ks":
            cycle_knob("spin")
            return screen_tools(call)
        if a == "rs":
            return screen_edit(call, _ctx[uid]["cur"][0])
        if a == "kh":
            return ask(uid, "knob_text", f"أرسل نص {'الترويسة' if p[2] == 'header' else 'التذييل'} (أو - للحذف):", "ui:knob", call, name=p[2])
        if a == "scr":
            return screen_screens(call)
        if a == "sc":
            key = _scr_by_idx(uid, int(p[2]))
            return screen_edit(call, key) if key else screen_screens(call)
        if a == "mv":
            move_button(uid, int(p[2]), p[3])
            key, _ = _ctx[uid]["cur"]
            return screen_edit(call, key)
        if a == "cols":
            key, _ = _ctx[uid]["cur"]
            c = copy.deepcopy(cfg())
            c["cols"][key] = (c["cols"].get(key, 0) + 1) % 4
            save_cfg(c)
            return screen_edit(call, key)
        if a == "be":
            return screen_button(call, int(p[2]))
        if a == "bt":
            if p[2] in ("color", "reset"):
                button_action(uid, p[2])
                key, cds = _ctx[uid]["cur"]
                return screen_button(call, cds.index(_ctx[uid]["btn"]))
            return ask(uid, "btn_" + p[2], "أرسل النص الجديد للزر:" if p[2] == "text" else "أرسل أيقونة (إيموجي واحد):", "ui:home", call, cd=_ctx[uid]["btn"])
        if a == "txt":
            return screen_texts(call, int(p[2]))
        if a == "te":
            return screen_text_key(call, int(p[2]))
        if a == "tt":
            k = _ctx[uid]["tkey"]
            if p[2] == "reset":
                C.set_setting(f"text_ar_{k}", "")
                return screen_texts(call, 0)
            return ask(uid, "key_text", f"أرسل النص الجديد لـ <code>{_html.escape(k)}</code>:", "ui:txt:0", call, key=k)
        if a == "tools":
            return screen_tools(call)
        if a == "t":
            return run_tool(call, p[2])
        if a == "src":
            return screen_source(call)
        if a == "sa":
            return source_action(call, p[2])
        if a == "cadd":
            return ask(uid, "custom_btn", "أرسل بصيغة:\n<code>النص | النوع | القيمة</code>\nالأنواع: <code>url</code> (رابط) · <code>popup</code> (نافذة نص) · <code>source</code>\nمثال: <code>📢 قناتنا | url | https://t.me/xxx</code>", "ui:home", call)
        if a == "io":
            return screen_io(call)
        if a == "exp":
            return export_cfg(call.message.chat.id)
        if a == "imp":
            return ask(uid, "import", "أرسل ملف JSON (أو الصق نصه) للاستيراد:", "ui:io", call)
        if a == "undo":
            return undo(call)
        if a == "reset":
            save_cfg(default_cfg())
            return screen_home(call)
        if a == "full":
            return full_preview(call)
    except Exception:
        C.log.exception("studio callback %s", d)


def screen_io(call):
    _show(call, "📤📥 <b>تصدير / استيراد</b>\nتصدير كل إعدادات الشكل في ملف JSON تعدّله يدوياً ثم تستورده، أو تنقله لبوت آخر.",
          [[("📤 تصدير", "ui:exp"), ("📥 استيراد", "ui:imp")], [("🔙 رجوع", "ui:home")]])


def export_cfg(chat_id):
    data = json.dumps(cfg(), ensure_ascii=False, indent=2).encode("utf-8")
    f = io.BytesIO(data)
    f.name = "theme.json"
    C.bot.send_document(chat_id, f, caption="📤 إعدادات الشكل — عدّلها ثم استوردها من الاستوديو.")


def undo(call):
    try:
        hist = json.loads(C.get_setting("ui_hist") or "[]")
    except Exception:
        hist = []
    if not hist:
        C.bot.answer_callback_query(call.id, "لا يوجد ما يُتراجع عنه", show_alert=True)
        return screen_home(call)
    prev = hist.pop()
    C.set_setting("ui_hist", json.dumps(hist))
    C.set_setting("ui_cfg", prev)
    _cache["cfg"] = None
    screen_home(call)


def sanitize_cfg(d):
    base = default_cfg()
    if not isinstance(d, dict):
        raise ValueError("الملف ليس كائن JSON")
    if d.get("preset") in all_presets():
        base["preset"] = d["preset"]
    base["over"] = _clean_knobs(d.get("over") or {})
    for cd, ov in (d.get("buttons") or {}).items():
        if isinstance(ov, dict) and len(str(cd)) <= 64:
            clean = {}
            if isinstance(ov.get("text"), str):
                clean["text"] = ov["text"][:60]
            if isinstance(ov.get("icon"), str):
                clean["icon"] = ov["icon"][:8]
            if ov.get("color") in ("primary", "success", "danger", "none"):
                clean["color"] = ov["color"]
            if ov.get("hide"):
                clean["hide"] = True
            if clean:
                base["buttons"][str(cd)] = clean
    for key, lst in (d.get("order") or {}).items():
        if isinstance(lst, list):
            base["order"][str(key)] = [str(x)[:64] for x in lst[:60]]
    for key, n in (d.get("cols") or {}).items():
        if n in (0, 1, 2, 3):
            base["cols"][str(key)] = n
    custom = []
    for x in d.get("custom") or []:
        if isinstance(x, dict) and re.match(r"^[a-z0-9_]{1,16}$", str(x.get("id", ""))) and x.get("kind") in ("url", "popup", "source"):
            if x["kind"] == "url" and not re.match(r"^https?://", str(x.get("value", ""))):
                continue
            custom.append({"id": x["id"], "text": str(x.get("text", ""))[:40] or "زر", "kind": x["kind"], "value": str(x.get("value", ""))[:190]})
    base["custom"] = custom if "custom" in d else base["custom"]
    s = d.get("source") or {}
    if isinstance(s, dict):
        base["source"].update({"text": str(s.get("text", ""))[:900], "file_id": str(s.get("file_id", ""))[:200], "kind": s.get("kind") if s.get("kind") in ("video", "animation", "photo") else "",
                               "spoiler": bool(s.get("spoiler", True)),
                               "urls": [[str(t)[:40], str(u)] for t, u in (s.get("urls") or [])[:4] if re.match(r"^https?://", str(u))]})
    return base


def run_tool(call, tool):
    chat = call.message.chat.id
    if tool == "cd30":
        run_countdown(chat, 30, "عد تنازلي تجريبي")
    elif tool == "cd120":
        run_countdown(chat, 120, "عد تنازلي — دقيقتان")
    elif tool == "anim":
        run_animation(chat, knobs()["spin"], "جارٍ التحميل")
    elif tool == "term":
        C.bot.send_message(chat, terminal_status(), parse_mode="HTML")
    elif tool == "src":
        send_source(chat)
    elif tool == "plug":
        return _show(call, "🧩 <b>الإضافات المحمّلة</b>\n" + "\n".join(f"• {_html.escape(p)}" for p in _plugins), [[("🔙 رجوع", "ui:tools")]])


def source_action(call, act):
    uid = call.from_user.id
    c = copy.deepcopy(cfg())
    s = c["source"]
    if act == "spoiler":
        s["spoiler"] = not s.get("spoiler")
    elif act == "delmedia":
        s["file_id"], s["kind"] = "", ""
    elif act == "media":
        return ask(uid, "src_media", "أرسل الفيديو (أو GIF/صورة) الذي سيظهر عند الضغط على «السورس». سيظهر مموّهاً (Spoiler) حتى يضغط عليه المستخدم.", "ui:src", call)
    elif act == "text":
        return ask(uid, "src_text", "أرسل نص التعريف (يدعم &lt;b&gt; &lt;i&gt; &lt;a href=...&gt;). سيظهر داخل اقتباس. أرسل - لاستعادة النص الافتراضي:", "ui:src", call)
    elif act == "urls":
        return ask(uid, "src_urls", "أرسل أزرار الروابط، كل سطر:\n<code>النص | https://رابط</code>\n(حتى 4 أسطر، أو - للحذف)", "ui:src", call)
    save_cfg(c)
    screen_source(call)


def full_preview(call):
    chat = call.message.chat.id
    k = knobs()
    C.bot.send_message(chat, styled_bq(sample_block(k)), parse_mode="HTML")
    kb = process_markup(C.main_menu_markup(True))
    C.bot.send_message(chat, styled_bq("<b>القائمة الرئيسية بالستايل الحالي</b>"), reply_markup=kb, parse_mode="HTML")
    C.bot.send_message(chat, terminal_status(), parse_mode="HTML")
    run_animation(chat, k["spin"], "معاينة الأنيميشن", 4)


def has_pending(m):
    p = _pending.get(m.from_user.id)
    return bool(p) and time.time() - p["ts"] < 600


def on_pending(m):
    uid = m.from_user.id
    p = _pending.get(uid)
    if not p:
        return
    txt = (getattr(m, "text", None) or getattr(m, "caption", None) or "").strip()
    if txt == "/cancel":
        _pending.pop(uid, None)
        return C.bot.send_message(m.chat.id, "تم الإلغاء. /studio للعودة.")
    kind = p["kind"]
    try:
        c = copy.deepcopy(cfg())
        if kind == "btn_text":
            c["buttons"].setdefault(p["cd"], {})["text"] = txt[:60]
        elif kind == "btn_icon":
            c["buttons"].setdefault(p["cd"], {})["icon"] = txt[:8]
        elif kind == "key_text":
            C.set_setting(f"text_ar_{p['key']}", txt)
        elif kind == "knob_text":
            c["over"][p["name"]] = "" if txt == "-" else txt[:200]
        elif kind == "src_text":
            c["source"]["text"] = "" if txt == "-" else txt[:900]
        elif kind == "src_urls":
            urls = []
            if txt != "-":
                for ln in txt.splitlines()[:4]:
                    if "|" in ln:
                        t, u = [x.strip() for x in ln.split("|", 1)]
                        if re.match(r"^https?://", u):
                            urls.append([t[:40], u])
            c["source"]["urls"] = urls
        elif kind == "src_media":
            ct = getattr(m, "content_type", "")
            if ct == "video":
                c["source"].update(file_id=m.video.file_id, kind="video")
            elif ct == "animation":
                c["source"].update(file_id=m.animation.file_id, kind="animation")
            elif ct == "photo":
                c["source"].update(file_id=m.photo[-1].file_id, kind="photo")
            elif ct == "document" and (getattr(m.document, "mime_type", "") or "").startswith("video"):
                c["source"].update(file_id=m.document.file_id, kind="video")
            else:
                return C.bot.send_message(m.chat.id, "❌ أرسل فيديو أو GIF أو صورة.")
        elif kind == "custom_btn":
            parts = [x.strip() for x in txt.split("|")]
            if len(parts) < 2 or parts[1] not in ("url", "popup", "source"):
                return C.bot.send_message(m.chat.id, "❌ الصيغة: النص | النوع | القيمة")
            val = parts[2] if len(parts) > 2 else ""
            if parts[1] == "url" and not re.match(r"^https?://", val):
                return C.bot.send_message(m.chat.id, "❌ الرابط يجب أن يبدأ بـ http(s)://")
            cid = "c" + hashlib.sha1((parts[0] + str(time.time())).encode()).hexdigest()[:6]
            c["custom"].append({"id": cid, "text": parts[0][:40], "kind": parts[1], "value": val[:190]})
        elif kind == "import":
            raw = txt
            if getattr(m, "content_type", "") == "document":
                raw = C.bot.download_file(C.bot.get_file(m.document.file_id).file_path).decode("utf-8")
            c = sanitize_cfg(json.loads(raw))
        save_cfg(c)
        _pending.pop(uid, None)
        C.bot.send_message(m.chat.id, "✅ تم الحفظ — أرسل /studio للمتابعة.")
    except ValueError as e:  # JSON تالف / قيمة غير صالحة
        C.bot.send_message(m.chat.id, f"❌ ملف غير صالح: {_html.escape(str(e)[:150])}")
    except Exception as e:
        C.log.exception("studio pending")
        C.bot.send_message(m.chat.id, f"❌ تعذر الحفظ: {_html.escape(str(e)[:150])}")


def cmd_studio(m):
    if not is_owner(m.from_user.id):
        return
    _pending.pop(m.from_user.id, None)
    fake = type("Call", (), {})()
    msg = C.bot.send_message(m.chat.id, "🎨 جارٍ فتح الاستوديو...")
    fake.message, fake.from_user, fake.id = msg, m.from_user, "0"
    screen_home(fake)


def cmd_countdown(m):
    if not is_owner(m.from_user.id):
        return
    a = (m.text or "").split(None, 2)
    if len(a) < 2 or not a[1].isdigit():
        return C.bot.send_message(m.chat.id, "الاستخدام: <code>/countdown 60 عنوان اختياري</code>", parse_mode="HTML")
    run_countdown(m.chat.id, int(a[1]), a[2] if len(a) > 2 else "عد تنازلي")


def cmd_anim(m):
    if not is_owner(m.from_user.id):
        return
    a = (m.text or "").split()
    run_animation(m.chat.id, a[1] if len(a) > 1 and a[1] in SPIN_FRAMES else knobs()["spin"], "جارٍ التحميل")


def cmd_term(m):
    if is_owner(m.from_user.id):
        C.bot.send_message(m.chat.id, terminal_status(), parse_mode="HTML")


def cmd_source(m):
    send_source(m.chat.id)


def cmd_themeexport(m):
    if is_owner(m.from_user.id):
        export_cfg(m.chat.id)


def cmd_uireset(m):
    if is_owner(m.from_user.id):
        save_cfg(default_cfg())
        C.bot.send_message(m.chat.id, "♻️ أُعيد الشكل للوضع الأصلي.")


# ============================================================ التركيب
def _reg_front(decorator_result_list_name):
    lst = getattr(C.bot, decorator_result_list_name, None)
    if isinstance(lst, list) and lst:
        lst.insert(0, lst.pop())


def _flush_loop():
    while True:
        time.sleep(30)
        if _dirty["v"]:
            _dirty["v"] = False
            try:
                C.set_setting("ui_reg", json.dumps({"reg": _REG, "screens": _SCREENS}, ensure_ascii=False)[:60000])
            except Exception:
                pass


def load_plugins():
    for path in sorted(glob.glob(os.path.join(_HERE, "plugin_*.py"))):
        name = os.path.basename(path)[:-3]
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            reg = getattr(mod, "register", None)
            if callable(reg):
                reg(C, sys.modules[__name__])
                _plugins.append(name)
        except Exception:
            C.log.exception("plugin %s", name)


def install(core):
    global C
    C = core
    try:
        saved = json.loads(C.get_setting("ui_reg") or "{}")
        _REG.update(saved.get("reg", {}))
        _SCREENS.update(saved.get("screens", {}))
    except Exception:
        pass
    load_custom_presets()
    # 1) أزرار: زخرفة عند الإنشاء
    types = core.types
    prev_init = types.InlineKeyboardButton.__init__

    def init(self, *a, **kw):
        prev_init(self, *a, **kw)
        decorate_button(self)
    types.InlineKeyboardButton.__init__ = init
    # 2) لوحات: إخفاء/ترتيب/أعمدة عند الإرسال
    for name in ("send_message", "edit_message_text", "edit_message_reply_markup", "send_photo", "send_video",
                 "send_document", "send_animation", "edit_message_caption", "reply_to"):
        orig = getattr(core.bot, name, None)
        if orig is None:
            continue

        def make(o):
            def w(*a, **k):
                if "reply_markup" in k:
                    k["reply_markup"] = process_markup(k["reply_markup"])
                a = tuple(process_markup(x) if isinstance(x, types.InlineKeyboardMarkup) else x for x in a)
                return o(*a, **k)
            return w
        setattr(core.bot, name, make(orig))
    # 3) إطار النص
    core._bq = styled_bq
    # 4) القائمة الرئيسية + لوحة الأدمن
    orig_main, orig_admin = core.main_menu_markup, core.admin_main_markup

    def main_menu(is_admin=False):
        kb = orig_main(is_admin)
        for cb in cfg()["custom"]:
            if cb.get("kind") == "url":
                kb.add(types.InlineKeyboardButton(cb["text"], url=cb.get("value", "")))
            else:
                kb.add(types.InlineKeyboardButton(cb["text"], callback_data=("ui:source" if cb["id"] == "source" else f"ui:cb:{cb['id']}"), style="success"))
        kb.__dict__["_ui_screen"] = "main"
        return kb

    def admin_main():
        kb = orig_admin()
        kb.add(types.InlineKeyboardButton("🎨 استوديو الستايل", callback_data="ui:home", style="primary"))
        kb.__dict__["_ui_screen"] = "admin"
        return kb
    core.main_menu_markup, core.admin_main_markup = main_menu, admin_main
    if hasattr(core, "admin_menu_markup"):
        core.admin_menu_markup = admin_main
    # 5) المعالجات (تُدرَج في المقدمة لتسبق معالجات النواة العامة)
    bot = core.bot
    bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("ui:"))(on_callback)
    _reg_front("callback_query_handlers")
    bot.message_handler(func=has_pending, content_types=["text", "video", "animation", "photo", "document"])(on_pending)
    _reg_front("message_handlers")
    for cmds, fn in ((["studio", "style"], cmd_studio), (["countdown"], cmd_countdown), (["anim"], cmd_anim), (["term"], cmd_term),
                     (["source"], cmd_source), (["themeexport"], cmd_themeexport), (["uireset"], cmd_uireset)):
        bot.message_handler(commands=cmds)(fn)
        _reg_front("message_handlers")
    threading.Thread(target=_flush_loop, daemon=True, name="studio-flush").start()
    load_plugins()
    core.log.info("Style studio installed (%d presets, %d plugins)", len(all_presets()), len(_plugins))
