# -*- coding: utf-8 -*-
"""
🎓 Telegram-бот для изучения билетов по программированию.
Режимы: просмотр, случайный билет, квиз, прогресс.
"""

import json
import logging
import os
import random
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from tickets_data import BLOCKS, TICKETS, BLOCK_TICKET_IDS

# ──────────────────── Logging ────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ──────────────────── Config ────────────────────
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DATA_DIR = Path(__file__).parent / "user_data"
DATA_DIR.mkdir(exist_ok=True)

# ──────────────────── User progress persistence ────────────────────

def _progress_path(user_id: int) -> Path:
    return DATA_DIR / f"{user_id}.json"


def load_progress(user_id: int) -> dict:
    path = _progress_path(user_id)
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {"learned": [], "quiz_correct": 0, "quiz_total": 0}


def save_progress(user_id: int, data: dict):
    with open(_progress_path(user_id), "w") as f:
        json.dump(data, f, ensure_ascii=False)


def get_ticket_by_id(ticket_id: int):
    for t in TICKETS:
        if t["id"] == ticket_id:
            return t
    return None

# ──────────────────── Keyboards ────────────────────

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Все билеты по блокам", callback_data="menu_blocks")],
        [InlineKeyboardButton("🎲 Случайный билет", callback_data="menu_random")],
        [InlineKeyboardButton("🧠 Квиз (проверь себя!)", callback_data="menu_quiz")],
        [InlineKeyboardButton("📊 Мой прогресс", callback_data="menu_progress")],
        [InlineKeyboardButton("🔥 Марафон (все 40)", callback_data="menu_marathon")],
        [InlineKeyboardButton("♻️ Сбросить прогресс", callback_data="menu_reset")],
    ])


def blocks_keyboard():
    buttons = []
    for key, block in BLOCKS.items():
        buttons.append([
            InlineKeyboardButton(
                f"{block['emoji']} {block['name']} ({block['range']})",
                callback_data=f"block_{key}",
            )
        ])
    buttons.append([InlineKeyboardButton("🔙 Главное меню", callback_data="menu_main")])
    return InlineKeyboardMarkup(buttons)


def ticket_list_keyboard(block_key: str):
    ticket_ids = BLOCK_TICKET_IDS[block_key]
    buttons = []
    row = []
    for tid in ticket_ids:
        t = get_ticket_by_id(tid)
        row.append(InlineKeyboardButton(f"#{tid}", callback_data=f"ticket_{tid}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 К блокам", callback_data="menu_blocks")])
    return InlineKeyboardMarkup(buttons)


def ticket_action_keyboard(ticket_id: int):
    buttons = [
        [
            InlineKeyboardButton("✅ Знаю!", callback_data=f"learned_{ticket_id}"),
            InlineKeyboardButton("🧠 Квиз", callback_data=f"quizticket_{ticket_id}"),
        ],
    ]
    # Navigation
    nav_row = []
    if ticket_id > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Пред.", callback_data=f"ticket_{ticket_id - 1}"))
    if ticket_id < 40:
        nav_row.append(InlineKeyboardButton("➡️ След.", callback_data=f"ticket_{ticket_id + 1}"))
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("🔙 Главное меню", callback_data="menu_main")])
    return InlineKeyboardMarkup(buttons)


def quiz_options_keyboard(ticket_id: int, options: list):
    buttons = []
    for i, opt in enumerate(options):
        buttons.append([
            InlineKeyboardButton(opt, callback_data=f"answer_{ticket_id}_{i}")
        ])
    return InlineKeyboardMarkup(buttons)

# ──────────────────── Format ticket ────────────────────

