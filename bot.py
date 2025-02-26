import os
import telebot
import vk_api
import time
import threading
import requests
from telebot import types
from dotenv import load_dotenv
import signal
import sys
import logging

# Настройка логирования для Render (логи выводятся в stdout)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загрузка переменных окружения из .env (для совместимости, но токен Telegram вставлен напрямую ниже)
load_dotenv()

# Токены для Telegram и VK
# Временное решение: вставляем токен Telegram напрямую для тестирования на Render
# В продакшене рекомендуется настроить TELEGRAM_TOKEN в переменных окружения на Render для безопасности
TELEGRAM_TOKEN = '7506083870:AAFePsqVIvR-8iKfZ9QAc43n7MFqvQKJEMA'
if not TELEGRAM_TOKEN or any(char.isspace() for char in TELEGRAM_TOKEN):
    logger.error("TELEGRAM_TOKEN не задан или содержит пробелы. Убедитесь, что он правильно настроен в переменных окружения.")
    raise ValueError("TELEGRAM_TOKEN отсутствует или некорректен. Настройте его в .env или в настройках Render.")

VK_TOKEN = os.getenv('VK_TOKEN', '')  # Значение по умолчанию — пустая строка

# Инициализация бота Telegram
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Инициализация VK API
vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()

# Списки для групп и бесед
VK_Groups = [-211223344, -155667788, -199887766, -188445566, -177334455]  # Группы
VK_CONVERSATIONS = [2000000001, 2000000005]  # Беседы
DELAY_TIME = 15  # Задержка между действиями (секунды)
DELETE_TIME = 15  # Время до удаления (секунды)
SPAM_RUNNING = {'groups': False, 'conversations': False}  # Флаги спама
SPAM_THREADS = {'groups': [], 'conversations': []}  # Потоки спама
SPAM_TEMPLATE = "Первое сообщение"  # Шаблон по умолчанию

# Глобальная переменная для отслеживания статуса бота
bot_started = False

# Основная клавиатура
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🚀 Спам в группы"),
        types.KeyboardButton("🚀 Спам в беседы"),
        types.KeyboardButton("⏳ Установить задержку"),
        types.KeyboardButton("🕒 Время удаления"),
        types.KeyboardButton("ℹ️ Статус"),
        types.KeyboardButton("➕ Добавить чат"),
        types.KeyboardButton("✍️ Шаблон для спама"),
        types.KeyboardButton("🔑 Сменить токен VK"),
        types.KeyboardButton("🗑 Очистить API VK")
    )
    return markup

# Клавиатура с кнопкой отключения
def spam_menu(spam_type):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("⛔ Отключить спам"))
    markup.add(
        types.KeyboardButton("🚀 Спам в группы"),
        types.KeyboardButton("🚀 Спам в беседы"),
        types.KeyboardButton("⏳ Установить задержку"),
        types.KeyboardButton("🕒 Время удаления"),
        types.KeyboardButton("ℹ️ Статус"),
        types.KeyboardButton("➕ Добавить чат"),
        types.KeyboardButton("✍️ Шаблон для спама"),
        types.KeyboardButton("🔑 Сменить токен VK"),
        types.KeyboardButton("🗑 Очистить API VK")
    )
    return markup

# Функция спама
def send_and_delete_vk_messages(chat_id, telegram_chat_id):
    global DELAY_TIME, DELETE_TIME, SPAM_TEMPLATE
    while SPAM_RUNNING['groups'] if chat_id < 0 else SPAM_RUNNING['conversations']:
        try:
            msg1 = vk.messages.send(peer_id=chat_id, message=SPAM_TEMPLATE, random_id=int(time.time() * 1000))
            logger.info(f"Отправлено '{SPAM_TEMPLATE}' в VK чат {chat_id}")
            bot.send_message(telegram_chat_id, f"Отправлено '{SPAM_TEMPLATE}' в VK чат {chat_id}")
            time.sleep(DELETE_TIME)
            vk.messages.delete(message_ids=[msg1], delete_for_all=1)
            logger.info(f"Удалено сообщение в VK чат {chat_id}")
            bot.send_message(telegram_chat_id, f"Удалено сообщение в VK чат {chat_id}")
            time.sleep(DELAY_TIME - DELETE_TIME if DELAY_TIME > DELETE_TIME else 0)
        except Exception as e:
            logger.error(f"Ошибка в чате {chat_id}: {str(e)}")
            bot.send_message(telegram_chat_id, f"Ошибка в чате {chat_id}: {str(e)}")
            break

