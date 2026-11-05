# -*- coding: utf-8 -*-
"""
إضافة تجريبية: أي ملف باسم plugin_*.py بجوار البوت يُحمَّل تلقائياً عند التشغيل.
يجب أن يحوي الدالة register(core, ui):
  core = وحدة النواة (core.bot, core.db_*, core.html_escape ...)
  ui   = وحدة الاستوديو (ui.run_countdown, ui.run_animation, ui.terminal_box, ui.progress_bar, ui.knobs ...)
"""


def register(core, ui):
    bot = core.bot

    @bot.message_handler(commands=["hello"])
    def hello(m):
        k = ui.knobs()
        bot.send_message(m.chat.id, f"{k['arrow']} أهلاً <b>{core.html_escape(m.from_user.first_name or '')}</b>\n{ui.progress_bar(70, 12, k['bar'])} 70%",
                         parse_mode="HTML")

    @bot.message_handler(commands=["timer"])
    def timer(m):
        parts = (m.text or "").split()
        secs = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
        ui.run_countdown(m.chat.id, min(secs, 300), "مؤقت")
