import os
import threading
import time
import signal
import sys
import logging
import uuid

# Проверка наличия зависимостей
try:
    from flask import Flask, request, Response
    from telebot import TeleBot, types
    import vk_api
    import requests
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Ошибка: отсутствует библиотека - {e}. Установите зависимости с помощью 'pip install -r requirements.txt'.")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Токены и конфигурация
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN or any(char.isspace() for char in TELEGRAM_TOKEN):
    logger.error("TELEGRAM_TOKEN не задан или содержит пробелы")
    raise ValueError("TELEGRAM_TOKEN отсутствует или некорректен")

VK_TOKEN = os.getenv('VK_TOKEN', '')
# Railway предоставляет публичный домен через переменную окружения
RAILWAY_PUBLIC_DOMAIN = os.getenv('RAILWAY_PUBLIC_DOMAIN', 'your-app-name.railway.app')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', f"https://{RAILWAY_PUBLIC_DOMAIN}")
WEBHOOK_PATH = '/webhook'
WEBHOOK_FULL_URL = f"{WEBHOOK_URL}{WEBHOOK_PATH}"

# Уникальный идентификатор экземпляра
INSTANCE_ID = str(uuid.uuid4())
logger.info(f"Запущен экземпляр бота с ID: {INSTANCE_ID}")

# Инициализация Flask приложения
app = Flask(__name__)

# Инициализация бота Telegram
bot = TeleBot(TELEGRAM_TOKEN, threaded=False)

# Инициализация VK API
vk_session = vk_api.VkApi(token=VK_TOKEN) if VK_TOKEN else None
vk = vk_session.get_api() if vk_session else None

# Глобальные переменные
VK_Groups = [-211223344, -155667788, -199887766, -188445566, -177334455]
VK_CONVERSATIONS = [2000000001, 2000000005]
DELAY_TIME = 15
DELETE_TIME = 15
SPAM_RUNNING = {'groups': False, 'conversations': False}
SPAM_THREADS = {'groups': [], 'conversations': []}
SPAM_TEMPLATE = "Первое сообщение"
bot_started = False

# Основная клавиатура
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        "🚀 Спам в группы", "🚀 Спам в беседы",
        "⏳ Установить задержку", "🕒 Время удаления",
        "ℹ️ Статус", "➕ Добавить чат",
        "✍️ Шаблон для спама", "🔑 Сменить токен VK",
        "🗑 Удалить чат", "🗑 Очистить API VK"
    )
    return markup

# Клавиатура спама
def spam_menu(spam_type):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("⛔ Отключить спам")
    markup.add(
        "🚀 Спам в группы", "🚀 Спам в беседы",
        "⏳ Установить задержку", "🕒 Время удаления",
        "ℹ️ Статус", "➕ Добавить чат",
        "✍️ Шаблон для спама", "🔑 Сменить токен VK",
        "🗑 Удалить чат", "🗑 Очистить API VK"
    )
    return markup

# Клавиатура удаления чатов
def create_remove_chat_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    if VK_Groups or VK_CONVERSATIONS:
        for group_id in VK_Groups:
            markup.add(types.InlineKeyboardButton(f"Группа {group_id}", callback_data=f"remove_group_{group_id}"))
        for conv_id in VK_CONVERSATIONS:
            markup.add(types.InlineKeyboardButton(f"Беседа {conv_id}", callback_data=f"remove_conversation_{conv_id}"))
        markup.add(types.InlineKeyboardButton("Отмена", callback_data="cancel_remove"))
    else:
        markup.add(types.InlineKeyboardButton("Нет чатов для удаления", callback_data="no_chats"))
    return markup

# Функция спама
def send_and_delete_vk_messages(chat_id, telegram_chat_id):
    global DELAY_TIME, DELETE_TIME, SPAM_TEMPLATE
    while SPAM_RUNNING['groups'] if chat_id < 0 else SPAM_RUNNING['conversations']:
        try:
            if not vk:
                raise Exception("VK API не инициализирован")
            msg1 = vk.messages.send(peer_id=chat_id, message=SPAM_TEMPLATE, random_id=int(time.time() * 1000))
            bot.send_message(telegram_chat_id, f"Отправлено '{SPAM_TEMPLATE}' в VK чат {chat_id}")
            time.sleep(DELETE_TIME)
            vk.messages.delete(message_ids=[msg1], delete_for_all=1)
            bot.send_message(telegram_chat_id, f"Удалено сообщение в VK чат {chat_id}")
            time.sleep(max(0, DELAY_TIME - DELETE_TIME))
        except Exception as e:
            logger.error(f"Ошибка в чате {chat_id}: {str(e)}")
            bot.send_message(telegram_chat_id, f"Ошибка в чате {chat_id}: {str(e)}")
            break