def format_ticket(ticket: dict, show_full: bool = True) -> str:
    block = BLOCKS[ticket["block"]]
    text = (
        f"{block['emoji']} <b>Билет #{ticket['id']}: {ticket['title']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    if show_full:
        text += f"💡 <b>Суть:</b> {ticket['short']}\n\n"
        text += f"{ticket['explanation']}\n"
        if ticket.get("code"):
            text += f"\n📝 <b>Пример кода:</b>\n{ticket['code']}\n"
    else:
        text += f"💡 {ticket['short']}\n"
    return text

# ──────────────────── Handlers ────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        f"🎓 Я бот для подготовки к экзамену по программированию.\n"
        f"У меня <b>40 билетов</b> по 3 блокам:\n\n"
        f"📐 Алгоритмы и логика (1–15)\n"
        f"🗄 Структуры данных и сложность (16–26)\n"
        f"🧩 ООП и JavaScript (27–40)\n\n"
        f"<b>Выбери режим:</b>"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=main_menu_keyboard(), parse_mode="HTML")
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu_keyboard(), parse_mode="HTML")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # ── Main menu ──
    if data == "menu_main":
        await start(update, context)

    # ── Blocks list ──
    elif data == "menu_blocks":
        text = "📚 <b>Выбери блок:</b>\n\n"
        for key, block in BLOCKS.items():
            count = len(BLOCK_TICKET_IDS[key])
            text += f"{block['emoji']} {block['name']} — {count} билетов\n"
        await query.edit_message_text(text, reply_markup=blocks_keyboard(), parse_mode="HTML")

    # ── Specific block ──
    elif data.startswith("block_"):
        block_key = data.replace("block_", "")
        block = BLOCKS[block_key]
        progress = load_progress(user_id)
        ticket_ids = BLOCK_TICKET_IDS[block_key]

        learned_in_block = len([tid for tid in ticket_ids if tid in progress["learned"]])
        text = (
            f"{block['emoji']} <b>{block['name']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Изучено: {learned_in_block}/{len(ticket_ids)}\n\n"
            f"Выбери билет:\n\n"
        )
        for tid in ticket_ids:
            t = get_ticket_by_id(tid)
            mark = "✅" if tid in progress["learned"] else "📝"
            text += f"{mark} <b>#{tid}</b> — {t['title']}\n"

        await query.edit_message_text(
            text, reply_markup=ticket_list_keyboard(block_key), parse_mode="HTML"
        )

    # ── View ticket ──
    elif data.startswith("ticket_"):
        ticket_id = int(data.replace("ticket_", ""))
        ticket = get_ticket_by_id(ticket_id)
        if ticket:
            text = format_ticket(ticket)
            await query.edit_message_text(
                text, reply_markup=ticket_action_keyboard(ticket_id), parse_mode="HTML"
            )

    # ── Mark as learned ──
    elif data.startswith("learned_"):
        ticket_id = int(data.replace("learned_", ""))
        progress = load_progress(user_id)
        if ticket_id not in progress["learned"]:
            progress["learned"].append(ticket_id)
            save_progress(user_id, progress)
            await query.answer("✅ Билет отмечен как изученный!", show_alert=True)
        else:
            progress["learned"].remove(ticket_id)
            save_progress(user_id, progress)
            await query.answer("❌ Билет снят с изученных", show_alert=True)
        # Refresh
        ticket = get_ticket_by_id(ticket_id)
        text = format_ticket(ticket)
        await query.edit_message_text(
            text, reply_markup=ticket_action_keyboard(ticket_id), parse_mode="HTML"
        )

    # ── Random ticket ──
    elif data == "menu_random":
        ticket = random.choice(TICKETS)
        text = "🎲 <b>Случайный билет!</b>\n\n" + format_ticket(ticket)
        await query.edit_message_text(
            text, reply_markup=ticket_action_keyboard(ticket["id"]), parse_mode="HTML"
        )

    # ── Quiz mode ──
    elif data == "menu_quiz":
        progress = load_progress(user_id)
        # Pick a random ticket that hasn't been learned
        unlearned = [t for t in TICKETS if t["id"] not in progress["learned"]]
        pool = unlearned if unlearned else TICKETS
        ticket = random.choice(pool)
        quiz = ticket["quiz"]

        text = (
            f"🧠 <b>Квиз! Билет #{ticket['id']}: {ticket['title']}</b>\n\n"
            f"❓ {quiz['question']}\n"
        )
        await query.edit_message_text(
            text,
            reply_markup=quiz_options_keyboard(ticket["id"], quiz["options"]),
            parse_mode="HTML",
        )

    # ── Quiz for specific ticket ──
    elif data.startswith("quizticket_"):
        ticket_id = int(data.replace("quizticket_", ""))
        ticket = get_ticket_by_id(ticket_id)
        quiz = ticket["quiz"]
        text = (
            f"🧠 <b>Квиз! Билет #{ticket['id']}: {ticket['title']}</b>\n\n"
            f"❓ {quiz['question']}\n"
        )
        await query.edit_message_text(
            text,
            reply_markup=quiz_options_keyboard(ticket["id"], quiz["options"]),
            parse_mode="HTML",
        )

    # ── Answer quiz ──
    elif data.startswith("answer_"):
        parts = data.split("_")
        ticket_id = int(parts[1])
        answer_idx = int(parts[2])
        ticket = get_ticket_by_id(ticket_id)
        quiz = ticket["quiz"]

        progress = load_progress(user_id)
        progress["quiz_total"] += 1

        if answer_idx == quiz["correct"]:
            progress["quiz_correct"] += 1
            save_progress(user_id, progress)
            text = (
                f"✅ <b>Правильно!</b> 🎉\n\n"
                f"Билет #{ticket_id}: <b>{ticket['title']}</b>\n"
                f"Ответ: <b>{quiz['options'][quiz['correct']]}</b>\n\n"
                f"📊 Статистика: {progress['quiz_correct']}/{progress['quiz_total']} "
                f"({progress['quiz_correct']*100//max(progress['quiz_total'],1)}%)"
            )
        else:
            save_progress(user_id, progress)
            text = (
                f"❌ <b>Неправильно!</b>\n\n"
                f"Билет #{ticket_id}: <b>{ticket['title']}</b>\n"
                f"Твой ответ: {quiz['options'][answer_idx]}\n"
                f"Правильный: <b>{quiz['options'][quiz['correct']]}</b>\n\n"
                f"📊 Статистика: {progress['quiz_correct']}/{progress['quiz_total']} "
                f"({progress['quiz_correct']*100//max(progress['quiz_total'],1)}%)"
            )

        buttons = [
            [InlineKeyboardButton("📖 Посмотреть билет", callback_data=f"ticket_{ticket_id}")],
            [InlineKeyboardButton("🧠 Ещё вопрос!", callback_data="menu_quiz")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="menu_main")],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
        )

    # ── Progress ──
    elif data == "menu_progress":
        progress = load_progress(user_id)
        total = len(TICKETS)
        learned = len(progress["learned"])
        pct = learned * 100 // max(total, 1)

        # Progress bar
        filled = pct // 5
        bar = "█" * filled + "░" * (20 - filled)

        text = (
            f"📊 <b>Твой прогресс</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📝 Билетов изучено: <b>{learned}/{total}</b>\n"
            f"[{bar}] {pct}%\n\n"
        )

        # Per block
        for key, block in BLOCKS.items():
            block_ids = BLOCK_TICKET_IDS[key]
            block_learned = len([tid for tid in block_ids if tid in progress["learned"]])
            block_pct = block_learned * 100 // max(len(block_ids), 1)
            b_filled = block_pct // 10
            b_bar = "█" * b_filled + "░" * (10 - b_filled)
            text += (
                f"{block['emoji']} {block['name']}\n"
                f"   [{b_bar}] {block_learned}/{len(block_ids)} ({block_pct}%)\n\n"
            )

        # Quiz stats
        q_total = progress["quiz_total"]
        q_correct = progress["quiz_correct"]
        q_pct = q_correct * 100 // max(q_total, 1) if q_total > 0 else 0
        text += (
            f"🧠 <b>Квиз:</b> {q_correct}/{q_total} правильных ({q_pct}%)\n\n"
        )

        if pct == 100:
            text += "🏆 <b>Поздравляю! Все билеты изучены!</b> 🎉\n"
        elif pct >= 75:
            text += "🔥 <b>Отлично! Ты почти готов!</b>\n"
        elif pct >= 50:
            text += "💪 <b>Хорошо! Больше половины!</b>\n"
        elif pct >= 25:
            text += "📚 <b>Неплохо! Продолжай!</b>\n"
        else:
            text += "🚀 <b>Давай начнём учить!</b>\n"

        buttons = [
            [InlineKeyboardButton("📚 Учить билеты", callback_data="menu_blocks")],
            [InlineKeyboardButton("🧠 Квиз", callback_data="menu_quiz")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="menu_main")],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
        )

    # ── Marathon ──
    elif data == "menu_marathon":
        progress = load_progress(user_id)
        unlearned = [t for t in TICKETS if t["id"] not in progress["learned"]]

        if not unlearned:
            text = (
                "🏆 <b>Все 40 билетов изучены!</b>\n\n"
                "Можешь сбросить прогресс и пройти заново, "
                "или пройти квиз для закрепления."
            )
            buttons = [
                [InlineKeyboardButton("🧠 Квиз", callback_data="menu_quiz")],
                [InlineKeyboardButton("♻️ Сбросить", callback_data="menu_reset")],
                [InlineKeyboardButton("🔙 Меню", callback_data="menu_main")],
            ]
        else:
            ticket = unlearned[0]
            remaining = len(unlearned)
            text = (
                f"🔥 <b>Марафон!</b> Осталось: {remaining} билетов\n\n"
                + format_ticket(ticket)
            )
            buttons = [
                [
                    InlineKeyboardButton("✅ Знаю!", callback_data=f"mlearn_{ticket['id']}"),
                    InlineKeyboardButton("🧠 Квиз", callback_data=f"quizticket_{ticket['id']}"),
                ],
                [InlineKeyboardButton("⏭ Пропустить", callback_data=f"mskip_{ticket['id']}")],
                [InlineKeyboardButton("🔙 Меню", callback_data="menu_main")],
            ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
        )

    # ── Marathon: learn ──
    elif data.startswith("mlearn_"):
        ticket_id = int(data.replace("mlearn_", ""))
        progress = load_progress(user_id)
        if ticket_id not in progress["learned"]:
            progress["learned"].append(ticket_id)
            save_progress(user_id, progress)
        # Continue marathon
        unlearned = [t for t in TICKETS if t["id"] not in progress["learned"]]
        if not unlearned:
            text = "🏆 <b>Марафон завершён! Все билеты изучены!</b> 🎉"
            buttons = [
                [InlineKeyboardButton("📊 Прогресс", callback_data="menu_progress")],
                [InlineKeyboardButton("🔙 Меню", callback_data="menu_main")],
            ]
        else:
            ticket = unlearned[0]
            remaining = len(unlearned)
            text = (
                f"✅ Отлично! Осталось: <b>{remaining}</b>\n\n"
                + format_ticket(ticket)
            )
            buttons = [
                [
                    InlineKeyboardButton("✅ Знаю!", callback_data=f"mlearn_{ticket['id']}"),
                    InlineKeyboardButton("🧠 Квиз", callback_data=f"quizticket_{ticket['id']}"),
                ],
                [InlineKeyboardButton("⏭ Пропустить", callback_data=f"mskip_{ticket['id']}")],
                [InlineKeyboardButton("🔙 Меню", callback_data="menu_main")],
            ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
        )

    # ── Marathon: skip ──
    elif data.startswith("mskip_"):
        ticket_id = int(data.replace("mskip_", ""))
        progress = load_progress(user_id)
        unlearned = [t for t in TICKETS if t["id"] not in progress["learned"]]
        # Find next after current
        current_idx = None
        for i, t in enumerate(unlearned):
            if t["id"] == ticket_id:
                current_idx = i
                break
        if current_idx is not None and current_idx + 1 < len(unlearned):
            ticket = unlearned[current_idx + 1]
        elif unlearned:
            ticket = unlearned[0]
        else:
            text = "🏆 <b>Марафон завершён!</b>"
            buttons = [[InlineKeyboardButton("🔙 Меню", callback_data="menu_main")]]
            await query.edit_message_text(
                text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
            )
            return

        remaining = len(unlearned)
        text = f"⏭ Пропущено. Осталось: <b>{remaining}</b>\n\n" + format_ticket(ticket)
        buttons = [
            [
                InlineKeyboardButton("✅ Знаю!", callback_data=f"mlearn_{ticket['id']}"),
                InlineKeyboardButton("🧠 Квиз", callback_data=f"quizticket_{ticket['id']}"),
            ],
            [InlineKeyboardButton("⏭ Пропустить", callback_data=f"mskip_{ticket['id']}")],
            [InlineKeyboardButton("🔙 Меню", callback_data="menu_main")],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
        )

    # ── Reset ──
    elif data == "menu_reset":
        text = (
            "⚠️ <b>Сбросить весь прогресс?</b>\n\n"
            "Это удалит все отметки «изучено» и статистику квиза."
        )
        buttons = [
            [InlineKeyboardButton("✅ Да, сбросить", callback_data="reset_confirm")],
            [InlineKeyboardButton("❌ Отмена", callback_data="menu_main")],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
        )

    elif data == "reset_confirm":
        save_progress(user_id, {"learned": [], "quiz_correct": 0, "quiz_total": 0})
        await query.answer("♻️ Прогресс сброшен!", show_alert=True)
        await start(update, context)


