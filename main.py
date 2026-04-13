import telebot
from telebot import types
import random
import time
import sqlite3
import math
import re
from datetime import datetime

# === НАСТРОЙКИ ===
TOKEN = '8484938224:AAHHydNIcGcBBty61nUeZb_6QRz8ripnUIY'
ADMIN_IDS = [5379659751] 
MAX_AMOUNT = 100000
DB_PATH = 'kazino.db'
COOLDOWN_TIME_SECONDS = 5

last_bank_time = 0
BANK_COOLDOWN = 10

# === ИНИЦИАЛИЗАЦИЯ БД И ДОХОДОВ ===
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if cursor.fetchone() is None:
            conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, balance INTEGER, last_play_time TEXT, username TEXT)')

        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'last_play_time' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN last_play_time TEXT")
        if 'username' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
            
        conn.execute('CREATE TABLE IF NOT EXISTS income (id INTEGER PRIMARY KEY AUTOINCREMENT, amount INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
        conn.commit()

init_db()

# === КЕШИРОВАНИЕ ЮЗЕРОВ ===
def cache_user(user):
    """Сохраняет или обновляет юзернейм в базе"""
    if not user: return
    uid = user.id
    uname = user.username.lower() if user.username else None
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (id, balance) VALUES (?, ?)", (uid, 0))
        if uname:
            cur.execute("UPDATE users SET username = ? WHERE id = ?", (uname, uid))
        conn.commit()

def get_id_by_username(username):
    username = username.replace('@', '').lower()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        return row[0] if row else None

def add_income(amount):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO income (amount) VALUES (?)", (amount,))
        conn.commit()

def get_income_stats():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT SUM(amount) FROM income WHERE timestamp >= datetime('now', '-1 day')")
        day = cur.fetchone()[0] or 0
        cur.execute("SELECT SUM(amount) FROM income WHERE timestamp >= datetime('now', '-7 days')")
        week = cur.fetchone()[0] or 0
        cur.execute("SELECT SUM(amount) FROM income WHERE timestamp >= datetime('now', '-30 days')")
        month = cur.fetchone()[0] or 0
        cur.execute("SELECT SUM(amount) FROM income")
        all_time = cur.fetchone()[0] or 0
        return day, week, month, all_time

def get_user_data(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT balance, last_play_time FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        if row:
            balance = row[0]
            last_play_time_str = row[1]
            last_play_time = datetime.fromisoformat(last_play_time_str) if last_play_time_str else None
            return balance, last_play_time
        return 0, None

def set_user_data(user_id, balance, last_play_time=None):
    balance = max(0, int(balance))
    last_play_time_str = last_play_time.isoformat() if last_play_time else None
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (id, balance, last_play_time) VALUES (?, ?, ?)", (user_id, 0, None))
        cur.execute("UPDATE users SET balance = ?, last_play_time = ? WHERE id = ?", (balance, last_play_time_str, user_id))
        conn.commit()

def get_balance(user_id):
    balance, _ = get_user_data(user_id)
    return balance

def set_balance(user_id, amount):
    _, last_play_time = get_user_data(user_id)
    set_user_data(user_id, amount, last_play_time)

def is_admin(user_id):
    return user_id in ADMIN_IDS

def parse_amount(arg):
    try:
        value = int(arg)
        if 0 < value <= MAX_AMOUNT:
            return value
    except (ValueError, TypeError):
        return None

# === БОТ ===
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

def set_commands(bot_instance):
    commands = [
        types.BotCommand('start', '🚀 Запустить бота'),
        types.BotCommand('help', '📖 Справка'),
        types.BotCommand('bank', '🏦 Баланс казино'),
        types.BotCommand('play', '🎰 Рулетка'),
        types.BotCommand('bj', '🃏 Блэкджек'),
        types.BotCommand('mines', '💣 Минное поле'),
        types.BotCommand('ttt', '⭕️ Крестики-нолики (дуэль)'),
        types.BotCommand('cube', '🎲 Кубик'),
        types.BotCommand('rps', '🪨 КНБ'),
        types.BotCommand('balance', '💰 Баланс'),
        types.BotCommand('chet', '💱 Из баксов в фишки'),
        types.BotCommand('sell', '💹 Из фишек в баксы'),
        types.BotCommand('out', '💸 Вывести в $'),
        types.BotCommand('income', '📈 [Админ] Доходы'),
        types.BotCommand('delincome', '📉 [Админ] Убрать доход')
    ]
    bot_instance.set_my_commands(commands)

def safe_api_call(method, *args, **kwargs):
    while True:
        try:
            return method(*args, **kwargs)
        except telebot.apihelper.ApiTelegramException as e:
            if e.error_code == 429:
                retry_after = e.result_json.get('parameters', {}).get('retry_after', 5)
                time.sleep(retry_after + 1)
            elif "message is not modified" in str(e).lower():
                return None
            else:
                if "unexpected keyword argument" in str(e).lower(): return None 
                else: raise 
        except Exception:
            raise

@bot.message_handler(commands=['help'])
def help_cmd(message):
    cache_user(message.from_user)
    text = (
        "📖 <b>Справка по казино</b>\n\n"
        "💵 <b>Как купить фишки:</b>\n"
        "Надо перевести точную сумму, @LomanTTGG\n"
        "Пример:<code>/pay @LomanTTGG [сумма]</code>\n"
        "<i>(1 фишка = 50$. Минимальная сумма 50$)</i>. Бот автоматически зачислит фишки на твой баланс в казино.\n\n"
        "💸 <b>Как вывести фишки:</b>\n"
        "Используй команду <code>/out [кол-во фишек]</code>. Вам выпишут чек в $.\n\n"
        "💱 <b>Конвертация:</b>\n"
        "<code>/chet [сумма в $]</code> — узнать, сколько фишек ты получишь за доллары.\n"
        "<code>/sell [кол-во фишек]</code> — узнать, сколько долларов ты получишь за фишки.\n\n"
        "🎮 <b>Дуэли (Крестики-Нолики):</b>\n"
        "Вызов ответом: <code>/ttt [ставка]</code> (ответь на сообщение игрока)\n"
        "Вызов по тегу: <code>/ttt @username [ставка]</code>\n"
        "Вызов по ID: <code>/ttt 123456 [ставка]</code>\n\n"
        "🏦 <b>Информация:</b>\n"
        "<code>/bank</code> — баланс самого казино."
    )
    safe_api_call(bot.send_message, message.chat.id, text, message_thread_id=message.message_thread_id)

@bot.message_handler(commands=['balance'])
def balance_cmd(message):
    cache_user(message.from_user)
    user_id = message.from_user.id
    balance = get_balance(user_id)
    safe_api_call(bot.reply_to, message, f"💰 Баланс: <b>{balance}</b> фишек.")

@bot.message_handler(commands=['bank'])
def bank_cmd(message):
    cache_user(message.from_user)
    global last_bank_time
    current_time = time.time()
    if current_time - last_bank_time < BANK_COOLDOWN:
        wait_time = int(BANK_COOLDOWN - (current_time - last_bank_time))
        return safe_api_call(bot.reply_to, message, f"⏳ Подождите еще {wait_time} сек.")
    last_bank_time = current_time
    msg_wait = safe_api_call(bot.reply_to, message, "⏳ Узнаю баланс казино у Роксаны...")
    if msg_wait:
        safe_api_call(bot.send_message, ADMIN_IDS[0], f"Банк {message.chat.id} {msg_wait.message_id}")

@bot.message_handler(commands=['out'])
def out_chips(message):
    cache_user(message.from_user)
    args = message.text.split()
    if len(args) != 2:
        return safe_api_call(bot.reply_to, message, "📌 Пример: /out 1 (где 1 фишка = 50$)")
    chips = parse_amount(args[1])
    if not chips: return safe_api_call(bot.reply_to, message, "❌ Укажите целое число фишек.")
    
    user_id = message.from_user.id
    balance = get_balance(user_id)
    if chips > balance: return safe_api_call(bot.reply_to, message, f"❌ Недостаточно фишек. Баланс: {balance}")
    
    set_balance(user_id, balance - chips)
    usd_amount = chips * 50
    msg_wait = safe_api_call(bot.reply_to, message, f"⏳ Запрос на вывод {chips} фишек ({usd_amount}$) отправлен!\nОжидаем подтверждения от банка...")
    
    if not msg_wait:
        set_balance(user_id, balance)
        return
    safe_api_call(bot.send_message, ADMIN_IDS[0], f"Вывод {usd_amount}$ {user_id} {message.chat.id} {msg_wait.message_id}")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.chat.type == 'private' and m.reply_to_message)
def handle_admin_reply(message):
    original_text = message.reply_to_message.text
    if not original_text: return
    if original_text.startswith("Вывод"):
        parts = original_text.split()
        if len(parts) >= 5: 
            try:
                usd_amount = int(parts[1].replace('$', ''))
                target_user_id = int(parts[2])
                chat_id = int(parts[3])
                wait_msg_id = int(parts[4])
                if "❌" in message.text:
                    chips_to_refund = usd_amount // 50
                    set_balance(target_user_id, get_balance(target_user_id) + chips_to_refund)
                    error_text = f"❌ <b>Ошибка вывода!</b>\n\nПричина: {message.text}\n\n<i>{chips_to_refund} фишек возвращено.</i>"
                    try: safe_api_call(bot.edit_message_text, error_text, chat_id=chat_id, message_id=wait_msg_id)
                    except: safe_api_call(bot.send_message, chat_id, error_text, reply_to_message_id=wait_msg_id)
                    safe_api_call(bot.reply_to, message, "✅ Пользователь уведомлен об ошибке.")
                else:
                    match = re.search(r'#(\d+)', message.text)
                    if match:
                        instructions = f"<i>Чтоб забрать чек, скопируйте команду ниже:</i>\n<code>/accept {match.group(1)}</code>"
                    else:
                        instructions = "<i>Для принятия чека используйте команду /accept и его номер.</i>"
                    user_msg = f"✅ <b>Ваши деньги ({usd_amount}$) были успешно выведены!</b>\n\n{message.text}\n\n{instructions}"
                    try: safe_api_call(bot.edit_message_text, user_msg, chat_id=chat_id, message_id=wait_msg_id)
                    except: safe_api_call(bot.send_message, chat_id, user_msg, reply_to_message_id=wait_msg_id)
                    safe_api_call(bot.reply_to, message, "✅ Чек выдан.")
            except Exception as e: safe_api_call(bot.reply_to, message, f"❌ Ошибка: {e}")
                
    elif original_text.startswith("Банк"):
        parts = original_text.split()
        if len(parts) >= 3:
            try:
                chat_id, wait_msg_id = int(parts[1]), int(parts[2])
                try: safe_api_call(bot.edit_message_text, message.text, chat_id=chat_id, message_id=wait_msg_id)
                except: safe_api_call(bot.send_message, chat_id, message.text, reply_to_message_id=wait_msg_id)
                safe_api_call(bot.reply_to, message, "✅ Баланс передан.")
            except Exception as e: safe_api_call(bot.reply_to, message, f"❌ Ошибка: {e}")

# АДМИН-КОМАНДЫ
@bot.message_handler(commands=['get'])
def add_chips_from_userbot(message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()
        chips_to_add, target_user_id = int(args[1]), int(args[2])
        set_balance(target_user_id, get_balance(target_user_id) + chips_to_add)
        if chips_to_add > 0: add_income(chips_to_add)
        bot.reply_to(message, f"✅ Игроку {target_user_id} выдано {chips_to_add} фишек. (Учтено в доходах)")
    except: bot.reply_to(message, "❌ Формат: /get <кол-во> <айди>")

@bot.message_handler(commands=['income'])
def show_income(message):
    if not is_admin(message.from_user.id): return
    day, week, month, all_time = get_income_stats()
    text = f"📈 <b>Статистика доходов:</b>\n24 часа: <b>{day}</b>\nНеделя: <b>{week}</b>\nМесяц: <b>{month}</b>\nВсе время: <b>{all_time}</b>"
    safe_api_call(bot.reply_to, message, text)

@bot.message_handler(commands=['delincome'])
def remove_income(message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) != 2:
        return safe_api_call(bot.reply_to, message, "❗ Пример: /delincome 800 (уберет 800 фишек из статистики)")
    try:
        amount = int(args[1])
        if amount <= 0: raise ValueError
        add_income(-amount) 
        safe_api_call(bot.reply_to, message, f"✅ Вычтено {amount} фишек из статистики.")
    except: safe_api_call(bot.reply_to, message, "❌ Сумма должна быть положительным числом.")

@bot.message_handler(commands=['del'])
def modify_balance(message):
    if not is_admin(message.from_user.id): return
    if not message.reply_to_message: return safe_api_call(bot.reply_to, message, "⚠️ Ответьте на сообщение пользователя.")
    try:
        amount = int(message.text.split()[1])
        if amount <= 0: raise ValueError
        uid = message.reply_to_message.from_user.id
        set_balance(uid, max(0, get_balance(uid) - amount))
        safe_api_call(bot.send_message, message.chat.id, f"✅ Забрал {amount} фишек", message_thread_id=message.message_thread_id)
    except: safe_api_call(bot.reply_to, message, "❌ Ошибка. Пример: /del 10")

@bot.message_handler(commands=['chet'])
def usd_to_chips(message):
    args = message.text.split()
    if len(args) != 2:
        return safe_api_call(bot.reply_to, message, "📌 Пример: <code>/chet 100</code> (где 100 - это доллары)")
    try:
        usd = float(args[1])
        chips = int(usd / 50)
        safe_api_call(bot.reply_to, message, f"💸 {usd:,.2f}$ = {chips:,} фишек".replace(',', ' '))
    except ValueError:
        safe_api_call(bot.reply_to, message, "❌ Укажите число.")

@bot.message_handler(commands=['sell'])
def sell_chips(message):
    args = message.text.split()
    if len(args) != 2:
        return safe_api_call(bot.reply_to, message, "📌 Пример: <code>/sell 10</code> (где 10 - это фишки)")
    try:
        chips = int(args[1])
        usd = chips * 50
        safe_api_call(bot.reply_to, message, f"💵 {chips:,} фишек = {usd:,}$".replace(',', ' '))
    except ValueError:
        safe_api_call(bot.reply_to, message, "❌ Укажите число.")

# СТАРТ И МЕНЮ
@bot.message_handler(commands=['start'])
def start(message):
    cache_user(message.from_user)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎰 Рулетка", callback_data="play_info"),
        types.InlineKeyboardButton("🃏 Блэкджек", callback_data="bj_info"),
        types.InlineKeyboardButton("💣 Минное поле", callback_data="mines_info"),
        types.InlineKeyboardButton("⭕️ Крестики-нолики", callback_data="ttt_info"),
        types.InlineKeyboardButton("🎲 Кубик", callback_data="cube_info"),
        types.InlineKeyboardButton("🪨 КНБ", callback_data="rps_info"),
        types.InlineKeyboardButton("💰 Баланс", callback_data="balance")
    )
    safe_api_call(bot.reply_to, message, f"👋 Привет, <b>{message.from_user.first_name}</b>!\nЭто <b>Казино-бот</b>. Выбери игру:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ['balance', 'play_info', 'bj_info', 'mines_info', 'ttt_info', 'cube_info', 'rps_info'])
def main_callback_handler(call):
    cache_user(call.from_user)
    if call.message.reply_to_message and call.from_user.id != call.message.reply_to_message.from_user.id:
        return safe_api_call(bot.answer_callback_query, call.id, "❌ Это меню вызывал другой игрок!", show_alert=True)
    
    cid, tid = call.message.chat.id, call.message.message_thread_id
    safe_api_call(bot.answer_callback_query, call.id)

    if call.data == "balance": safe_api_call(bot.send_message, cid, f"💰 Баланс: <b>{get_balance(call.from_user.id)}</b> фишек.", message_thread_id=tid)
    elif call.data == "play_info": safe_api_call(bot.send_message, cid, "🎰 <b>Рулетка</b>\nПиши <code>/play [ставка]</code>", message_thread_id=tid)
    elif call.data == 'bj_info': safe_api_call(bot.send_message, cid, "🃏 <b>Блэкджек</b>\nПиши <code>/bj [ставка]</code>", message_thread_id=tid)
    elif call.data == 'mines_info': safe_api_call(bot.send_message, cid, "💣 <b>Минное поле</b>\nПиши <code>/mines [ставка]</code>", message_thread_id=tid)
    elif call.data == 'ttt_info': safe_api_call(bot.send_message, cid, "⭕️ <b>Крестики-нолики (PvP)</b>\nВызов игрока: <code>/ttt @username [ставка]</code> или реплай.", message_thread_id=tid)
    elif call.data == 'cube_info': safe_api_call(bot.send_message, cid, "🎲 <b>Кубик</b>\nПиши <code>!к [ставка]</code> или <code>/cube [ставка]</code>", message_thread_id=tid)
    elif call.data == 'rps_info': safe_api_call(bot.send_message, cid, "🪨 <b>КНБ</b>\nПиши <code>/rps [ставка] [камень/ножницы/бумага]</code>", message_thread_id=tid)

# === КРЕСТИКИ-НОЛИКИ (PvP ЦЕЛЕВЫЕ) ===
ttt_lobbies = {}
ttt_games = {}

def check_ttt_win(b):
    for c in [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]:
        if b[c[0]] != ' ' and b[c[0]] == b[c[1]] == b[c[2]]: return b[c[0]]
    if ' ' not in b: return 'draw'
    return None

def get_ttt_keyboard(game_id, disabled=False):
    game = ttt_games.get(game_id)
    if not game: return types.InlineKeyboardMarkup()
    markup = types.InlineKeyboardMarkup(row_width=3)
    buttons = []
    for i, cell in enumerate(game['board']):
        text = '❌' if cell == 'x' else ('⭕️' if cell == 'o' else '⬜️')
        cb_data = f"ttt_move_{game_id}_{i}" if not disabled else "ignore"
        buttons.append(types.InlineKeyboardButton(text, callback_data=cb_data))
    markup.add(*buttons)
    return markup

def render_ttt(chat_id, message_id, game_id):
    game = ttt_games[game_id]
    turn_mark = '❌' if game['turn'] == 'x' else '⭕️'
    text = f"⭕️❌ <b>Крестики-Нолики</b> | Банк: {game['bet']*2}\n\n❌ Игрок: {game['x_name']}\n⭕️ Игрок: {game['o_name']}\n\nСейчас ходит: {turn_mark}"
    safe_api_call(bot.edit_message_text, text, chat_id, message_id, reply_markup=get_ttt_keyboard(game_id))

@bot.message_handler(commands=['ttt', 'xo'])
def ttt_cmd(message):
    cache_user(message.from_user)
    args = message.text.split()
    host_id = message.from_user.id
    host_name = message.from_user.first_name
    
    target_id = None
    target_name = None
    bet = None
    target_identifier = None

    for arg in args[1:]:
        parsed = parse_amount(arg)
        if parsed is not None:
            bet = parsed
        else:
            target_identifier = arg

    if not bet: 
        return safe_api_call(bot.reply_to, message, f"❌ Ставка должна быть числом от 1 до {MAX_AMOUNT}.")

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        cache_user(target_user)
        target_id = target_user.id
        target_name = target_user.first_name
        if target_user.is_bot: 
            return safe_api_call(bot.reply_to, message, "❌ Нельзя вызывать бота на дуэль!")
    else:
        if not target_identifier:
            return safe_api_call(bot.reply_to, message, "⚠️ Пример:\n<code>/ttt @username 100</code>\n<code>/ttt 100 @username</code>\n<code>/ttt 12345678 100</code>\nИли ответьте на чужое сообщение: <code>/ttt 100</code>")
        
        if target_identifier.startswith('@'):
            uname = target_identifier.replace('@', '').lower()
            target_id = get_id_by_username(uname)
            if not target_id: 
                return safe_api_call(bot.reply_to, message, f"❌ Игрок {target_identifier} не найден в базе. Пусть он напишет боту любое сообщение.")
            target_name = target_identifier
        elif target_identifier.isdigit():
            target_id = int(target_identifier)
            target_name = f"ID: {target_id}"
        else:
            return safe_api_call(bot.reply_to, message, "❌ Неверный формат игрока. Укажите @username или ID.")

    if target_id == host_id: 
        return safe_api_call(bot.reply_to, message, "❌ С собой играть нельзя!")
    
    balance = get_balance(host_id)
    if balance < bet: 
        return safe_api_call(bot.reply_to, message, f"❌ У тебя недостаточно фишек. Твой баланс: {balance}")

    target_balance = get_balance(target_id)
    if target_balance < bet:
        return safe_api_call(bot.reply_to, message, f"❌ У противника ({target_name}) недостаточно фишек для такой ставки! Баланс противника: {target_balance}")

    set_balance(host_id, balance - bet)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Принять", callback_data=f"ttacc_{bet}_{host_id}_{target_id}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data=f"ttdec_{bet}_{host_id}_{target_id}")
    )
    
    msg = safe_api_call(bot.reply_to, message, f"⭕️❌ <b>Вызов на дуэль!</b>\n\n<b>{host_name}</b> вызывает {target_name}!\n💰 Ставка: {bet} фишек\n\nОжидаем подтверждения...", reply_markup=markup)
    if msg: ttt_lobbies[msg.message_id] = {'host_name': host_name, 'target_name': target_name}