# Самопингование для поддержания активности
def ping_service():
    global bot_started
    PING_URL = os.getenv('PING_URL', 'https://httpbin.org/status/200')
    PING_INTERVAL = 300  # 5 минут
    while bot_started:
        try:
            response = requests.get(PING_URL, timeout=10)
            logger.debug(f"Пинг: статус {response.status_code}")
        except Exception as e:
            logger.error(f"Ошибка пинга: {str(e)}")
        time.sleep(PING_INTERVAL)

# Обработчики сообщений
@bot.message_handler(commands=['start'])
def send_welcome(message):
    logger.info(f"Пользователь {message.chat.id} запустил бота")
    bot.send_message(message.chat.id, f"Привет! Я бот для спама в VK. Экземпляр: {INSTANCE_ID}", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "🚀 Спам в группы")
def start_spam_groups(message):
    global SPAM_RUNNING, SPAM_THREADS
    if not VK_Groups:
        bot.send_message(message.chat.id, "Список групп пуст!", reply_markup=main_menu())
        return
    if not vk:
        bot.send_message(message.chat.id, "VK токен не установлен!", reply_markup=main_menu())
        return
    SPAM_RUNNING['groups'] = True
    SPAM_THREADS['groups'] = []
    for chat_id in VK_Groups[:]:
        thread = threading.Thread(target=send_and_delete_vk_messages, args=(chat_id, message.chat.id))
        thread.start()
        SPAM_THREADS['groups'].append(thread)
    bot.send_message(message.chat.id, "Спам запущен в группах VK!", reply_markup=spam_menu('groups'))

@bot.message_handler(func=lambda message: message.text == "🚀 Спам в беседы")
def start_spam_conversations(message):
    global SPAM_RUNNING, SPAM_THREADS
    if not VK_CONVERSATIONS:
        bot.send_message(message.chat.id, "Список бесед пуст!", reply_markup=main_menu())
        return
    if not vk:
        bot.send_message(message.chat.id, "VK токен не установлен!", reply_markup=main_menu())
        return
    SPAM_RUNNING['conversations'] = True
    SPAM_THREADS['conversations'] = []
    for chat_id in VK_CONVERSATIONS[:]:
        thread = threading.Thread(target=send_and_delete_vk_messages, args=(chat_id, message.chat.id))
        thread.start()
        SPAM_THREADS['conversations'].append(thread)
    bot.send_message(message.chat.id, "Спам запущен в беседах VK!", reply_markup=spam_menu('conversations'))

@bot.message_handler(func=lambda message: message.text == "⛔ Отключить спам")
def stop_spam(message):
    global SPAM_RUNNING, SPAM_THREADS
    SPAM_RUNNING['groups'] = False
    SPAM_RUNNING['conversations'] = False
    for thread_type in SPAM_THREADS:
        for thread in SPAM_THREADS[thread_type][:]:
            if thread.is_alive():
                thread.join(timeout=5)
    SPAM_THREADS = {'groups': [], 'conversations': []}
    bot.send_message(message.chat.id, "Спам остановлен!", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "⏳ Установить задержку")
def set_delay_prompt(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("15 сек", callback_data="delay_15"),
        types.InlineKeyboardButton("30 сек", callback_data="delay_30"),
        types.InlineKeyboardButton("1 мин", callback_data="delay_60"),
        types.InlineKeyboardButton("5 мин", callback_data="delay_300")
    )
    bot.send_message(message.chat.id, "Выбери время между действиями:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🕒 Время удаления")