# ── /help command ──
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 <b>Команды бота:</b>\n\n"
        "/start — Главное меню\n"
        "/help — Эта справка\n"
        "/random — Случайный билет\n"
        "/quiz — Квиз\n"
        "/progress — Мой прогресс\n"
        "/ticket <i>номер</i> — Конкретный билет (1-40)\n\n"
        "<b>Режимы:</b>\n"
        "📚 <b>Блоки</b> — просматривай билеты по темам\n"
        "🎲 <b>Случайный</b> — билет наугад\n"
        "🧠 <b>Квиз</b> — проверь знания\n"
        "🔥 <b>Марафон</b> — пройди все 40 подряд\n"
        "📊 <b>Прогресс</b> — следи за успехами"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ── /random command ──
async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket = random.choice(TICKETS)
    text = "🎲 <b>Случайный билет!</b>\n\n" + format_ticket(ticket)
    await update.message.reply_text(
        text, reply_markup=ticket_action_keyboard(ticket["id"]), parse_mode="HTML"
    )


# ── /quiz command ──
async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    progress = load_progress(user_id)
    unlearned = [t for t in TICKETS if t["id"] not in progress["learned"]]
    pool = unlearned if unlearned else TICKETS
    ticket = random.choice(pool)
    quiz = ticket["quiz"]

    text = (
        f"🧠 <b>Квиз! Билет #{ticket['id']}: {ticket['title']}</b>\n\n"
        f"❓ {quiz['question']}\n"
    )
    await update.message.reply_text(
        text,
        reply_markup=quiz_options_keyboard(ticket["id"], quiz["options"]),
        parse_mode="HTML",
    )