@bot.callback_query_handler(func=lambda call: call.data.startswith('ttacc_'))
def ttt_accept(call):
    cache_user(call.from_user)
    _, bet_str, host_id_str, target_id_str = call.data.split('_')
    bet, host_id, target_id = int(bet_str), int(host_id_str), int(target_id_str)
    
    if call.from_user.id != target_id: 
        return safe_api_call(bot.answer_callback_query, call.id, "❌ Этот вызов не для тебя!", show_alert=True)
        
    t_bal = get_balance(target_id)
    if t_bal < bet: 
        return safe_api_call(bot.answer_callback_query, call.id, "💰 Недостаточно фишек для принятия ставки!", show_alert=True)
        
    set_balance(target_id, t_bal - bet)
    
    lobby = ttt_lobbies.pop(call.message.message_id, {})
    host_name = lobby.get('host_name', "Игрок 1")
    target_name = call.from_user.first_name
    
    players = [
        {'id': host_id, 'name': host_name},
        {'id': target_id, 'name': target_name}
    ]
    random.shuffle(players) 
    
    game_id = f"{call.message.chat.id}|{call.message.message_id}"
    ttt_games[game_id] = {
        'x': players[0]['id'], 
        'x_name': players[0]['name'], 
        'o': players[1]['id'], 
        'o_name': players[1]['name'], 
        'turn': 'x', 
        'board': [' ']*9, 
        'bet': bet
    }
    
    safe_api_call(bot.answer_callback_query, call.id, "✅ Дуэль началась!")
    render_ttt(call.message.chat.id, call.message.message_id, game_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ttdec_'))
def ttt_decline(call):
    _, bet_str, host_id_str, target_id_str = call.data.split('_')
    bet, host_id, target_id = int(bet_str), int(host_id_str), int(target_id_str)
    
    if call.from_user.id not in (host_id, target_id):
        return safe_api_call(bot.answer_callback_query, call.id, "❌ Вы не можете отменить этот вызов!", show_alert=True)
        
    set_balance(host_id, get_balance(host_id) + bet)
    ttt_lobbies.pop(call.message.message_id, None)
    
    who_canceled = "Игрок отменил вызов" if call.from_user.id == host_id else "Противник отклонил вызов"
    safe_api_call(bot.edit_message_text, f"❌ {who_canceled}. Ставка возвращена.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ttt_move_'))
def ttt_move(call):
    cache_user(call.from_user)
    _, _, game_id, pos_str = call.data.split('_')
    pos = int(pos_str)
    game = ttt_games.get(game_id)
    if not game: return safe_api_call(bot.answer_callback_query, call.id, "Игра завершена.", show_alert=True)
        
    current_turn_id = game['x'] if game['turn'] == 'x' else game['o']
    if call.from_user.id != current_turn_id: return safe_api_call(bot.answer_callback_query, call.id, "Сейчас не ваш ход!", show_alert=True)
    if game['board'][pos] != ' ': return safe_api_call(bot.answer_callback_query, call.id, "Клетка занята!", show_alert=True)
        
    game['board'][pos] = game['turn']
    winner = check_ttt_win(game['board'])
    
    if winner:
        if winner == 'draw':
            set_balance(game['x'], get_balance(game['x']) + game['bet'])
            set_balance(game['o'], get_balance(game['o']) + game['bet'])
            text = f"⭕️❌ <b>Крестики-Нолики</b>\n🤝 <b>Ничья!</b> Фишки возвращены.\n\n❌ {game['x_name']} против ⭕️ {game['o_name']}"
        else:
            win_id = game['x'] if winner == 'x' else game['o']
            win_name = game['x_name'] if winner == 'x' else game['o_name']
            win_amount = game['bet'] * 2
            set_balance(win_id, get_balance(win_id) + win_amount)
            text = f"⭕️❌ <b>Крестики-Нолики</b>\n🎉 Победитель: <b>{win_name}</b> (+{win_amount} фишек)!\n\n❌ {game['x_name']} против ⭕️ {game['o_name']}"
        
        safe_api_call(bot.edit_message_text, text, call.message.chat.id, call.message.message_id, reply_markup=get_ttt_keyboard(game_id, True))
        del ttt_games[game_id]
        return
        
    game['turn'] = 'o' if game['turn'] == 'x' else 'x'
    render_ttt(call.message.chat.id, call.message.message_id, game_id)

@bot.callback_query_handler(func=lambda call: call.data == 'ignore')
def ttt_ignore(call): safe_api_call(bot.answer_callback_query, call.id)

# === ОСТАЛЬНЫЕ ИГРЫ (СЛОТЫ, МИНЫ, КУБИК, КНБ, БДЖ) ===
@bot.message_handler(commands=['play'])
def play(message):
    cache_user(message.from_user)
    user_id = message.from_user.id
    args = message.text.split()
    balance = get_balance(user_id)
    if len(args) != 2: return safe_api_call(bot.reply_to, message, "⚠️ Пример: /play 100")
    bet = parse_amount(args[1])
    if not bet: return safe_api_call(bot.reply_to, message, f"❌ Ставка от 1 до {MAX_AMOUNT}")
    if bet > balance: return safe_api_call(bot.reply_to, message, f"❌ Недостаточно фишек. Баланс: {balance}")

    set_balance(user_id, balance - bet)
    dice_msg = safe_api_call(bot.send_dice, message.chat.id, emoji='🎰', message_thread_id=message.message_thread_id)
    time.sleep(2.5)

    v = dice_msg.dice.value - 1
    r1, r2, r3 = v % 4, (v // 4) % 4, (v // 16) % 4
    symbols = {0: 'BAR', 1: '🍒', 2: '🍋', 3: '7️⃣'}
    s1, s2, s3 = symbols[r1], symbols[r2], symbols[r3]
    
    multiplier = 0.0
    if s1 == s2 == s3: multiplier = {'BAR': 4.0, '🍋': 3.0, '🍒': 6.0, '7️⃣': 10.0}[s1]
    elif s1 == s2 and s3 != s1: multiplier = {'BAR': 2.0, '🍋': 2.0, '🍒': 3.0, '7️⃣': 3.0}[s1]

    if multiplier > 0:
        win_amount = int(bet * multiplier)
        set_balance(user_id, get_balance(user_id) + win_amount)
        result_text = f"🎉 <b>Вы выиграли!</b>\n\nКомбинация: [ {s1} | {s2} | {s3} ]\nМножитель: <b>x{multiplier}</b>\nВыигрыш: <b>+{win_amount}</b>\n💰 Баланс: <b>{get_balance(user_id)}</b>"
    else:
        result_text = f"😞 <b>Проигрыш...</b>\n\nКомбинация: [ {s1} | {s2} | {s3} ]\nПроиграно: <b>-{bet}</b>\n💰 Баланс: <b>{get_balance(user_id)}</b>"
    safe_api_call(bot.reply_to, message, result_text)

# === МИНЫ ===
active_mines_games = {}
def get_mines_mult(n, s): return round((1.0 / (math.comb(9-n, s) / math.comb(9, s))) * 0.95, 2) if s > 0 else 1.0

@bot.message_handler(commands=['mines'])
def mines_cmd(message):
    cache_user(message.from_user)
    if message.from_user.id in active_mines_games: return safe_api_call(bot.reply_to, message, "‼️ Заверши текущую игру!")
    args = message.text.split()
    if len(args) != 2: return safe_api_call(bot.reply_to, message, "⚠️ Пример: <code>/mines 100</code>")
    bet = parse_amount(args[1])
    if not bet or bet > get_balance(message.from_user.id): return safe_api_call(bot.reply_to, message, "❌ Ошибка ставки или нехватка фишек.")
    
    markup = types.InlineKeyboardMarkup(row_width=4)
    markup.add(*[types.InlineKeyboardButton(f"{i} 💣", callback_data=f"m_s_{i}_{bet}") for i in range(1, 9)])
    
    info_text = (
        f"💣 <b>Минное поле</b>\n"
        f"Ставка: <b>{bet}</b> фишек.\n\n"
        f"👇 <i>Выбери количество мин, которые будут спрятаны на поле. "
        f"Чем больше мин ты выберешь, тем выше будет коэффициент выигрыша за каждую открытую безопасную ячейку, "
        f"но и шанс подорваться возрастет!</i>\n\n"
        f"Сколько мин прячем?"
    )
    safe_api_call(bot.reply_to, message, info_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('m_s_'))
def mines_setup(call):
    cache_user(call.from_user)
    
    if call.message.reply_to_message and call.from_user.id != call.message.reply_to_message.from_user.id:
        return safe_api_call(bot.answer_callback_query, call.id, "❌ Это не ваша игра!", show_alert=True)

    try:
        data_parts = call.data.split('_')
        n = int(data_parts[2])    
        bet = int(data_parts[3])  
        uid = call.from_user.id
    except (IndexError, ValueError):
        return safe_api_call(bot.answer_callback_query, call.id, "❌ Ошибка данных игры.", show_alert=True)
    
    bal = get_balance(uid)
    if bet > bal: 
        return safe_api_call(bot.answer_callback_query, call.id, "💰 Недостаточно фишек!", show_alert=True)
    
    set_balance(uid, bal - bet)
    
    # Генерируем случайные позиции мин (3x3 поле). Правильный вариант!
    pos = set()
    while len(pos) < n:
        pos.add((random.randint(0, 2), random.randint(0, 2)))
    
    active_mines_games[uid] = {
        'bet': bet, 
        'n': n, 
        'b': [['.']*3 for _ in range(3)], 
        'pos': list(pos), 
        's': 0, 
        'win': float(bet), 
        'over': False, 
        'mid': call.message.message_id
    }
    
    safe_api_call(bot.answer_callback_query, call.id)
    render_mines(call.message.chat.id, call.message.message_id, uid)

def render_mines(chat_id, message_id, uid):
    g = active_mines_games.get(uid)
    if not g: return
    markup = types.InlineKeyboardMarkup()
    for r in range(3):
        row = []
        for c in range(3):
            cell = g['b'][r][c]
            cb = f"m_c_{r}_{c}" if not g['over'] and cell == '.' else "ignore"
            btn = '✅' if cell == 'O' else ('💥' if cell == 'X' else ('💣' if cell == 'M' else '⬜️'))
            row.append(types.InlineKeyboardButton(btn, callback_data=cb))
        markup.row(*row)
    if g['win'] > g['bet'] and not g['over']: markup.add(types.InlineKeyboardButton(f"💰 Забрать {int(g['win'])}", callback_data="m_cash"))
    
    txt = f"💣 <b>Мин:</b> {g['n']} | <b>Ставка:</b> {g['bet']}\nОткрыто: {g['s']} | Икс: <b>x{get_mines_mult(g['n'], g['s']):.2f}</b>\nНа вывод: <b>{int(g['win'])}</b>\n\n"
    if g['over']: txt += "💥 <b>Подорвался!</b>" if 'X' in sum(g['b'], []) else "✅ <b>Успешный вывод!</b>"
    safe_api_call(bot.edit_message_text, txt, chat_id, message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('m_c_') or call.data == 'm_cash')
def mines_play(call):
    uid = call.from_user.id
    g = active_mines_games.get(uid)
    if not g or g['mid'] != call.message.message_id: return
    
    if call.data == 'm_cash':
        set_balance(uid, get_balance(uid) + int(g['win']))
        g['over'] = True
        render_mines(call.message.chat.id, call.message.message_id, uid)
        del active_mines_games[uid]
        return

    r, c = int(call.data.split('_')[2]), int(call.data.split('_')[3])
    if (r, c) in g['pos']:
        g['b'][r][c] = 'X'; g['over'] = True
        for mr, mc in g['pos']:
            if (mr, mc) != (r, c): g['b'][mr][mc] = 'M'
        render_mines(call.message.chat.id, call.message.message_id, uid)
        del active_mines_games[uid]
    else:
        g['b'][r][c] = 'O'; g['s'] += 1
        g['win'] = g['bet'] * get_mines_mult(g['n'], g['s'])
        if g['s'] == 9 - g['n']:
            set_balance(uid, get_balance(uid) + int(g['win']))
            g['over'] = True
            render_mines(call.message.chat.id, call.message.message_id, uid)
            del active_mines_games[uid]
        else:
            render_mines(call.message.chat.id, call.message.message_id, uid)

# === КУБИК И КНБ ===
@bot.message_handler(func=lambda m: m.text and (m.text.lower().startswith('/cube') or m.text.lower().startswith('!к')))
def cube_game(message):
    cache_user(message.from_user)
    args = message.text.split()
    if len(args) < 2: return safe_api_call(bot.reply_to, message, "⚠️ Пример: <code>!к 100</code> или <code>/cube 100</code>")
    bet, uid = parse_amount(args[1]), message.from_user.id
    if not bet or bet > get_balance(uid): return safe_api_call(bot.reply_to, message, "❌ Ошибка ставки.")
    set_balance(uid, get_balance(uid) - bet)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🎯 Точечно (4x)", callback_data=f"c_t_ex_{bet}"), types.InlineKeyboardButton("⚖️ Чет / Нечет (2x)", callback_data=f"c_t_eo_{bet}"))
    safe_api_call(bot.reply_to, message, f"🎲 <b>Кубик</b>\nТвоя ставка: {bet}\nВыбери режим:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('c_t_'))
def cube_type(call):
    if call.message.reply_to_message and call.from_user.id != call.message.reply_to_message.from_user.id: return
    mode, bet = call.data.split('_')[2], int(call.data.split('_')[3])
    markup = types.InlineKeyboardMarkup()
    if mode == 'ex':
        buttons = [types.InlineKeyboardButton(str(i), callback_data=f"c_r_ex_{bet}_{i}") for i in range(1, 7)]
        markup.add(*buttons[:3]); markup.add(*buttons[3:])
        txt = "🎯 Угадай число (4x):"
    else:
        markup.add(types.InlineKeyboardButton("Чет (2,4,6)", callback_data=f"c_r_eo_{bet}_e"), types.InlineKeyboardButton("Нечет (1,3,5)", callback_data=f"c_r_eo_{bet}_o"))
        txt = "⚖️ Чет или Нечет (2x)?"
    safe_api_call(bot.edit_message_text, txt, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('c_r_'))
def cube_roll(call):
    if call.message.reply_to_message and call.from_user.id != call.message.reply_to_message.from_user.id: return
    _, _, mode, bet, choice = call.data.split('_'); bet, uid = int(bet), call.from_user.id
    safe_api_call(bot.edit_message_text, "🎲 Бросаю кубик...", call.message.chat.id, call.message.message_id)
    dice = safe_api_call(bot.send_dice, call.message.chat.id, emoji='🎲', message_thread_id=call.message.message_thread_id)
    time.sleep(4)
    score, win, txt = dice.dice.value, 0, f"🎲 Выпало: <b>{dice.dice.value}</b>\n\n"
    
    if mode == 'ex':
        if str(score) == choice: win = bet * 4; txt += f"🎉 <b>Угадал!</b> Выигрыш: {win}"
        else: txt += f"💥 <b>Мимо!</b> Ставил на {choice}."
    else:
        is_even = score % 2 == 0
        if (choice == 'e' and is_even) or (choice == 'o' and not is_even): win = bet * 2; txt += f"🎉 <b>Угадал!</b> Выигрыш: {win}"
        else: txt += "💥 <b>Не угадал!</b>"
            
    if win > 0: set_balance(uid, get_balance(uid) + win)
    safe_api_call(bot.send_message, call.message.chat.id, txt + f"\n💰 Баланс: {get_balance(uid)}", reply_to_message_id=dice.message_id, message_thread_id=call.message.message_thread_id)

@bot.message_handler(commands=['rps'])
def rps_cmd(message):
    cache_user(message.from_user)
    args = message.text.split()
    if len(args) != 3 or args[2].lower() not in ['камень', 'ножницы', 'бумага']: return safe_api_call(bot.reply_to, message, "⚠️ Пример: /rps 100 камень")
    bet, uid = parse_amount(args[1]), message.from_user.id
    if not bet or bet > get_balance(uid): return safe_api_call(bot.reply_to, message, "❌ Ошибка ставки.")

    user_c, bot_c = args[2].lower(), random.choice(['камень', 'ножницы', 'бумага'])
    set_balance(uid, get_balance(uid) - bet)
    emoji = {'камень': '🪨', 'ножницы': '✂️', 'бумага': '📄'}
    
    if user_c == bot_c:
        set_balance(uid, get_balance(uid) + bet)
        txt = f"{emoji[bot_c]} Ничья! Возврат."
    elif (user_c == 'камень' and bot_c == 'ножницы') or (user_c == 'ножницы' and bot_c == 'бумага') or (user_c == 'бумага' and bot_c == 'камень'):
        set_balance(uid, get_balance(uid) + bet*2)
        txt = f"{emoji[bot_c]} Вы выиграли {bet*2}!"
    else: txt = f"{emoji[bot_c]} Бот выиграл."
    safe_api_call(bot.reply_to, message, txt + f"\n💰 Баланс: {get_balance(uid)}")

# === БЛЭКДЖЕК ===
active_bj_games = {}
BJ_CARDS = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11}
BJ_SUITS = ['♠️', '♥️', '♣️', '♦️']

def generate_shoe(num_decks=4):
    deck = [{'rank': rank, 'suit': suit} for suit in BJ_SUITS for rank in BJ_CARDS.keys() for _ in range(num_decks)]
    random.shuffle(deck)
    return deck

def calc_score(h):
    s = sum(BJ_CARDS[c['rank']] for c in h)
    a = sum(1 for c in h if c['rank'] == 'A')
    while s > 21 and a > 0: 
        s -= 10
        a -= 1
    return s

def get_bj_text(g, show=False):
    p_str = " ".join([f"{c['rank']}{c['suit']}" for c in g['p']])
    if show:
        d_str = " ".join([f"{c['rank']}{c['suit']}" for c in g['d']])
        return f"🃏 <b>Блэкджек</b> | Ставка: {g['bet']}\n\n👨‍💼 <b>Дилер ({calc_score(g['d'])}):</b>\n{d_str}\n\n👤 <b>Вы ({calc_score(g['p'])}):</b>\n{p_str}\n\n"
    return f"🃏 <b>Блэкджек</b> | Ставка: {g['bet']}\n\n👨‍💼 <b>Дилер:</b>\n{g['d'][0]['rank']}{g['d'][0]['suit']} ❓\n\n👤 <b>Вы ({calc_score(g['p'])}):</b>\n{p_str}\n\n"

@bot.message_handler(commands=['bj'])
def bj_cmd(message):
    cache_user(message.from_user)
    uid = message.from_user.id
    if uid in active_bj_games: return safe_api_call(bot.reply_to, message, "‼️ Заверши текущую игру!")
    
    args = message.text.split()
    if len(args) != 2: return safe_api_call(bot.reply_to, message, "⚠️ Пример: /bj [ставка]")
    bet = parse_amount(args[1])
    if not bet or bet > get_balance(uid): return safe_api_call(bot.reply_to, message, "❌ Ошибка ставки.")

    set_balance(uid, get_balance(uid) - bet)
    
    shoe = generate_shoe()
    g = {'deck': shoe, 'p': [shoe.pop(), shoe.pop()], 'd': [shoe.pop(), shoe.pop()], 'bet': bet}
    
    if calc_score(g['p']) == 21:
        if calc_score(g['d']) == 21: 
            set_balance(uid, get_balance(uid) + bet)
            res = "🤝 Ничья!"
        else: 
            set_balance(uid, get_balance(uid) + int(bet * 2.5))
            res = "🎉 БЛЭКДЖЕК!"
        return safe_api_call(bot.reply_to, message, get_bj_text(g, True) + res + f"\n💰 Баланс: {get_balance(uid)}")

    active_bj_games[uid] = g
    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🃏 Еще", callback_data="bj_hit"), 
        types.InlineKeyboardButton("🛑 Хватит", callback_data="bj_stand")
    )
    msg = safe_api_call(bot.reply_to, message, get_bj_text(g), reply_markup=markup)
    active_bj_games[uid]['mid'] = msg.message_id

@bot.callback_query_handler(func=lambda call: call.data in ['bj_hit', 'bj_stand'])
def bj_cb(call):
    uid = call.from_user.id
    g = active_bj_games.get(uid)
    
    if not g or g.get('mid') != call.message.message_id: 
        return safe_api_call(bot.answer_callback_query, call.id, "Ошибка.", show_alert=True)

    if call.data == 'bj_hit':
        g['p'].append(g['deck'].pop())
        
        if calc_score(g['p']) > 21:
            safe_api_call(bot.edit_message_text, get_bj_text(g, True) + "💥 <b>Перебор! Вы проиграли.</b>" + f"\n💰 Баланс: {get_balance(uid)}", call.message.chat.id, call.message.message_id)
            del active_bj_games[uid]
        else:
            markup = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🃏 Еще", callback_data="bj_hit"), 
                types.InlineKeyboardButton("🛑 Хватит", callback_data="bj_stand")
            )
            safe_api_call(bot.edit_message_text, get_bj_text(g), call.message.chat.id, call.message.message_id, reply_markup=markup)
            
    elif call.data == 'bj_stand':
        while calc_score(g['d']) < 17:
            g['d'].append(g['deck'].pop())
            
        p_score = calc_score(g['p'])
        d_score = calc_score(g['d'])
        bet = g['bet']
        
        if d_score > 21:
            res = f"🎉 <b>Дилер перебрал! Вы выиграли {bet}!</b>"
            set_balance(uid, get_balance(uid) + bet * 2)
        elif d_score > p_score:
            res = "😞 <b>Дилер выиграл!</b>"
        elif d_score < p_score:
            res = f"🎉 <b>Вы выиграли {bet}!</b>"
            set_balance(uid, get_balance(uid) + bet * 2)
        else:
            res = "🤝 <b>Ничья! Фишки возвращены.</b>"
            set_balance(uid, get_balance(uid) + bet)
            
        safe_api_call(bot.edit_message_text, get_bj_text(g, True) + res + f"\n💰 Баланс: {get_balance(uid)}", call.message.chat.id, call.message.message_id)
        del active_bj_games[uid]

if __name__ == '__main__':
    bot.polling(none_stop=True)