# Функция пингования
def ping_service():
    global bot_started
    PING_URL = "https://httpbin.org/status/200"  # URL для пинга, возвращающий код 200
    PING_INTERVAL = 300  # Интервал пинга в секундах (5 минут)

    while bot_started:
        try:
            response = requests.get(PING_URL, timeout=10)
            if response.status_code == 200:
                logger.info("Пинг успешен (статус 200)")
            else:
                logger.warning(f"Пинг вернул статус {response.status_code}")
        except Exception as e:
            logger.error(f"Ошибка пинга: {str(e)}")
        time.sleep(PING_INTERVAL)

# Приветственное сообщение
@bot.message_handler(commands=['start'])
def send_welcome(message):
    logger.info(f"Пользователь {message.chat.id} запустил бота")
    bot.send_message(message.chat.id, "Привет! Я бот для спама в VK.", reply_markup=main_menu())

# Спам в группы
@bot.message_handler(func=lambda message: message.text == "🚀 Спам в группы")
def start_spam_groups(message):
    global SPAM_RUNNING, SPAM_THREADS
    if not VK_Groups:
        logger.warning("Список групп пуст!")
        bot.send_message(message.chat.id, "Список групп пуст!", reply_markup=main_menu())
        return
    SPAM_RUNNING['groups'] = True
    SPAM_THREADS['groups'] = []
    for chat_id in VK_Groups:
        thread = threading.Thread(target=send_and_delete_vk_messages, args=(chat_id, message.chat.id))
        thread.start()
        SPAM_THREADS['groups'].append(thread)
    logger.info("Спам запущен в группах VK!")
    bot.send_message(message.chat.id, "Спам запущен в группах VK!", reply_markup=spam_menu('groups'))

# Спам в беседы
@bot.message_handler(func=lambda message: message.text == "🚀 Спам в беседы")
def start_spam_conversations(message):
    global SPAM_RUNNING, SPAM_THREADS
    if not VK_CONVERSATIONS:
        logger.warning("Список бесед пуст!")
        bot.send_message(message.chat.id, "Список бесед пуст!", reply_markup=main_menu())
        return
    SPAM_RUNNING['conversations'] = True
    SPAM_THREADS['conversations'] = []
    for chat_id in VK_CONVERSATIONS:
        thread = threading.Thread(target=send_and_delete_vk_messages, args=(chat_id, message.chat.id))
        thread.start()
        SPAM_THREADS['conversations'].append(thread)
    logger.info("Спам запущен в беседах VK!")
    bot.send_message(message.chat.id, "Спам запущен в беседах VK!", reply_markup=spam_menu('conversations'))

# Отключение спама
@bot.message_handler(func=lambda message: message.text == "⛔ Отключить спам")
def stop_spam(message):
    global SPAM_RUNNING
    SPAM_RUNNING['groups'] = False
    SPAM_RUNNING['conversations'] = False
    logger.info("Спам остановлен!")
    bot.send_message(message.chat.id, "Спам остановлен!", reply_markup=main_menu())

# Установить задержку
@bot.message_handler(func=lambda message: message.text == "⏳ Установить задержку")
def set_delay_prompt(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("15 сек", callback_data="delay_15"),
        types.InlineKeyboardButton("30 сек", callback_data="delay_30"),
        types.InlineKeyboardButton("1 мин", callback_data="delay_60"),
        types.InlineKeyboardButton("5 мин", callback_data="delay_300")
    )
    logger.info(f"Пользователь {message.chat.id} запросил установку задержки")
    bot.send_message(message.chat.id, "Выбери время между действиями:", reply_markup=markup)

# Установить время удаления
@bot.message_handler(func=lambda message: message.text == "🕒 Время удаления")
def set_delete_time_prompt(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("15 сек", callback_data="delete_15"),
        types.InlineKeyboardButton("30 сек", callback_data="delete_30"),
        types.InlineKeyboardButton("1 мин", callback_data="delete_60"),
        types.InlineKeyboardButton("5 мин", callback_data="delete_300")
    )
    logger.info(f"Пользователь {message.chat.id} запросил установку времени удаления")
    bot.send_message(message.chat.id, "Выбери время до удаления:", reply_markup=markup)

