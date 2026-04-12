import telebot
from telebot import types
import random
import time
import sqlite3
import math
from datetime import datetime

# === НАСТРОЙКИ ===
TOKEN = '8087549070:AAFG6E4i0QjOvgjoj6jUb_lpOImQx_qPP5c'
ADMIN_IDS = [5379659751] 
MAX_AMOUNT = 100000
DB_PATH = 'kazino.db'
COOLDOWN_TIME_SECONDS = 5

# Глобальные переменные для кулдауна команды /bank
last_bank_time = 0
BANK_COOLDOWN = 10

# ПРЯМЫЕ ССЫЛКИ НА ФОТОГРАФИИ (Оставлены, если понадобятся в будущем)
WIN_PHOTO_URL = "https://i-mg24.ru/images/041226144234-dyne5.png"
LOSE_PHOTO_URL = "https://i-mg24.ru/images/041226144331-5bq8f.png"
SPIN_PHOTO_URL = "https://i-mg24.ru/images/041226144354-mor1b.png"

# === ИНИЦИАЛИЗАЦИЯ БД И ДОХОДОВ ===
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Таблица юзеров
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if cursor.fetchone() is None:
            conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, balance INTEGER, last_play_time TEXT)')

        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'last_play_time' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN last_play_time TEXT")
            
        # НОВАЯ ТАБЛИЦА ДОХОДОВ
        conn.execute('CREATE TABLE IF NOT EXISTS income (id INTEGER PRIMARY KEY AUTOINCREMENT, amount INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
        conn.commit()

init_db()

def add_income(amount):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO income (amount) VALUES (?)", (amount,))
        conn.commit()

def get_income_stats():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        # День (24 часа)
        cur.execute("SELECT SUM(amount) FROM income WHERE timestamp >= datetime('now', '-1 day')")
        day = cur.fetchone()[0] or 0
        # Неделя
        cur.execute("SELECT SUM(amount) FROM income WHERE timestamp >= datetime('now', '-7 days')")
        week = cur.fetchone()[0] or 0
        # Месяц
        cur.execute("SELECT SUM(amount) FROM income WHERE timestamp >= datetime('now', '-30 days')")
        month = cur.fetchone()[0] or 0
        # За все время
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
        types.BotCommand('start', '🚀 Запустить/перезапустить бота'),
        types.BotCommand('help', '📖 Справка и правила'),
        types.BotCommand('bank', '🏦 Баланс самого казино'),
        types.BotCommand('play', '🎰 Сыграть в рулетку (ставка)'),
        types.BotCommand('bj', '🃏 Сыграть в блэкджек (ставка)'),
        types.BotCommand('mines', '💣 Минное поле (ставка)'),
        types.BotCommand('basket', '🏀 Баскетбол (ставка)'),
        types.BotCommand('cube', '🎲 Кубик (ставка)'),
        types.BotCommand('rps', '🪨 Камень-ножницы-бумага (ставка)'),
        types.BotCommand('balance', '💰 Посмотреть свой баланс'),
        types.BotCommand('chet', '💱 Рассчитать из баксов в фишки'),
        types.BotCommand('sell', '💹 Рассчитать из фишек в баксы'),
        types.BotCommand('out', '💸 Вывести фишки в $'),
        # Админские команды (get и del) не обязательно показывать всем, но оставим как было
        types.BotCommand('get', '👑 [Админ] Выдать фишки'),
        types.BotCommand('del', '👑 [Админ] Забрать фишки')
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
                if "unexpected keyword argument" in str(e).lower():
                    return None 
                else:
                    raise 
        except Exception:
            raise

# === ИНФО КОМАНДЫ (ПОМОЩЬ И БАНК) ===
@bot.message_handler(commands=['help'])
def help_cmd(message):
    text = (
        "📖 <b>Справка по казино</b>\n\n"
        "💵 <b>Как купить фишки:</b>\n"
        "Надо перевести точную сумму, @LomanTTGG\n"
        "Пример:<code>/pay @LomanTTGG [сумма]</code>\n"
        "<i>(1 фишка = 100$. Минимальная сумма 100$)</i>. Бот автоматически зачислит фишки на твой баланс в казино.\n\n"
        "💸 <b>Как вывести фишки:</b>\n"
        "Используй команду <code>/out [кол-во фишек]</code>. Вам выпишут чек в $.\n\n"
        "💱 <b>Конвертация:</b>\n"
        "<code>/chet [сумма в $]</code> — узнать, сколько фишек ты получишь за доллары.\n"
        "<code>/sell [кол-во фишек]</code> — узнать, сколько долларов ты получишь за фишки.\n\n"
        "🎮 <b>Новые игры:</b>\n"
        "🏀 <code>!б [ставка]</code> или <code>/basket [ставка]</code> — Баскетбол\n"
        "🎲 <code>!к [ставка]</code> или <code>/cube [ставка]</code> — Кубик (угадай число или чет/нечет)\n\n"
        "🏦 <b>Информация:</b>\n"
        "<code>/bank</code> — проверить, сколько сейчас долларов на балансе самого казино (резерв на выплаты чеков)."
    )
    safe_api_call(bot.send_message, message.chat.id, text, message_thread_id=message.message_thread_id)

@bot.message_handler(commands=['balance'])
def balance_cmd(message):
    user_id = message.from_user.id
    balance = get_balance(user_id)
    safe_api_call(bot.reply_to, message, f"💰 Баланс: <b>{balance}</b> фишек.")

@bot.message_handler(commands=['bank'])
def bank_cmd(message):
    global last_bank_time
    current_time = time.time()
    
    if current_time - last_bank_time < BANK_COOLDOWN:
        wait_time = int(BANK_COOLDOWN - (current_time - last_bank_time))
        return safe_api_call(bot.reply_to, message, f"⏳ Команда /bank доступна 1 раз в {BANK_COOLDOWN} секунд.\nПодождите еще {wait_time} сек.")
        
    last_bank_time = current_time
    msg_wait = safe_api_call(bot.reply_to, message, "⏳ Узнаю баланс казино у Роксаны...")
    
    if msg_wait:
        admin_id = ADMIN_IDS[0]
        safe_api_call(bot.send_message, admin_id, f"Банк {message.chat.id} {msg_wait.message_id}")

# === ВЫВОД СРЕДСТВ И ВЗАИМОДЕЙСТВИЕ С СЕССИЕЙ ===
@bot.message_handler(commands=['out'])
def out_chips(message):
    args = message.text.split()
    if len(args) != 2:
        return safe_api_call(bot.reply_to, message, "📌 Пример: /out 1 (где 1 фишка = 100$)")
    
    chips = parse_amount(args[1])
    if not chips:
        return safe_api_call(bot.reply_to, message, "❌ Укажите целое число фишек.")
    
    user_id = message.from_user.id
    balance = get_balance(user_id)
    
    if chips > balance:
        return safe_api_call(bot.reply_to, message, f"❌ Недостаточно фишек. Баланс: {balance}")
    
    set_balance(user_id, balance - chips)
    usd_amount = chips * 100
    
    msg_wait = safe_api_call(bot.reply_to, message, f"⏳ Запрос на вывод {chips} фишек ({usd_amount}$) отправлен!\nОжидаем подтверждения от банка...")
    
    if not msg_wait:
        set_balance(user_id, balance)
        return

    admin_id = ADMIN_IDS[0]
    msg_to_admin = f"Вывод {usd_amount}$ {user_id} {message.chat.id} {msg_wait.message_id}"
    safe_api_call(bot.send_message, admin_id, msg_to_admin)

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
                    chips_to_refund = usd_amount // 100
                    current_balance = get_balance(target_user_id)
                    set_balance(target_user_id, current_balance + chips_to_refund)
                    
                    error_text = f"❌ <b>Ошибка вывода!</b>\n\nПричина: {message.text}\n\n<i>{chips_to_refund} фишек возвращено на ваш баланс.</i>"
                    try:
                        safe_api_call(bot.edit_message_text, error_text, chat_id=chat_id, message_id=wait_msg_id)
                    except Exception:
                        safe_api_call(bot.send_message, chat_id, error_text, reply_to_message_id=wait_msg_id)
                    
                    safe_api_call(bot.reply_to, message, "✅ Пользователь уведомлен об ошибке, фишки возвращены.")
                else:
                    user_msg = f"✅ <b>Ваши деньги ({usd_amount}$) были успешно выведены!</b>\n\n{message.text}\n\n<i>Напишите команду /checks, либо /acceptcheck (номер чека) для принятия</i>"
                    try:
                        safe_api_call(bot.edit_message_text, user_msg, chat_id=chat_id, message_id=wait_msg_id)
                    except Exception:
                        safe_api_call(bot.send_message, chat_id, user_msg, reply_to_message_id=wait_msg_id)
                        
                    safe_api_call(bot.reply_to, message, "✅ Чек успешно встроен в группу.")
            except Exception as e:
                safe_api_call(bot.reply_to, message, f"❌ Ошибка обработки ответа от сессии: {e}")
                
    elif original_text.startswith("Банк"):
        parts = original_text.split()
        if len(parts) >= 3:
            try:
                chat_id = int(parts[1])
                wait_msg_id = int(parts[2])
                
                try:
                    safe_api_call(bot.edit_message_text, message.text, chat_id=chat_id, message_id=wait_msg_id)
                except Exception:
                    safe_api_call(bot.send_message, chat_id, message.text, reply_to_message_id=wait_msg_id)
                    
                safe_api_call(bot.reply_to, message, "✅ Баланс передан в чат.")
            except Exception as e:
                safe_api_call(bot.reply_to, message, f"❌ Ошибка отправки банка: {e}")

# === АДМИН-КОМАНДЫ ===
@bot.message_handler(commands=['get'])
def add_chips_from_userbot(message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()
        chips_to_add = int(args[1])
        target_user_id = int(args[2])
        current_balance = get_balance(target_user_id)
        set_balance(target_user_id, current_balance + chips_to_add)
        
        # ЗАПИСЫВАЕМ В ДОХОД
        if chips_to_add > 0:
            add_income(chips_to_add)
            
        bot.reply_to(message, f"✅ Игроку {target_user_id} выдано {chips_to_add} фишек. (Учтено в доходах)")
    except Exception:
        bot.reply_to(message, "❌ Ошибка. Формат: /get <кол-во_фишек> <айди_юзера>")

@bot.message_handler(commands=['income'])
def show_income(message):
    if not is_admin(message.from_user.id): return
    day, week, month, all_time = get_income_stats()
    text = (
        "📈 <b>Статистика доходов (купленных фишек):</b>\n\n"
        f"За 24 часа: <b>{day}</b>\n"
        f"За неделю: <b>{week}</b>\n"
        f"За месяц: <b>{month}</b>\n"
        f"За всё время: <b>{all_time}</b>"
    )
    safe_api_call(bot.reply_to, message, text)

@bot.message_handler(commands=['delincome'])
def remove_income(message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) != 2:
        return safe_api_call(bot.reply_to, message, "❗ Пример: /delincome 800 (уберет 800 фишек из статистики доходов)")
    try:
        amount = int(args[1])
        if amount <= 0: raise ValueError
        # Вычитаем из доходов (добавляем с минусом)
        add_income(-amount) 
        safe_api_call(bot.reply_to, message, f"✅ Успешно вычтено {amount} фишек из статистики доходов.")
    except ValueError:
        safe_api_call(bot.reply_to, message, "❌ Сумма должна быть положительным числом.")

@bot.message_handler(commands=['del'])
def modify_balance(message):
    if not is_admin(message.from_user.id): return
    if not message.reply_to_message:
        return safe_api_call(bot.reply_to, message, "⚠️ Ответьте на сообщение пользователя.")
    args = message.text.split()
    if len(args) != 2:
        return safe_api_call(bot.reply_to, message, "❗ Пример: /del 10")
    try:
        amount = int(args[1])
        if amount <= 0: raise ValueError
        uid = message.reply_to_message.from_user.id
        name = message.reply_to_message.from_user.first_name
        current_bal = get_balance(uid)
        set_balance(uid, max(0, current_bal - amount))
        safe_api_call(bot.send_message, message.chat.id, f"✅ Забрал {amount} фишек у {name}", message_thread_id=message.message_thread_id)
    except ValueError:
        safe_api_call(bot.reply_to, message, "❌ Сумма должна быть положительным числом.")

@bot.message_handler(commands=['chet'])
def usd_to_chips(message):
    args = message.text.split()
    if len(args) != 2:
        return safe_api_call(bot.reply_to, message, "📌 Пример: /chet 100")
    try:
        usd = float(args[1])
        chips = int(usd / 100)
        safe_api_call(bot.reply_to, message, f"💸 {usd:,.2f}$ = {chips:,} фишек".replace(',', ' '))
    except ValueError:
        pass

@bot.message_handler(commands=['sell'])
def sell_chips(message):
    args = message.text.split()
    if len(args) != 2:
        return safe_api_call(bot.reply_to, message, "📌 Пример: /sell 10")
    try:
        chips = int(args[1])
        usd = chips * 100
        safe_api_call(bot.reply_to, message, f"💵 {chips:,} фишек = {usd:,}$".replace(',', ' '))
    except ValueError:
        pass

# === ОСНОВНЫЕ ИГРЫ ===
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎰 Рулетка", callback_data="play_info"),
        types.InlineKeyboardButton("🃏 Блэкджек", callback_data="bj_info"),
        types.InlineKeyboardButton("💣 Минное поле", callback_data="mines_info"),
        types.InlineKeyboardButton("🏀 Баскетбол", callback_data="basket_info"),
        types.InlineKeyboardButton("🎲 Кубик", callback_data="cube_info"),
        types.InlineKeyboardButton("🪨 КНБ", callback_data="rps_info"),
        types.InlineKeyboardButton("💰 Баланс", callback_data="balance")
    )
    safe_api_call(bot.reply_to, message,
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\nЭто <b>Казино-бот</b>. Выбери игру:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ['balance', 'play_info', 'bj_info', 'mines_info', 'basket_info', 'cube_info', 'rps_info'])
def main_callback_handler(call):
    if call.message.reply_to_message and call.from_user.id != call.message.reply_to_message.from_user.id:
        return safe_api_call(bot.answer_callback_query, call.id, "❌ Это меню вызывал другой игрок!", show_alert=True)

    user_id = call.from_user.id
    chat_id = call.message.chat.id
    thread_id = call.message.message_thread_id
    safe_api_call(bot.answer_callback_query, call.id)

    if call.data == "balance":
        bal, _ = get_user_data(user_id)
        safe_api_call(bot.send_message, chat_id, f"💰 Баланс: <b>{bal}</b> фишек.", message_thread_id=thread_id)
    elif call.data == "play_info":
        safe_api_call(bot.send_message, chat_id, "🎰 <b>Рулетка (Слоты)</b>\nНапиши <code>/play [ставка]</code>, чтобы сыграть.", message_thread_id=thread_id)
    elif call.data == 'bj_info':
        safe_api_call(bot.send_message, chat_id, "🃏 <b>Блэкджек</b>\nНапиши <code>/bj [ставка]</code>, чтобы начать.", message_thread_id=thread_id)
    elif call.data == 'mines_info':
        safe_api_call(bot.send_message, chat_id, "💣 <b>Минное поле</b>\nНапиши <code>/mines [ставка]</code>, выбери кол-во мин и играй.", message_thread_id=thread_id)
    elif call.data == 'basket_info':
        safe_api_call(bot.send_message, chat_id, "🏀 <b>Баскетбол</b>\nНапиши <code>!б [ставка]</code> или <code>/basket [ставка]</code>, чтобы бросить мяч в кольцо.", message_thread_id=thread_id)
    elif call.data == 'cube_info':
        safe_api_call(bot.send_message, chat_id, "🎲 <b>Кубик</b>\nНапиши <code>!к [ставка]</code> или <code>/cube [ставка]</code>, чтобы бросить кубик.", message_thread_id=thread_id)
    elif call.data == 'rps_info':
        safe_api_call(bot.send_message, chat_id, "🪨 <b>Камень-ножницы-бумага</b>\nНапиши <code>/rps [ставка] [камень/ножницы/бумага]</code>.", message_thread_id=thread_id)


# === РУЛЕТКА (СЛОТЫ) ===
@bot.message_handler(commands=['play'])
def play(message):
    user_id = message.from_user.id
    args = message.text.split()
    thread_id = message.message_thread_id

    balance, last_play_time = get_user_data(user_id)
    if len(args) != 2: return safe_api_call(bot.reply_to, message, "⚠️ Пример: /play 100")
    
    bet = parse_amount(args[1])
    if not bet: return safe_api_call(bot.reply_to, message, f"❌ Ставка от 1 до {MAX_AMOUNT}")
    if bet > balance: return safe_api_call(bot.reply_to, message, f"❌ Недостаточно фишек. Баланс: {balance}")

    # Списываем ставку
    set_user_data(user_id, balance - bet, datetime.now())

    # Отправляем дайс слотов
    dice_msg = safe_api_call(bot.send_dice, message.chat.id, emoji='🎰', message_thread_id=thread_id)
    
    # Ждем пока прокрутится анимация
    time.sleep(2.5)

    value = dice_msg.dice.value
    # Декодируем значение дайса (от 1 до 64) на 3 барабана
    v = value - 1
    r1 = v % 4
    r2 = (v // 4) % 4
    r3 = (v // 16) % 4
    
    # Символы телеграма (в коде используем вишню вместо винограда для вывода)
    symbols = {0: 'BAR', 1: '🍒', 2: '🍋', 3: '7️⃣'}
    s1, s2, s3 = symbols[r1], symbols[r2], symbols[r3]
    
    multiplier = 0.0
    
    # Проверка выигрышных комбинаций
    if s1 == s2 == s3:
        # Полные комбо (3 одинаковых)
        if s1 == 'BAR': multiplier = 4.0
        elif s1 == '🍋': multiplier = 3.0
        elif s1 == '🍒': multiplier = 6.0
        elif s1 == '7️⃣': multiplier = 10.0
    elif s1 == s2 and s3 != s1:
        # Частичные комбо (первые 2 одинаковые)
        if s1 == 'BAR': multiplier = 2.0
        elif s1 == '🍋': multiplier = 2.0
        elif s1 == '🍒': multiplier = 3.0
        elif s1 == '7️⃣': multiplier = 3.0

    if multiplier > 0:
        win_amount = int(bet * multiplier)
        set_balance(user_id, get_balance(user_id) + win_amount)
        result_text = (
            f"🎉 <b>Вы выиграли!</b>\n\n"
            f"Комбинация: [ {s1} | {s2} | {s3} ]\n"
            f"Множитель: <b>x{multiplier}</b>\n"
            f"Выигрыш: <b>+{win_amount}</b> фишек\n"
            f"💰 Баланс: <b>{get_balance(user_id)}</b>"
        )
    else:
        result_text = (
            f"😞 <b>Проигрыш...</b>\n\n"
            f"Комбинация: [ {s1} | {s2} | {s3} ]\n"
            f"Проиграно: <b>-{bet}</b> фишек\n"
            f"💰 Баланс: <b>{get_balance(user_id)}</b>"
        )

    safe_api_call(bot.reply_to, message, result_text)


# === МИННОЕ ПОЛЕ ===
active_mines_games = {}
MINES_GRID_SIZE = 3

def get_mines_multiplier(num_mines, safe_opened):
    if safe_opened == 0: return 1.0
    safe_total = 9 - num_mines
    if safe_opened > safe_total: return 0.0
    chance = math.comb(safe_total, safe_opened) / math.comb(9, safe_opened)
    return round((1.0 / chance) * 0.95, 2)

def generate_mines_field(size, num_mines):
    field = [['.' for _ in range(size)] for _ in range(size)]
    mine_positions = set()
    while len(mine_positions) < num_mines:
        mine_positions.add((random.randint(0, size - 1), random.randint(0, size - 1)))
    return field, mine_positions

def get_mines_keyboard(game_state):
    markup = types.InlineKeyboardMarkup()
    for r in range(MINES_GRID_SIZE):
        row_buttons = []
        for c in range(MINES_GRID_SIZE):
            cell = game_state['board'][r][c]
            cb_data = f"mine_click_{r}_{c}"
            if game_state['game_over']:
                cb_data = "mine_noop"
                btn_text = '✅' if cell == 'O' else ('💥' if cell == 'X' else ('💣' if cell == 'M_REVEALED' else '⬜️'))
            else:
                btn_text = '✅' if cell == 'O' else '⬜️'
                if cell == 'O': cb_data = "mine_noop"
            row_buttons.append(types.InlineKeyboardButton(btn_text, callback_data=cb_data))
        markup.row(*row_buttons)

    if game_state['current_winnings'] > game_state['bet'] and not game_state['game_over']:
        markup.add(types.InlineKeyboardButton(f"💰 Забрать {int(game_state['current_winnings'])}", callback_data="mine_cashout"))
    return markup

def get_mines_text(game_state):
    mult = get_mines_multiplier(game_state['num_mines'], game_state['safe_cells_opened'])
    text = f"💣 <b>Мин:</b> {game_state['num_mines']} | <b>Ставка:</b> {game_state['bet']}\nОткрыто: <b>{game_state['safe_cells_opened']}</b> | Икс: <b>x{mult:.2f}</b>\nНа вывод: <b>{int(game_state['current_winnings'])}</b>\n\n"
    if game_state['game_over']:
        text += "💥 <b>Подорвался!</b>" if game_state['mined'] else "✅ <b>Успешный вывод!</b>"
    return text

@bot.message_handler(commands=['mines'])
def mines_cmd(message):
    user_id = message.from_user.id
    if user_id in active_mines_games:
        return safe_api_call(bot.reply_to, message, "‼️ Сначала заверши текущую игру!")

    args = message.text.split()
    if len(args) != 2: return safe_api_call(bot.reply_to, message, "⚠️ Пример: <code>/mines 100</code>")
    
    bet = parse_amount(args[1])
    if not bet: return safe_api_call(bot.reply_to, message, "❌ Неверная ставка.")
    if bet > get_balance(user_id): return safe_api_call(bot.reply_to, message, "💰 Недостаточно фишек.")

    markup = types.InlineKeyboardMarkup(row_width=4)
    buttons = [types.InlineKeyboardButton(f"{i} 💣", callback_data=f"mine_setup_{i}_{bet}") for i in range(1, 9)]
    markup.add(*buttons)
    
    info_text = (
        f"💣 <b>Минное поле</b>\n"
        f"Твоя ставка: <b>{bet}</b> фишек.\n\n"
        f"👇 <i>Выбери количество мин, которые будут спрятаны на поле (сетка 3x3). "
        f"Чем больше мин ты выберешь, тем выше будет коэффициент выигрыша за каждую открытую безопасную ячейку, "
        f"но и шанс подорваться возрастет!</i>\n\n"
        f"Сколько мин прячем?"
    )
    safe_api_call(bot.reply_to, message, info_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mine_setup_'))
def mines_setup(call):
    if call.message.reply_to_message and call.from_user.id != call.message.reply_to_message.from_user.id:
        return safe_api_call(bot.answer_callback_query, call.id, "❌ Это не твоя игра!", show_alert=True)

    user_id = call.from_user.id
    _, _, num_mines_str, bet_str = call.data.split('_')
    num_mines, bet = int(num_mines_str), int(bet_str)
    
    balance = get_balance(user_id)
    if bet > balance:
        return safe_api_call(bot.answer_callback_query, call.id, "💰 Недостаточно фишек!", show_alert=True)
    
    set_balance(user_id, balance - bet)
    board, mine_pos = generate_mines_field(MINES_GRID_SIZE, num_mines)
    
    active_mines_games[user_id] = {
        'user_id': user_id, 'bet': bet, 'num_mines': num_mines, 'board': board,
        'mine_positions': mine_pos, 'safe_cells_opened': 0, 'current_winnings': float(bet),
        'game_over': False, 'mined': False, 'message_id': call.message.message_id
    }
    
    markup = get_mines_keyboard(active_mines_games[user_id])
    safe_api_call(bot.edit_message_text, get_mines_text(active_mines_games[user_id]), call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mine_click_') or call.data in ['mine_cashout', 'mine_noop'])
def mines_play(call):
    if call.message.reply_to_message and call.from_user.id != call.message.reply_to_message.from_user.id:
        return safe_api_call(bot.answer_callback_query, call.id, "❌ Это не твоя игра!", show_alert=True)

    user_id = call.from_user.id
    game = active_mines_games.get(user_id)
    if not game or game['message_id'] != call.message.message_id: return
    
    if call.data == 'mine_noop': 
        return safe_api_call(bot.answer_callback_query, call.id)

    if call.data == 'mine_cashout':
        if game['game_over']: return
        set_balance(user_id, get_balance(user_id) + int(game['current_winnings']))
        game['game_over'] = True
        markup = get_mines_keyboard(game)
        safe_api_call(bot.edit_message_text, get_mines_text(game), call.message.chat.id, game['message_id'], reply_markup=markup)
        del active_mines_games[user_id]
        return

    _, _, r, c = call.data.split('_')
    r, c = int(r), int(c)

    if (r, c) in game['mine_positions']:
        game['board'][r][c] = 'X'
        game['game_over'] = True
        game['mined'] = True
        for mr, mc in game['mine_positions']:
            if (mr, mc) != (r, c): game['board'][mr][mc] = 'M_REVEALED'
        safe_api_call(bot.edit_message_text, get_mines_text(game), call.message.chat.id, game['message_id'], reply_markup=get_mines_keyboard(game))
        del active_mines_games[user_id]
    else:
        game['board'][r][c] = 'O'
        game['safe_cells_opened'] += 1
        mult = get_mines_multiplier(game['num_mines'], game['safe_cells_opened'])
        game['current_winnings'] = game['bet'] * mult
        
        if game['safe_cells_opened'] == (9 - game['num_mines']):
            set_balance(user_id, get_balance(user_id) + int(game['current_winnings']))
            game['game_over'] = True
            safe_api_call(bot.edit_message_text, get_mines_text(game), call.message.chat.id, game['message_id'], reply_markup=get_mines_keyboard(game))
            del active_mines_games[user_id]
        else:
            safe_api_call(bot.edit_message_text, get_mines_text(game), call.message.chat.id, game['message_id'], reply_markup=get_mines_keyboard(game))

# === БАСКЕТБОЛ (!б) ===
@bot.message_handler(func=lambda m: m.text and (
    m.text.lower().startswith('/basket') or m.text.lower().startswith('!б')
))
def basketball_game(message):
    args = message.text.split()
    if len(args) < 2:
        return safe_api_call(bot.reply_to, message, "⚠️ Пример: <code>!б 100</code> или <code>/basket 100</code>")
    
    bet = parse_amount(args[1])
    user_id = message.from_user.id
    balance = get_balance(user_id)
    thread_id = message.message_thread_id
    
    if not bet: return safe_api_call(bot.reply_to, message, f"❌ Ставка от 1 до {MAX_AMOUNT}")
    if bet > balance: return safe_api_call(bot.reply_to, message, f"❌ Недостаточно фишек. Баланс: {balance}")

    set_balance(user_id, balance - bet)
    
    # Отправляем дайс баскетбола точно в тему
    dice_msg = safe_api_call(bot.send_dice, message.chat.id, emoji='🏀', message_thread_id=thread_id)
    
    time.sleep(4)
    
    score = dice_msg.dice.value
    
    if score >= 4:
        win_amount = bet * 2
        set_balance(user_id, get_balance(user_id) + win_amount)
        text = f"🎉 <b>Трёхочковый!</b> Мяч в корзине!\n\nТы выиграл {win_amount} фишек!\n💰 Баланс: {get_balance(user_id)}"
    else:
        text = f"💥 <b>Мимо!</b> Мяч отскочил от кольца...\n\nТы проиграл {bet} фишек.\n💰 Баланс: {get_balance(user_id)}"
        
    safe_api_call(bot.reply_to, message, text)

# === КУБИК (!к) ===
@bot.message_handler(func=lambda m: m.text and (
    m.text.lower().startswith('/cube') or m.text.lower().startswith('!к')
))
def cube_game(message):
    args = message.text.split()
    if len(args) < 2:
        return safe_api_call(bot.reply_to, message, "⚠️ Пример: <code>!к 100</code> или <code>/cube 100</code>")
    
    bet = parse_amount(args[1])
    user_id = message.from_user.id
    balance = get_balance(user_id)
    
    if not bet: return safe_api_call(bot.reply_to, message, f"❌ Ставка от 1 до {MAX_AMOUNT}")
    if bet > balance: return safe_api_call(bot.reply_to, message, f"❌ Недостаточно фишек. Баланс: {balance}")

    set_balance(user_id, balance - bet)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎯 Точечно (4x)", callback_data=f"cube_type_exact_{bet}"),
        types.InlineKeyboardButton("⚖️ Чет / Нечет (2x)", callback_data=f"cube_type_eo_{bet}")
    )
    safe_api_call(bot.reply_to, message, f"🎲 <b>Кубик</b>\nТвоя ставка: {bet} фишек.\n\nВыбери режим игры:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cube_type_'))
def cube_type_selection(call):
    if call.message.reply_to_message and call.from_user.id != call.message.reply_to_message.from_user.id:
        return safe_api_call(bot.answer_callback_query, call.id, "❌ Это не твоя игра!", show_alert=True)
        
    _, _, mode, bet_str = call.data.split('_')
    bet = int(bet_str)
    
    markup = types.InlineKeyboardMarkup()
    if mode == 'exact':
        buttons = [types.InlineKeyboardButton(str(i), callback_data=f"cube_roll_exact_{bet}_{i}") for i in range(1, 7)]
        markup.add(*buttons[:3])
        markup.add(*buttons[3:])
        text = f"🎯 <b>Точечно</b> | Ставка: {bet}\nУгадай точное число (выигрыш 4x):"
    else:
        markup.add(
            types.InlineKeyboardButton("Четное (2, 4, 6)", callback_data=f"cube_roll_eo_{bet}_even"),
            types.InlineKeyboardButton("Нечетное (1, 3, 5)", callback_data=f"cube_roll_eo_{bet}_odd")
        )
        text = f"⚖️ <b>Чет / Нечет</b> | Ставка: {bet}\nКакое число выпадет (выигрыш 2x)?"
        
    safe_api_call(bot.edit_message_text, text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cube_roll_'))
def cube_roll_action(call):
    if call.message.reply_to_message and call.from_user.id != call.message.reply_to_message.from_user.id:
        return safe_api_call(bot.answer_callback_query, call.id, "❌ Это не твоя игра!", show_alert=True)
        
    user_id = call.from_user.id
    parts = call.data.split('_')
    mode = parts[2]
    bet = int(parts[3])
    choice = parts[4]
    thread_id = call.message.message_thread_id
    
    safe_api_call(bot.edit_message_text, "🎲 Бросаю кубик...", call.message.chat.id, call.message.message_id)
    
    # Отправляем кубик точно в ту же тему
    dice_msg = safe_api_call(bot.send_dice, call.message.chat.id, emoji='🎲', message_thread_id=thread_id)
    time.sleep(4)
    
    score = dice_msg.dice.value
    win_amount = 0
    text = f"🎲 Выпало: <b>{score}</b>\n\n"
    
    if mode == 'exact':
        if str(score) == choice:
            win_amount = bet * 4
            text += f"🎉 <b>В точку!</b> Ты угадал число!\nВыигрыш: {win_amount} фишек."
        else:
            text += f"💥 <b>Мимо!</b> Ты ставил на {choice}.\nПроигрыш: {bet} фишек."
    elif mode == 'eo':
        is_even = score % 2 == 0
        if (choice == 'even' and is_even) or (choice == 'odd' and not is_even):
            win_amount = bet * 2
            choice_ru = "Четное" if choice == "even" else "Нечетное"
            text += f"🎉 <b>Угадал!</b> Выпало {choice_ru.lower()}.\nВыигрыш: {win_amount} фишек."
        else:
            choice_ru = "Четное" if choice == "even" else "Нечетное"
            text += f"💥 <b>Не угадал!</b> Ты ставил на {choice_ru.lower()}.\nПроигрыш: {bet} фишек."
            
    if win_amount > 0:
        set_balance(user_id, get_balance(user_id) + win_amount)
        
    text += f"\n💰 Баланс: {get_balance(user_id)}"
    safe_api_call(bot.send_message, call.message.chat.id, text, reply_to_message_id=dice_msg.message_id, message_thread_id=thread_id)


# === КАМЕНЬ НОЖНИЦЫ БУМАГА ===
@bot.message_handler(commands=['rps'])
def rps_cmd(message):
    args = message.text.split()
    valid_choices = ['камень', 'ножницы', 'бумага']
    if len(args) != 3 or args[2].lower() not in valid_choices:
        return safe_api_call(bot.reply_to, message, "⚠️ Пример: /rps [ставка] [камень/ножницы/бумага]")
    
    user_id = message.from_user.id
    bet = parse_amount(args[1])
    balance = get_balance(user_id)
    
    if not bet: return safe_api_call(bot.reply_to, message, f"❌ Ставка от 1 до {MAX_AMOUNT}")
    if bet > balance: return safe_api_call(bot.reply_to, message, f"❌ Недостаточно фишек. Баланс: {balance}")

    user_choice = args[2].lower()
    bot_choice = random.choice(valid_choices)
    set_balance(user_id, balance - bet)
    
    emoji_map = {'камень': '🪨', 'ножницы': '✂️', 'бумага': '📄'}
    
    if user_choice == bot_choice:
        set_balance(user_id, get_balance(user_id) + bet)
        text = f"{emoji_map[bot_choice]} Ничья! Бот тоже выбрал {bot_choice}.\n🔄 Ставка возвращена.\n💰 Баланс: {get_balance(user_id)}"
    elif (user_choice == 'камень' and bot_choice == 'ножницы') or \
         (user_choice == 'ножницы' and bot_choice == 'бумага') or \
         (user_choice == 'бумага' and bot_choice == 'камень'):
        win_amount = bet * 2
        set_balance(user_id, get_balance(user_id) + win_amount)
        text = f"{emoji_map[bot_choice]} Бот выбрал {bot_choice}!\n🎉 Вы выиграли {win_amount} фишек!\n💰 Баланс: {get_balance(user_id)}"
    else:
        text = f"{emoji_map[bot_choice]} Бот выбрал {bot_choice}!\n😞 Вы проиграли {bet} фишек.\n💰 Баланс: {get_balance(user_id)}"
    safe_api_call(bot.reply_to, message, text)

# === БЛЭКДЖЕК (ПОЛНАЯ ВЕРСИЯ С ДОБОРОМ) ===
active_bj_games = {}
BJ_CARDS = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11}
BJ_SUITS = ['♠️', '♥️', '♣️', '♦️']

def draw_card():
    rank = random.choice(list(BJ_CARDS.keys()))
    suit = random.choice(BJ_SUITS)
    return {'rank': rank, 'suit': suit, 'value': BJ_CARDS[rank]}

def calc_score(hand):
    score = sum(c['value'] for c in hand)
    aces = sum(1 for c in hand if c['rank'] == 'A')
    while score > 21 and aces > 0:
        score -= 10
        aces -= 1
    return score

def format_hand(hand, hide_first=False):
    if hide_first:
        cards_str = "❓ " + " ".join([f"{c['rank']}{c['suit']}" for c in hand[1:]])
    else:
        cards_str = " ".join([f"{c['rank']}{c['suit']}" for c in hand])
    return cards_str

def get_bj_text(game, show_dealer=False):
    p_score = calc_score(game['player'])
    p_hand_str = format_hand(game['player'])
    
    if show_dealer:
        d_score = calc_score(game['dealer'])
        d_hand_str = format_hand(game['dealer'])
        text = f"🃏 <b>Блэкджек</b> | Ставка: {game['bet']}\n\n"
        text += f"👨‍💼 <b>Дилер ({d_score}):</b>\n{d_hand_str}\n\n"
        text += f"👤 <b>Вы ({p_score}):</b>\n{p_hand_str}\n\n"
    else:
        visible_dealer_card = game['dealer'][0]
        text = f"🃏 <b>Блэкджек</b> | Ставка: {game['bet']}\n\n"
        text += f"👨‍💼 <b>Дилер:</b>\n{visible_dealer_card['rank']}{visible_dealer_card['suit']} ❓\n\n"
        text += f"👤 <b>Вы ({p_score}):</b>\n{p_hand_str}\n\n"
    return text

@bot.message_handler(commands=['bj'])
def bj_cmd(message):
    user_id = message.from_user.id
    if user_id in active_bj_games:
        return safe_api_call(bot.reply_to, message, "‼️ Сначала заверши текущую игру в Блэкджек!")

    args = message.text.split()
    if len(args) != 2:
        return safe_api_call(bot.reply_to, message, "⚠️ Пример: /bj [ставка]")
    
    bet = parse_amount(args[1])
    balance = get_balance(user_id)
    
    if not bet: return safe_api_call(bot.reply_to, message, f"❌ Ставка от 1 до {MAX_AMOUNT}")
    if bet > balance: return safe_api_call(bot.reply_to, message, f"❌ Недостаточно фишек. Баланс: {balance}")

    set_balance(user_id, balance - bet)
    
    p_hand = [draw_card(), draw_card()]
    d_hand = [draw_card(), draw_card()]
    
    game = {
        'user_id': user_id,
        'bet': bet,
        'player': p_hand,
        'dealer': d_hand,
        'status': 'playing'
    }
    
    p_score = calc_score(p_hand)
    
    if p_score == 21:
        d_score = calc_score(d_hand)
        if d_score == 21:
            set_balance(user_id, get_balance(user_id) + bet)
            text = get_bj_text(game, show_dealer=True) + "🤝 <b>Ничья!</b> У обоих Блэкджек. Ставка возвращена."
        else:
            win_amount = int(bet * 2.5)
            set_balance(user_id, get_balance(user_id) + win_amount)
            text = get_bj_text(game, show_dealer=True) + f"🎉 <b>БЛЭКДЖЕК!</b> Вы выиграли {win_amount} фишек!"
        text += f"\n💰 Баланс: {get_balance(user_id)}"
        return safe_api_call(bot.reply_to, message, text)

    active_bj_games[user_id] = game
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🃏 Взять еще", callback_data="bj_hit"),
        types.InlineKeyboardButton("🛑 Хватит", callback_data="bj_stand")
    )
    
    msg = safe_api_call(bot.reply_to, message, get_bj_text(game, show_dealer=False), reply_markup=markup)
    active_bj_games[user_id]['message_id'] = msg.message_id

@bot.callback_query_handler(func=lambda call: call.data in ['bj_hit', 'bj_stand'])
def bj_callback(call):
    if call.message.reply_to_message and call.from_user.id != call.message.reply_to_message.from_user.id:
        return safe_api_call(bot.answer_callback_query, call.id, "❌ Это не твоя игра!", show_alert=True)

    user_id = call.from_user.id
    if user_id not in active_bj_games:
        return safe_api_call(bot.answer_callback_query, call.id, "Игра не найдена или уже завершена.", show_alert=True)
        
    game = active_bj_games[user_id]
    if game.get('message_id') != call.message.message_id:
        return safe_api_call(bot.answer_callback_query, call.id, "Это старая игра.", show_alert=True)

    if call.data == 'bj_hit':
        game['player'].append(draw_card())
        p_score = calc_score(game['player'])
        
        if p_score > 21:
            text = get_bj_text(game, show_dealer=True) + f"💥 <b>Перебор!</b> Вы проиграли {game['bet']} фишек.\n💰 Баланс: {get_balance(user_id)}"
            safe_api_call(bot.edit_message_text, text, call.message.chat.id, call.message.message_id)
            del active_bj_games[user_id]
        elif p_score == 21:
            bj_dealer_turn(call.message.chat.id, call.message.message_id, user_id, game)
        else:
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("🃏 Взять еще", callback_data="bj_hit"),
                types.InlineKeyboardButton("🛑 Хватит", callback_data="bj_stand")
            )
            safe_api_call(bot.edit_message_text, get_bj_text(game, show_dealer=False), call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'bj_stand':
        bj_dealer_turn(call.message.chat.id, call.message.message_id, user_id, game)

def bj_dealer_turn(chat_id, message_id, user_id, game):
    p_score = calc_score(game['player'])
    
    while calc_score(game['dealer']) < 17:
        game['dealer'].append(draw_card())
        
    d_score = calc_score(game['dealer'])
    bet = game['bet']
    
    if d_score > 21:
        win = bet * 2
        set_balance(user_id, get_balance(user_id) + win)
        res = f"🎉 Дилер перебрал! Вы выиграли {win} фишек!"
    elif d_score > p_score:
        res = f"😞 Дилер выиграл. Вы проиграли {bet} фишек."
    elif d_score < p_score:
        win = bet * 2
        set_balance(user_id, get_balance(user_id) + win)
        res = f"🎉 Вы выиграли {win} фишек!"
    else:
        set_balance(user_id, get_balance(user_id) + bet)
        res = "🤝 <b>Ничья!</b> Ставка возвращена."
        
    text = get_bj_text(game, show_dealer=True) + res + f"\n💰 Баланс: {get_balance(user_id)}"
    safe_api_call(bot.edit_message_text, text, chat_id, message_id)
    del active_bj_games[user_id]

# Запуск бота
if __name__ == '__main__':
    try:
        set_commands(bot)
    except Exception as e:
        print(f"Не удалось установить команды: {e}")
    bot.infinity_polling()