def set_delete_time_prompt(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("15 сек", callback_data="delete_15"),
        types.InlineKeyboardButton("30 сек", callback_data="delete_30"),
        types.InlineKeyboardButton("1 мин", callback_data="delete_60"),
        types.InlineKeyboardButton("5 мин", callback_data="delete_300")
    )
    bot.send_message(message.chat.id, "Выбери время до удаления:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delay_"))
def set_delay_callback(call):
    global DELAY_TIME
    DELAY_TIME = int(call.data.split("_")[1])
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                         text=f"Задержка между действиями: {DELAY_TIME} секунд", reply_markup=None)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Выбери действие:", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
def set_delete_time_callback(call):
    global DELETE_TIME
    DELETE_TIME = int(call.data.split("_")[1])
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                         text=f"Время до удаления: {DELETE_TIME} секунд", reply_markup=None)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Выбери действие:", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "ℹ️ Статус")
def status(message):
    groups_str = ", ".join(map(str, VK_Groups)) if VK_Groups else "Пусто"
    convs_str = ", ".join(map(str, VK_CONVERSATIONS)) if VK_CONVERSATIONS else "Пусто"
    status_msg = f"Задержка: {DELAY_TIME} сек\nВремя удаления: {DELETE_TIME} сек\nШаблон: '{SPAM_TEMPLATE}'\nГруппы: {groups_str}\nБеседы: {convs_str}\nЭкземпляр: {INSTANCE_ID}"
    bot.send_message(message.chat.id, status_msg, reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "➕ Добавить чат")
def add_chat_prompt(message):
    bot.send_message(message.chat.id, "Введи ID чата VK (- для группы, 2000000000+ для беседы):")
    bot.register_next_step_handler(message, add_chat)

def add_chat(message):
    try:
        chat_id = int(message.text)
        if chat_id < 0 and chat_id not in VK_Groups:
            VK_Groups.append(chat_id)
            bot.send_message(message.chat.id, f"Группа {chat_id} добавлена!", reply_markup=main_menu())
        elif chat_id >= 2000000000 and chat_id not in VK_CONVERSATIONS:
            VK_CONVERSATIONS.append(chat_id)
            bot.send_message(message.chat.id, f"Беседа {chat_id} добавлена!", reply_markup=main_menu())
        else:
            bot.send_message(message.chat.id, "Чат уже в списке или неверный ID!", reply_markup=main_menu())
    except ValueError:
        bot.send_message(message.chat.id, "ID должен быть числом!", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "🗑 Удалить чат")
def remove_chat_prompt(message):
    markup = create_remove_chat_keyboard()
    bot.send_message(message.chat.id, "Выберите чат для удаления:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_") or call.data in ["cancel_remove", "no_chats"])
def handle_remove_chat(call):
    global VK_Groups, VK_CONVERSATIONS
    if call.data == "no_chats":
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                            text="Нет чатов для удаления.", reply_markup=None)
    elif call.data == "cancel_remove":
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                            text="Удаление отменено.", reply_markup=None)
    elif call.data.startswith("remove_group_"):
        group_id = int(call.data.split("_")[2])
        if group_id in VK_Groups:
            VK_Groups.remove(group_id)
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                text=f"Группа {group_id} удалена.", reply_markup=None)
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                text=f"Группа {group_id} не найдена.", reply_markup=None)
    elif call.data.startswith("remove_conversation_"):
        conv_id = int(call.data.split("_")[2])
        if conv_id in VK_CONVERSATIONS:
            VK_CONVERSATIONS.remove(conv_id)
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                text=f"Беседа {conv_id} удалена.", reply_markup=None)
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                text=f"Беседа {conv_id} не найдена.", reply_markup=None)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Выбери действие:", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "✍️ Шаблон для спама")
def edit_template_prompt(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Изменить шаблон", callback_data="edit_template"))
    bot.send_message(message.chat.id, f"Текущий шаблон: '{SPAM_TEMPLATE}'", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "edit_template")
def edit_template_callback(call):
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                         text="Введи новый текст для спама:", reply_markup=None)
    bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_template)

def update_template(message):
    global SPAM_TEMPLATE
    SPAM_TEMPLATE = message.text
    bot.send_message(message.chat.id, f"Шаблон обновлён: '{SPAM_TEMPLATE}'", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "🔑 Сменить токен VK")