# Обработка задержки
@bot.callback_query_handler(func=lambda call: call.data.startswith("delay_"))
def set_delay_callback(call):
    global DELAY_TIME
    DELAY_TIME = int(call.data.split("_")[1])
    logger.info(f"Задержка установлена на {DELAY_TIME} секунд пользователем {call.message.chat.id}")
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                          text=f"Задержка между действиями: {DELAY_TIME} секунд", reply_markup=None)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Выбери действие:", reply_markup=main_menu())

# Обработка времени удаления
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
def set_delete_time_callback(call):
    global DELETE_TIME
    DELETE_TIME = int(call.data.split("_")[1])
    logger.info(f"Время удаления установлено на {DELETE_TIME} секунд пользователем {call.message.chat.id}")
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                          text=f"Время до удаления: {DELETE_TIME} секунд", reply_markup=None)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Выбери действие:", reply_markup=main_menu())

# Статус
@bot.message_handler(func=lambda message: message.text == "ℹ️ Статус")
def status(message):
    groups_str = ", ".join(map(str, VK_Groups)) if VK_Groups else "Пусто"
    convs_str = ", ".join(map(str, VK_CONVERSATIONS)) if VK_CONVERSATIONS else "Пусто"
    status_msg = f"Задержка: {DELAY_TIME} сек\nВремя удаления: {DELETE_TIME} сек\nШаблон: '{SPAM_TEMPLATE}'\nГруппы: {groups_str}\nБеседы: {convs_str}"
    logger.info(f"Пользователь {message.chat.id} запросил статус: {status_msg}")
    bot.send_message(message.chat.id, status_msg, reply_markup=main_menu())

# Добавить чат
@bot.message_handler(func=lambda message: message.text == "➕ Добавить чат")
def add_chat_prompt(message):
    logger.info(f"Пользователь {message.chat.id} запросил добавление чата")
    bot.send_message(message.chat.id, "Введи ID чата VK (- для группы, 2000000000+ для беседы):")
    bot.register_next_step_handler(message, add_chat)

def add_chat(message):
    try:
        chat_id = int(message.text)
        if chat_id < 0:
            if chat_id not in VK_Groups:
                VK_Groups.append(chat_id)
                logger.info(f"Группа {chat_id} добавлена пользователем {message.chat.id}")
                bot.send_message(message.chat.id, f"Группа {chat_id} добавлена!", reply_markup=main_menu())
            else:
                logger.warning(f"Группа {chat_id} уже в списке для пользователя {message.chat.id}")
                bot.send_message(message.chat.id, "Группа уже в списке!", reply_markup=main_menu())
        elif chat_id >= 2000000000:
            if chat_id not in VK_CONVERSATIONS:
                VK_CONVERSATIONS.append(chat_id)
                logger.info(f"Беседа {chat_id} добавлена пользователем {message.chat.id}")
                bot.send_message(message.chat.id, f"Беседа {chat_id} добавлена!", reply_markup=main_menu())
            else:
                logger.warning(f"Беседа {chat_id} уже в списке для пользователя {message.chat.id}")
                bot.send_message(message.chat.id, "Беседа уже в списке!", reply_markup=main_menu())
        else:
            logger.error(f"Неверный ID чата от пользователя {message.chat.id}")
            bot.send_message(message.chat.id, "Неверный ID!", reply_markup=main_menu())
    except ValueError:
        logger.error(f"Некорректный ввод ID от пользователя {message.chat.id}")
        bot.send_message(message.chat.id, "ID — число!", reply_markup=main_menu())

# Шаблон для спама
@bot.message_handler(func=lambda message: message.text == "✍️ Шаблон для спама")
def edit_template_prompt(message):
    logger.info(f"Пользователь {message.chat.id} запросил изменение шаблона")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Изменить шаблон", callback_data="edit_template"))
    bot.send_message(message.chat.id, f"Текущий шаблон: '{SPAM_TEMPLATE}'", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "edit_template")
