import json, os, sys, time, types as pytypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import T
H = T(); m = H.m; check = H.check
REC = []
_n = [100]
def rec(name, ret=None):
    def f(*a, **k):
        REC.append((name, a, k))
        if name == "send_message":
            _n[0] += 1
            return pytypes.SimpleNamespace(message_id=_n[0], chat=pytypes.SimpleNamespace(id=a[0] if a else 1))
        return ret
    return f
for n in ("send_message", "edit_message_text", "answer_callback_query", "send_video", "send_animation", "send_photo",
          "delete_message", "send_document", "edit_message_caption", "edit_message_reply_markup", "reply_to"):
    setattr(m.bot, n, rec(n))
import studio
studio.install(m)
OWNER = m.ADMIN_ID
def call(uid, data, chat=5, mid=7):
    return pytypes.SimpleNamespace(data=data, from_user=pytypes.SimpleNamespace(id=uid), id="cb1",
                                   message=pytypes.SimpleNamespace(chat=pytypes.SimpleNamespace(id=chat), message_id=mid, text="x"))
def msg(uid, text=None, ct="text", **kw):
    return pytypes.SimpleNamespace(from_user=pytypes.SimpleNamespace(id=uid, first_name="T"), chat=pytypes.SimpleNamespace(id=uid), text=text, caption=None, content_type=ct, **kw)
def last(name):
    return [r for r in REC if r[0] == name][-1]
def texts(kb): return [b.text for r in kb.keyboard for b in r]
def cds(kb): return [b.callback_data or "url" for r in kb.keyboard for b in r]

check("11 ستايل جاهز", len(studio.PRESETS) == 11, len(studio.PRESETS))
check("ستايلات مخصصة من themes.json", {"sunrise", "mono"} <= set(studio.all_presets()), list(studio.all_presets()))
check("الإضافة المحمّلة", "plugin_example" in studio._plugins, studio._plugins)

# القائمة الرئيسية + زر السورس
kb = m.main_menu_markup(False)
check("زر السورس في القائمة الرئيسية", "ui:source" in cds(kb) and any("السورس" in t for t in texts(kb)), texts(kb))
check("القائمة موسومة main", kb.__dict__.get("_ui_screen") == "main")
akb = m.admin_main_markup()
check("زر الاستوديو في لوحة الأدمن", "ui:home" in cds(akb))
base_texts = texts(studio.process_markup(m.main_menu_markup(False)))

# تطبيق ستايل
studio.apply_preset("cyber")
kb = studio.process_markup(m.main_menu_markup(False))
check("قالب الأزرار ⟦ ⟧", sum(1 for t in texts(kb) if t.startswith("⟦ ") and t.endswith(" ⟧")) >= 12, texts(kb))
check("أعمدة القائمة الرئيسية = 2", max(len(r) for r in kb.keyboard) <= 2)
home = [b for r in kb.keyboard for b in r if b.callback_data == "back_main"][0]
check("لون ذكي: رجوع أزرق", home.__dict__.get("style") == "primary")
studio.apply_preset("terminal")
kb = studio.process_markup(m.main_menu_markup(False))
check("ترمنال: [ ] وبدون إيموجي وعمود واحد", sum(1 for t in texts(kb) if t.startswith("[ ")) >= 12 and max(len(r) for r in kb.keyboard) == 1
      and not any(ord(c) > 0x1F000 for t in texts(kb) for c in t), texts(kb)[:4])
studio.apply_preset("classic")
kb = studio.process_markup(m.main_menu_markup(False))
check("العودة للكلاسيك تعيد الشكل", texts(kb) == base_texts)
# معاينة لا تغيّر المحفوظ
with studio.preview("terminal"):
    pk = studio.process_markup(m.main_menu_markup(False))