# ── /progress command ──
async def progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Simulate the callback
    user_id = update.effective_user.id
    progress = load_progress(user_id)
    total = len(TICKETS)
    learned = len(progress["learned"])
    pct = learned * 100 // max(total, 1)

    filled = pct // 5
    bar = "█" * filled + "░" * (20 - filled)

    text = (
        f"📊 <b>Твой прогресс</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 Билетов изучено: <b>{learned}/{total}</b>\n"
        f"[{bar}] {pct}%\n\n"
    )
    for key, block in BLOCKS.items():
        block_ids = BLOCK_TICKET_IDS[key]
        block_learned = len([tid for tid in block_ids if tid in progress["learned"]])
        block_pct = block_learned * 100 // max(len(block_ids), 1)
        b_filled = block_pct // 10
        b_bar = "█" * b_filled + "░" * (10 - b_filled)
        text += (
            f"{block['emoji']} {block['name']}\n"
            f"   [{b_bar}] {block_learned}/{len(block_ids)} ({block_pct}%)\n\n"
        )

    q_total = progress["quiz_total"]
    q_correct = progress["quiz_correct"]
    q_pct = q_correct * 100 // max(q_total, 1) if q_total > 0 else 0
    text += f"🧠 <b>Квиз:</b> {q_correct}/{q_total} правильных ({q_pct}%)\n"

    buttons = [
        [InlineKeyboardButton("📚 Учить", callback_data="menu_blocks")],
        [InlineKeyboardButton("🧠 Квиз", callback_data="menu_quiz")],
    ]
    await update.message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
    )