def edit_template_callback(call):
    logger.info(f"Пользователь {call.message.chat.id} начал редактирование шаблона")
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                          text="Введи новый текст для спама:", reply_markup=None)
    bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_template)

def update_template(message):
    global SPAM_TEMPLATE
    SPAM_TEMPLATE = message.text
    logger.info(f"Шаблон обновлён пользователем {message.chat.id} на: '{SPAM_TEMPLATE}'")
    bot.send_message(message.chat.id, f"Шаблон обновлён: '{SPAM_TEMPLATE}'", reply_markup=main_menu())

# Смена токена VK
@bot.message_handler(func=lambda message: message.text == "🔑 Сменить токен VK")
def change_vk_token_prompt(message):
    logger.info(f"Пользователь {message.chat.id} запросил смену токена VK")
    bot.send_message(message.chat.id, "Введи новый токен VK API:")
    bot.register_next_step_handler(message, update_vk_token)

def update_vk_token(message):
    global VK_TOKEN, vk_session, vk
    new_token = message.text.strip()
    VK_TOKEN = new_token
    try:
        vk_session = vk_api.VkApi(token=VK_TOKEN)
        vk = vk_session.get_api()
        vk.account.getInfo()  # Проверка токена
        logger.info(f"Токен VK успешно обновлён пользователем {message.chat.id}")
        bot.send_message(message.chat.id, "Токен VK успешно обновлён!", reply_markup=main_menu())
    except Exception as e:
        logger.error(f"Ошибка обновления токена для пользователя {message.chat.id}: {str(e)}")
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}. Токен недействителен!", reply_markup=main_menu())

# Очистка API VK с подтверждением
@bot.message_handler(func=lambda message: message.text == "🗑 Очистить API VK")
def clear_vk_api_prompt(message):
    logger.info(f"Пользователь {message.chat.id} запросил очистку API VK")
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Да, очистить", callback_data="confirm_clear"),
        types.InlineKeyboardButton("Отмена", callback_data="cancel_clear")
    )
    bot.send_message(message.chat.id, "Вы уверены, что хотите полностью очистить API VK и настройки?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["confirm_clear", "cancel_clear"])
def handle_clear_confirmation(call):
    if call.data == "confirm_clear":
        global VK_TOKEN, vk_session, vk, VK_Groups, VK_CONVERSATIONS, DELAY_TIME, DELETE_TIME, SPAM_TEMPLATE, SPAM_RUNNING, SPAM_THREADS
        
        # Остановка всех активных спам-потоков
        SPAM_RUNNING['groups'] = False
        SPAM_RUNNING['conversations'] = False
        for threads in SPAM_THREADS.values():
            for thread in threads:
                if thread and thread.is_alive():
                    thread.join()  # Дождаться завершения потоков
        SPAM_THREADS = {'groups': [], 'conversations': []}

        # Сброс токена и данных VK
        VK_TOKEN = ''
        vk_session = None
        vk = None
        VK_Groups = []
        VK_CONVERSATIONS = []

        # Возвращаем настройки по умолчанию
        DELAY_TIME = 15
        DELETE_TIME = 15
        SPAM_TEMPLATE = "Первое сообщение"

        logger.info(f"API VK и настройки очищены пользователем {call.message.chat.id}")
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text="API VK и все настройки успешно очищены! Требуется новый токен VK для работы.", reply_markup=main_menu())
    else:
        logger.info(f"Очистка API VK отменена пользователем {call.message.chat.id}")
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text="Очистка отменена.", reply_markup=main_menu())
    bot.answer_callback_query(call.id)

# Обработка сигналов для graceful shutdown
def signal_handler(sig, frame):
    global bot_started
    logger.info('Получен сигнал для завершения...')
    bot_started = False  # Останавливаем пингование
    bot.stop_polling()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Запуск бота с пингованием
if __name__ == "__main__":
    logger.info("Бот запущен")
    bot_started = True  # Устанавливаем флаг, что бот запущен

    # Запуск пингования в отдельном потоке
    ping_thread = threading.Thread(target=ping_service, daemon=True)
    ping_thread.start()

    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {str(e)}")
        bot_started = False  # Останавливаем пингование при ошибке
        sys.exit(1)