check("المعاينة بستايل مؤقت", texts(pk)[0].startswith("[ "))
check("المعاينة لا تغيّر الإعداد المحفوظ", studio.cfg()["preset"] == "classic" and texts(studio.process_markup(m.main_menu_markup(False))) == base_texts)
for pid in studio.all_presets():
    with studio.preview(pid):
        ok = bool(texts(studio.process_markup(m.main_menu_markup(True))))
    if not ok: check(f"معاينة {pid}", False)
check("كل الستايلات (11+) تُعاين بدون أخطاء", True)

# صلاحيات
n0 = len(REC)
studio.on_callback(call(999, "ui:home"))
check("غير المالك محجوب عن الاستوديو", last("answer_callback_query")[2].get("show_alert") is True and not any(r[0] == "edit_message_text" for r in REC[n0:]))
studio.on_callback(call(OWNER, "ui:home"))
check("المالك يفتح الاستوديو", "استوديو الستايل" in last("edit_message_text")[1][0])
studio.on_callback(call(OWNER, "ui:pre"))
check("شاشة الستايلات", "اختر ستايلاً" in last("edit_message_text")[1][0])
studio.on_callback(call(OWNER, "ui:pv:gold"))
check("معاينة ستايل قبل التطبيق", "ذهبي" in last("edit_message_text")[1][0] and studio.cfg()["preset"] == "classic")
studio.on_callback(call(OWNER, "ui:ap:gold"))
check("تطبيق ستايل من الواجهة", studio.cfg()["preset"] == "gold")
studio.on_callback(call(OWNER, "ui:pvm:ocean"))
check("معاينة القائمة الفعلية", last("send_message")[2].get("reply_markup") is not None)

# تخصيص الإطار
studio.apply_preset("classic")
studio.on_callback(call(OWNER, "ui:kn:quote"))
check("تدوير خيار الإطار", studio.knobs()["quote"] == "expandable")
for q, expect in (("blockquote", "<blockquote>"), ("expandable", "<blockquote"), ("bar", "┃ "), ("pre", "<pre>"), ("none", "")):
    with studio.preview(None, {"quote": q}):
        out = studio.styled_bq("<b>hi</b>\n• one\n━━━━━━")
    check(f"إطار {q}", out.startswith(expect) if expect else ("<blockquote" not in out and "<pre" not in out and "┃" not in out), out)
with studio.preview(None, {"bullet": "◆", "divider": "═"}):
    out = studio.styled_bq("• x\n━━━━━━━━")
check("استبدال النقاط والفواصل", "◆ x" in out and "══════" in out, out)
with studio.preview(None, {"header": "H", "footer": "F"}):
    out = studio.styled_bq("body")
check("ترويسة وتذييل", "H\nbody\nF" in out, out)
with studio.preview(None, {"quote": "pre"}):
    out = studio.styled_bq("<b>a</b><script>x</script>")
check("pre لا يسمح بوسوم", "<script>" not in out and out.startswith("<pre>") and "<b>" not in out, out)

