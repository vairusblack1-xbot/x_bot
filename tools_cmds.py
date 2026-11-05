# -*- coding: utf-8 -*-
"""أوامر الأدوات: /diag /sysstats /analyze /top"""
import os


def install(core, root):
    import diagnostics, monitor, analyzer
    monitor.start(core)
    bot = core.bot

    @bot.message_handler(commands=["diag"])
    def cmd_diag(message):
        if core.msg_seen(message) or not core.is_admin(message.from_user.id):
            return
        rep = diagnostics.format_report(diagnostics.run_checks(root, core), html=True)
        bot.send_message(message.chat.id, ("🩺 <b>فحص الجاهزية</b>\n\n" + rep)[:4000])

    @bot.message_handler(commands=["sysstats", "top"])
    def cmd_sys(message):
        if core.msg_seen(message) or not core.is_admin(message.from_user.id):
            return
        bot.send_message(message.chat.id, monitor.summary_html()[:4000])

    @bot.message_handler(commands=["analyze"])
    def cmd_analyze(message):
        if core.msg_seen(message):
            return
        a = (message.text or "").split()
        if len(a) != 2 or not a[1].isdigit():
            return bot.send_message(message.chat.id, "الاستخدام: <code>/analyze رقم_المشروع</code>")
        pid = int(a[1])
        p = core.db_fetchone("SELECT user_id FROM projects WHERE id=?", (pid,))
        if not p or (p["user_id"] != message.from_user.id and not core.is_admin(message.from_user.id)):
            return bot.send_message(message.chat.id, "❌ لا تملك مشروعاً بهذا الرقم.")
        try:
            bot.send_message(message.chat.id, analyzer.analyze_project(core, pid)[:4000])
        except Exception as e:
            core.log.exception("analyze")
            bot.send_message(message.chat.id, f"❌ تعذر التحليل: {core.html_escape(str(e)[:200])}")