# ── /ticket N command ──
async def ticket_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        try:
            ticket_id = int(context.args[0])
            if 1 <= ticket_id <= 40:
                ticket = get_ticket_by_id(ticket_id)
                text = format_ticket(ticket)
                await update.message.reply_text(
                    text,
                    reply_markup=ticket_action_keyboard(ticket_id),
                    parse_mode="HTML",
                )
                return
        except (ValueError, IndexError):
            pass
    await update.message.reply_text(
        "❌ Укажи номер билета от 1 до 40.\nПример: /ticket 15",
        parse_mode="HTML",
    )


# ── Text search ──
async def text_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.lower().strip()

    # Try to find by number
    if query_text.isdigit():
        tid = int(query_text)
        if 1 <= tid <= 40:
            ticket = get_ticket_by_id(tid)
            text = format_ticket(ticket)
            await update.message.reply_text(
                text, reply_markup=ticket_action_keyboard(tid), parse_mode="HTML"
            )
            return

    # Search by keyword
    results = []
    for t in TICKETS:
        searchable = f"{t['title']} {t['short']} {t['explanation']}".lower()
        if query_text in searchable:
            results.append(t)

    if results:
        text = f"🔍 Найдено <b>{len(results)}</b> билетов по запросу «{query_text}»:\n\n"
        buttons = []
        for t in results[:10]:
            text += f"• <b>#{t['id']}</b> — {t['title']}\n"
            buttons.append([
                InlineKeyboardButton(
                    f"#{t['id']} {t['title']}", callback_data=f"ticket_{t['id']}"
                )
            ])
        buttons.append([InlineKeyboardButton("🔙 Меню", callback_data="menu_main")])
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
        )
    else:
        text = (
            f"🤷 Ничего не найдено по запросу «{query_text}».\n"
            f"Попробуй другие ключевые слова или /start для главного меню."
        )
        await update.message.reply_text(text, parse_mode="HTML")


# ──────────────────── Main ────────────────────

def main():
    if not TOKEN:
        print("❌ Ошибка: установите переменную окружения TELEGRAM_BOT_TOKEN")
        print("   export TELEGRAM_BOT_TOKEN='ваш_токен_от_BotFather'")
        return

    app = Application.builder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("random", random_command))
    app.add_handler(CommandHandler("quiz", quiz_command))
    app.add_handler(CommandHandler("progress", progress_command))
    app.add_handler(CommandHandler("ticket", ticket_command))

    # Callback buttons
    app.add_handler(CallbackQueryHandler(button_handler))

    # Text search
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_search))

    print("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