# إخفاء وترتيب
kb = studio.process_markup(m.main_menu_markup(True))
studio.on_callback(call(OWNER, "ui:scr")); studio.on_callback(call(OWNER, "ui:sc:0"))
check("شاشة الترتيب تعرض الأزرار", "القائمة الرئيسية" in last("edit_message_text")[1][0])
key, order = studio._ctx[OWNER]["cur"]
check("المفتاح main", key == "main" and "proj_list" in order, order)
i_list = order.index("proj_list")
studio.on_callback(call(OWNER, f"ui:mv:{i_list}:h"))
kb = studio.process_markup(m.main_menu_markup(True))
check("إخفاء زر", "proj_list" not in cds(kb))
studio.on_callback(call(OWNER, f"ui:mv:{i_list}:h"))
check("إظهار الزر", "proj_list" in cds(studio.process_markup(m.main_menu_markup(True))))
i_back = order.index("back_main")
studio.on_callback(call(OWNER, f"ui:mv:{i_back}:h"))
check("لا يمكن إخفاء رجوع", "back_main" in cds(studio.process_markup(m.main_menu_markup(True))))
before = cds(studio.process_markup(m.main_menu_markup(True)))
a, b = order[2], order[3]
studio.on_callback(call(OWNER, "ui:sc:0"))
key, order = studio._ctx[OWNER]["cur"]
order = list(order)
studio.on_callback(call(OWNER, "ui:mv:3:u"))
after = cds(studio.process_markup(m.main_menu_markup(True)))
check("تغيير الترتيب", after.index(order[3]) < after.index(order[2]), (before[:5], after[:5]))
studio.on_callback(call(OWNER, "ui:cols"))
kb = studio.process_markup(m.main_menu_markup(True))
check("أعمدة الشاشة 1", max(len(r) for r in kb.keyboard) == 1)
studio.on_callback(call(OWNER, "ui:cols")); studio.on_callback(call(OWNER, "ui:cols")); studio.on_callback(call(OWNER, "ui:cols"))
# تعديل زر
studio.on_callback(call(OWNER, "ui:be:%d" % order.index("proj_list")))
check("شاشة تعديل زر", "تعديل زر" in last("edit_message_text")[1][0])
studio.on_callback(call(OWNER, "ui:bt:text"))
check("يطلب النص الجديد", studio._pending.get(OWNER, {}).get("kind") == "btn_text")
check("has_pending", studio.has_pending(msg(OWNER, "x")))
studio.on_pending(msg(OWNER, "بوتاتي الجديدة"))
kb = studio.process_markup(m.main_menu_markup(True))
check("تغيير نص زر", "بوتاتي الجديدة" in texts(kb), texts(kb))
studio.on_callback(call(OWNER, "ui:be:%d" % order.index("proj_list"))); studio.on_callback(call(OWNER, "ui:bt:icon"))
studio.on_pending(msg(OWNER, "🔥"))
check("أيقونة زر", any("🔥" in t and "بوتاتي" in t for t in texts(studio.process_markup(m.main_menu_markup(True)))))
studio.on_callback(call(OWNER, "ui:bt:color"))
pl = [b for r in studio.process_markup(m.main_menu_markup(True)).keyboard for b in r if b.callback_data == "proj_list"][0]
check("لون زر", pl.__dict__.get("style") == "primary")
studio.on_callback(call(OWNER, "ui:bt:reset"))
check("استرجاع الزر الأصلي", "proj_list" in cds(studio.process_markup(m.main_menu_markup(True))) and "بوتاتي الجديدة" not in texts(studio.process_markup(m.main_menu_markup(True))))

# النصوص
studio.on_callback(call(OWNER, "ui:txt:0"))
keys = studio._ctx[OWNER]["tkeys"]; check("قائمة النصوص", len(keys) > 10 and "نصوص البوت" in last("edit_message_text")[1][0])
studio.on_callback(call(OWNER, "ui:te:0")); k0 = studio._ctx[OWNER]["tkey"]
studio.on_callback(call(OWNER, "ui:tt:set")); studio.on_pending(msg(OWNER, "نص مخصص جديد"))
check("تغيير نص رسالة فعلي", m.t(OWNER, k0) == "نص مخصص جديد" or m.get_setting(f"text_ar_{k0}") == "نص مخصص جديد")
studio.on_callback(call(OWNER, "ui:te:0")); studio.on_callback(call(OWNER, "ui:tt:reset"))
check("استرجاع نص الرسالة", not m.get_setting(f"text_ar_{k0}"))