def change_vk_token_prompt(message):
    bot.send_message(message.chat.id, "Введи новый токен VK API:")
    bot.register_next_step_handler(message, update_vk_token)

def update_vk_token(message):
    global VK_TOKEN, vk_session, vk
    VK_TOKEN = message.text.strip()
    try:
        vk_session = vk_api.VkApi(token=VK_TOKEN)
        vk = vk_session.get_api()
        vk.account.getInfo()
        bot.send_message(message.chat.id, "Токен VK обновлён!", reply_markup=main_menu())
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}. Токен недействителен!", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "🗑 Очистить API VK")
def clear_vk_api_prompt(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Да, очистить", callback_data="confirm_clear"),
        types.InlineKeyboardButton("Отмена", callback_data="cancel_clear")
    )
    bot.send_message(message.chat.id, "Очистить API VK и настройки?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["confirm_clear", "cancel_clear"])
def handle_clear_confirmation(call):
    global VK_TOKEN, vk_session, vk, VK_Groups, VK_CONVERSATIONS, DELAY_TIME, DELETE_TIME, SPAM_TEMPLATE, SPAM_RUNNING, SPAM_THREADS
    if call.data == "confirm_clear":
        SPAM_RUNNING['groups'] = SPAM_RUNNING['conversations'] = False
        for thread_type in SPAM_THREADS:
            for thread in SPAM_THREADS[thread_type][:]:
                if thread.is_alive():
                    thread.join(timeout=5)
        SPAM_THREADS = {'groups': [], 'conversations': []}
        VK_TOKEN = ''
        vk_session = None
        vk = None
        VK_Groups = []
        VK_CONVERSATIONS = []
        DELAY_TIME = 15
        DELETE_TIME = 15
        SPAM_TEMPLATE = "Первое сообщение"
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                            text="API VK очищен! Нужен новый токен.", reply_markup=None)
    else:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                            text="Очистка отменена.", reply_markup=None)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Выбери действие:", reply_markup=main_menu())

# Вебхук обработчик
@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        logger.debug(f"Получено обновление: {json_string}")
        bot.process_new_updates([update])
        return Response('OK', status=200)
    else:
        return Response('Invalid content type', status=403)

@app.route('/')
def index():
    return "Бот работает!"

# Функция настройки вебхука
def setup_webhook():
    max_retries = 5
    retries = 0
    while retries < max_retries:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=WEBHOOK_FULL_URL)
            webhook_info = bot.get_webhook_info()
            if webhook_info.url == WEBHOOK_FULL_URL:
                logger.info(f"Webhook успешно установлен: {WEBHOOK_FULL_URL}")
                return True
            else:
                logger.warning(f"Webhook не совпадает: {webhook_info.url}")
        except Exception as e:
            retries += 1
            logger.error(f"Ошибка установки webhook (попытка {retries}/{max_retries}): {str(e)}")
            time.sleep(5 * retries)
    logger.error("Не удалось установить webhook")
    return False

# Обработка сигналов
def signal_handler(sig, frame):
    global bot_started
    logger.info(f"Завершение экземпляра {INSTANCE_ID}")
    bot_started = False
    bot.remove_webhook()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Запуск бота
if __name__ == "__main__":
    logger.info(f"Запуск бота, экземпляр: {INSTANCE_ID}")
    bot_started = True

    # Установка вебхука
    if not setup_webhook():
        logger.error("Не удалось настроить вебхук. Завершение.")
        sys.exit(1)

    # Запуск пингования в отдельном потоке
    ping_thread = threading.Thread(target=ping_service, daemon=True)
    ping_thread.start()

    # Использование Gunicorn для Railway
    port = int(os.getenv('PORT', 5000))
    try:
        from gunicorn.app.base import BaseApplication

        class StandaloneApplication(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()

            def load_config(self):
                for key, value in self.options.items():
                    self.cfg.set(key.lower(), value)

            def load(self):
                return self.application

        options = {
            'bind': f'0.0.0.0:{port}',
            'workers': 1,
            'timeout': 60,
        }
        StandaloneApplication(app, options).run()
    except ImportError:
        logger.error("Gunicorn не установлен. Установите его с помощью 'pip install gunicorn'.")
        sys.exit(1)