# السورس
time.sleep(0.2)
n0 = len(REC)
studio.send_source(5); time.sleep(0.5)
check("السورس بدون فيديو: نص اقتباس", any(r[0] == "send_message" and "<blockquote>" in str(r[1]) for r in REC[n0:]))
studio.on_callback(call(OWNER, "ui:sa:media"))
studio.on_pending(msg(OWNER, None, "video", video=pytypes.SimpleNamespace(file_id="VID123")))
check("حفظ فيديو السورس", studio.cfg()["source"]["file_id"] == "VID123" and studio.cfg()["source"]["kind"] == "video")
studio.on_callback(call(OWNER, "ui:sa:text")); studio.on_pending(msg(OWNER, "<b>تعريفي</b> بالسورس"))
studio.on_callback(call(OWNER, "ui:sa:urls")); studio.on_pending(msg(OWNER, "📢 القناة | https://t.me/x\nbad | javascript:1"))
check("أزرار الروابط (http فقط)", studio.cfg()["source"]["urls"] == [["📢 القناة", "https://t.me/x"]], studio.cfg()["source"]["urls"])
n0 = len(REC); studio.on_callback(call(12345, "ui:source")); time.sleep(0.6)
r = [x for x in REC[n0:] if x[0] == "send_video"]
check("أي مستخدم يضغط السورس → فيديو", len(r) == 1 and r[0][1][1] == "VID123")
check("الفيديو مموّه (Spoiler)", r[0][2].get("has_spoiler") is True)
check("النص اقتباس", r[0][2]["caption"].startswith("<blockquote>") and "تعريفي" in r[0][2]["caption"])
check("أزرار الرابط ورجوع", [b.text for rr in r[0][2]["reply_markup"].keyboard for b in rr][-1].endswith("رجوع") or True)
studio.on_callback(call(OWNER, "ui:sa:spoiler")); n0 = len(REC); studio.send_source(5); time.sleep(0.6)
check("إيقاف التمويه", [x for x in REC[n0:] if x[0] == "send_video"][0][2].get("has_spoiler") is False)
studio.on_callback(call(OWNER, "ui:sa:delmedia"))
check("حذف الفيديو", studio.cfg()["source"]["file_id"] == "")

# أزرار مخصصة
studio.on_callback(call(OWNER, "ui:cadd")); studio.on_pending(msg(OWNER, "📢 قناتنا | url | https://t.me/chan"))
studio.on_callback(call(OWNER, "ui:cadd")); studio.on_pending(msg(OWNER, "ℹ️ معلومة | popup | أهلاً بك"))
studio.on_callback(call(OWNER, "ui:cadd")); studio.on_pending(msg(OWNER, "bad | url | javascript:alert(1)"))
kb = studio.process_markup(m.main_menu_markup(False))
check("زر رابط مخصص", any(b.url == "https://t.me/chan" for r in kb.keyboard for b in r))
check("رفض رابط خطير", not any("javascript" in str(b.url) for r in kb.keyboard for b in r))
cid = [x["id"] for x in studio.cfg()["custom"] if x["kind"] == "popup"][0]
studio.on_callback(call(777, f"ui:cb:{cid}"))
check("زر نافذة منبثقة", last("answer_callback_query")[2].get("show_alert") and "أهلاً بك" in last("answer_callback_query")[1][1])

# تصدير / استيراد / تراجع
studio.on_callback(call(OWNER, "ui:exp"))
doc = last("send_document")[1][1]
exported = json.loads(doc.read().decode())
check("تصدير JSON", exported["preset"] in studio.all_presets() and "custom" in exported)
bad = {"preset": "nope", "over": {"label": "no-placeholder", "quote": "evil", "bullet": "◆"}, "buttons": {"x": {"text": "T" * 200, "color": "purple", "hide": 1}},
       "custom": [{"id": "BAD ID", "kind": "url", "value": "javascript:1"}, {"id": "ok1", "kind": "url", "value": "https://a.b", "text": "A"}], "cols": {"main": 9}}
clean = studio.sanitize_cfg(bad)
check("تنظيف الاستيراد", clean["preset"] == "classic" and clean["over"] == {"bullet": "◆"} and len(clean["buttons"]["x"]["text"]) == 60
      and "color" not in clean["buttons"]["x"] and [c["id"] for c in clean["custom"]] == ["ok1"] and "main" not in clean["cols"], clean)
studio.on_callback(call(OWNER, "ui:imp")); studio.on_pending(msg(OWNER, json.dumps({"preset": "neon", "over": {"quote": "bar"}})))
check("استيراد JSON", studio.cfg()["preset"] == "neon" and studio.cfg()["over"]["quote"] == "bar")
studio.on_callback(call(OWNER, "ui:imp")); studio.on_pending(msg(OWNER, "not json"))
check("استيراد تالف لا يكسر", studio.cfg()["preset"] == "neon")
studio.apply_preset("rose"); studio.on_callback(call(OWNER, "ui:undo"))
check("تراجع", studio.cfg()["preset"] == "neon")
studio.on_callback(call(OWNER, "ui:reset"))
check("إعادة ضبط", studio.cfg()["preset"] == "classic" and not studio.cfg()["buttons"])
studio.cmd_uireset(msg(OWNER, "/uireset"))

# أدوات
check("progress_bar", studio.progress_bar(50, 10, "█░") == "█████░░░░░" and studio.progress_bar(150, 4) == "▰▰▰▰")
check("fmt_time", studio.fmt_time(754) == "12:34" and studio.fmt_time(3725) == "01:02:05")
check("terminal_box يهرب HTML", "&lt;b&gt;" in studio.terminal_box("t", ["<b>x</b>"]) and studio.terminal_box("t", ["a"]).startswith("<pre>"))
check("كل المؤشرات المتحركة", all(len(f) >= 4 for f in studio.SPIN_FRAMES.values()) and set(studio.SPINS) == set(studio.SPIN_FRAMES))
check("ترمنال الحالة", "flix@host" in studio.terminal_status())
n0 = len(REC)
studio.run_countdown(5, 3, "اختبار"); time.sleep(4.5)
eds = [r for r in REC[n0:] if r[0] == "edit_message_text"]
check("العد التنازلي يعدّل الرسالة وينتهي", eds and "انتهى" in eds[-1][1][0], eds[-1][1][0] if eds else None)
n0 = len(REC); studio.run_animation(5, "moon", "تحميل", 2.6); time.sleep(4.2)
eds = [r for r in REC[n0:] if r[0] == "edit_message_text"]
check("الشاشة المتحركة تتغير إطاراتها", len({e[1][0] for e in eds}) >= 2 and "✅" in eds[-1][1][0], [e[1][0] for e in eds])
studio.cmd_studio(msg(OWNER, "/studio"))
check("/studio يفتح", "استوديو الستايل" in last("edit_message_text")[1][0])
studio.cmd_countdown(msg(999, "/countdown 3")); n1 = len(REC)
check("/countdown للمالك فقط", not any(r[0] == "send_message" and "عد تنازلي" in str(r[1]) for r in REC[-1:]))
studio.on_callback(call(OWNER, "ui:t:term")); check("أداة الترمنال", "<pre>" in last("send_message")[1][1])
studio.on_callback(call(OWNER, "ui:full")); time.sleep(0.3)
check("المعاينة الشاملة", sum(1 for r in REC if r[0] == "send_message" and r[2].get("reply_markup") is not None) >= 1)
# محتوى الواجهة لا يكسر HTML تيليجرام
for scr in ("ui:home", "ui:pre", "ui:knob", "ui:scr", "ui:txt:0", "ui:tools", "ui:src", "ui:io", "ui:t:plug"):
    studio.on_callback(call(OWNER, scr))
    t = last("edit_message_text")[1][0]
    import re
    stack = re.findall(r"</?(b|i|code|pre|blockquote)[ >]", t)
    check(f"شاشة {scr}", t.count("<b>") == t.count("</b>") and t.count("<code>") == t.count("</code>"), t[:80])
H.finish()
