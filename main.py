import telebot
from telebot import types
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import time
import json
import psycopg2
import os
from flask import Flask
from threading import Thread
import time

# 🛡️ معرفك الشخصي (لتقييد التحكم بك فقط)
ADMIN_ID = int(os.getenv('ADMIN_ID'))  # 🔁 استبدله بـ Telegram ID 
# 🎯 توكن البوت
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
# 🎯 رابط قاعدة بيانات PostgreSQL من Render
DATABASE_URL = os.getenv('DATABASE_URL')
# قبل أي شيء:
REQUIRED_CHANNEL = "@YMN_SPIRIT"  # القناة المطلوبة


# 🔹 إنشاء الجداول في PostgreSQL
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS channels (
        id BIGINT PRIMARY KEY
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS message (
        id SERIAL PRIMARY KEY,
        text TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS posted (
        chat_id BIGINT,
        msg_id BIGINT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS buttons (
        id SERIAL PRIMARY KEY,
        text TEXT,
        url TEXT
    );
    """)
    conn.commit()
    cur.close()
    conn.close()


def check_subscription(user_id):
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ['member', 'creator', 'administrator']:
            return True
        return False
    except Exception as e:
        print(f"Error checking subscription: {e}")
        return False

# 📥 تحميل/حفظ القنوات
# 📥 دوال للتعامل مع القنوات
def load_channels():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id FROM channels")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def save_channel(chat_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("INSERT INTO channels (id) VALUES (%s) ON CONFLICT DO NOTHING", (chat_id,))
    conn.commit()
    cur.close()
    conn.close()

def delete_channel(chat_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM channels WHERE id=%s", (chat_id,))
    conn.commit()
    cur.close()
    conn.close()

# 📥 دوال للرسالة
def load_message():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT text FROM message ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def save_message(text):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM message")
    cur.execute("INSERT INTO message (text) VALUES (%s)", (text,))
    conn.commit()
    cur.close()
    conn.close()

# 📥 دوال للرسائل المنشورة
def save_posted(chat_id, msg_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("INSERT INTO posted (chat_id, msg_id) VALUES (%s, %s)", (chat_id, msg_id))
    conn.commit()
    cur.close()
    conn.close()

def load_posted():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT chat_id, msg_id FROM posted")
    rows = cur.fetchall()
    conn.close()
    return rows

def clear_posted():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM posted")
    conn.commit()
    cur.close()
    conn.close()

def save_button(text, url):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("INSERT INTO buttons (text, url) VALUES (%s, %s)", (text, url))
    conn.commit()
    cur.close()
    conn.close()

def load_buttons():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT text, url FROM buttons")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def clear_buttons():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM buttons")
    conn.commit()
    cur.close()
    conn.close()

def get_dynamic_buttons():
    buttons = load_buttons()
    if buttons:  # إذا فيه أزرار مضافة
        markup = types.InlineKeyboardMarkup()
        for text, url in buttons:
            markup.add(types.InlineKeyboardButton(text, url=url))
        return markup
    else:  # إذا ما فيه أزرار مضافة → استخدم الزر الثابت
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📡 قنوات جهادية", url="https://t.me/addlist/5gK4-CGwMuVhZGFk"))
        return markup
# زر للقنوات
def get_fixed_button():
    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton("قنوات جهادية", url="https://t.me/addlist/5gK4-CGwMuVhZGFk")
    markup.add(button)
    return markup

# 🔍 رسالة المساعدة
@bot.message_handler(commands=['help'])
def help_message(message):
    help_m = """
🤖 PlusForChanelBot – لستة دعم القنوات

هذا البوت يساعد في دعم القنوات الجهادية بنشر رسالة موحدة يوميًا تتضمن قائمة القنوات المشاركة.
This bot helps support jihad-focused channels by posting a unified daily message with the list of participating channels.

🔹 أوامر المستخدم (User Commands):
/start – بدء استخدام البوت  
/help – عرض هذه الرسالة المساعدة  

🔐 أوامر المشرف (Admin Commands):
/show_channels – عرض جميع القنوات المسجلة  
/show_message – عرض رسالة اليوم المجدولة  
/delete_message – حذف الرسالة يدويًا
/addchannel – إضافة قناتك إلى قائمة الدعم  
/removechannel – إزالة قناتك من القائمة

🕙 ملاحظة | Note:
⏰ يتم نشر الرسالة تلقائيًا الساعة 11:00 مساءً  
🗑 ويتم حذفها تلقائيًا الساعة 6:00 صباحًا

💬 للتواصل أو الدعم: @RohThoryaBot
"""
    bot.reply_to(message, help_m)

# 🔍 عرض القنوات
@bot.message_handler(commands=['show_channels'])
def show_channels(message):
    if message.from_user.id != ADMIN_ID:
        return
    channels = load_channels()
    if not channels:
        bot.reply_to(message, "🚫 لا توجد قنوات مسجلة.")
        return
    result = "📋 القنوات المسجلة:\n\n"
    for chat_id in channels:
        try:
            chat = bot.get_chat(chat_id)
            title = chat.title or "بدون اسم"
            username = chat.username
            if username:
                result += f"🔹 [{title}](https://t.me/{username})\n[{chat_id}]\n"
            else:
                result += f"🔹 {title} (لا يوجد معرف)\n"
        except Exception as e:
            result += f"⚠️ لا يمكن جلب بيانات القناة: {chat_id}\n"
    bot.send_message(message.chat.id, result)

def normalize_chat_id(text):
    try:
        if text.startswith("http"):
            # لو رابط
            username = text.split("t.me/")[-1].replace("/", "").strip()
            chat = bot.get_chat(username)
            return chat.id
        elif text.startswith("@"):
            # لو يوزر
            chat = bot.get_chat(text)
            return chat.id
        else:
            # لو آيدي مباشر
            return int(text)
    except Exception as e:
        return None

# ➕ إضافة قناة
@bot.message_handler(commands=['addchannel'])
def add_channel(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ غير مسموح.")
        return
    
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ استخدم الأمر هكذا:\n`/addchannel @username` أو بالرابط أو الآيدي", parse_mode="Markdown")
            return
        
        chat_id = normalize_chat_id(parts[1].strip())
        if not chat_id:
            bot.reply_to(message, "❌ لم أستطع التعرف على القناة.")
            return
        
        channels = load_channels()
        if chat_id in channels:
            bot.reply_to(message, "ℹ️ القناة مسجلة بالفعل.")
        else:
            save_channel(chat_id)
            chat = bot.get_chat(chat_id)
            bot.reply_to(message, f"✅ تمت إضافة القناة:\n📛 {chat.title}\n🆔 `{chat_id}`", parse_mode="Markdown")
    
    except Exception as e:
        bot.reply_to(message, f"❌ خطأ: {e}")

# ➖ حذف قناة
@bot.message_handler(commands=['removechannel'])
def remove_channel(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ غير مسموح.")
        return
    
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ استخدم الأمر هكذا:\n`/removechannel @username` أو بالرابط أو الآيدي", parse_mode="Markdown")
            return
        
        chat_id = normalize_chat_id(parts[1].strip())
        if not chat_id:
            bot.reply_to(message, "❌ لم أستطع التعرف على القناة.")
            return
        
        channels = load_channels()
        if chat_id not in channels:
            bot.reply_to(message, "⚠️ القناة غير موجودة في القائمة.")
        else:
            delete_channel(chat_id)
            chat = bot.get_chat(chat_id)
            bot.reply_to(message, f"🗑️ تم حذف القناة:\n📛 {chat.title}\n🆔 `{chat_id}`", parse_mode="Markdown")
    
    except Exception as e:
        bot.reply_to(message, f"❌ خطأ: {e}")

@bot.message_handler(commands=['show_message'])
def show_scheduled_message(message):
    if message.from_user.id != ADMIN_ID:
        return
    msg = load_message()
    if msg:
        bot.reply_to(message, f"📨 الرسالة الحالية:\n\n{msg}",reply_markup=get_dynamic_buttons())
    else:
        bot.reply_to(message, "📭 لا توجد رسالة محفوظة حالياً.")

@bot.message_handler(commands=['delete_message'])
def delete_scheduled_message(message):
    if message.from_user.id != ADMIN_ID:
        return
    save_message("")  
    bot.reply_to(message, "🗑️ تم حذف الرسالة.")

# 🟢 ترحيب
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not check_subscription(message.from_user.id):
        bot.send_message(message.chat.id, f"❌ لا يمكنك استخدام البوت حتى تشترك في القناة {REQUIRED_CHANNEL}")
        return

    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "👋 أهلاً! أرسل الرسالة التي تريد نشرها. سيتم نشرها الساعة 11 مساءً وحذفها الساعة 6 صباحًا بإذن الله.")
    else:
        bot.reply_to(message,
            "👋 أهلاً!\n"
            "📡 أرسل رابط قناتك، وتأكد من جعل البوت مشرفًا فيها.\n"
            "💬 سيتم إضافة قناتك في قائمة الدعم.\n"
            "❗ إن لم تُضاف، راسل المسؤول: @RohThoryaBot\n\n"
            "⏰ سيتم نشر الرسالة الساعة 11 مساءً وحذفها الساعة 6 صباحًا تلقائيًا.\n"
            "⚠️ لا تقم بحذف الرسالة بنفسك."
                    )

# 📤 نشر يدوي عبر أمر
@bot.message_handler(commands=['sendpost'])
def manual_post(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ غير مسموح لك.")
        return
    post_scheduled_message()

# 🗑️ حذف يدوي عبر أمر
@bot.message_handler(commands=['removeposts'])
def manual_remove(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ غير مسموح لك.")
        return
    delete_scheduled_messages()

@bot.message_handler(commands=['addbutton'])
def add_button(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        # صيغة: /addbutton نص الزر - الرابط
        parts = message.text.split("-", 1)
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ استخدم الأمر هكذا:\n`/addbutton نص الزر - الرابط`", parse_mode="Markdown")
            return
        text = parts[0].replace("/addbutton", "").strip()
        url = parts[1].strip()
        save_button(text, url)
        bot.reply_to(message, f"✅ تمت إضافة زر: [{text}]({url})", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ خطأ: {e}")

@bot.message_handler(commands=['showbuttons'])
def show_buttons(message):
    if message.from_user.id != ADMIN_ID:
        return
    buttons = load_buttons()
    if not buttons:
        bot.reply_to(message, "🚫 لا توجد أزرار حالياً.")
        return
    result = "📋 الأزرار الحالية:\n\n"
    for i, (text, url) in enumerate(buttons, start=1):
        result += f"{i}. [{text}]({url})\n"
    bot.send_message(message.chat.id, result, parse_mode="Markdown")

@bot.message_handler(commands=['clearbuttons'])
def clear_all_buttons(message):
    if message.from_user.id != ADMIN_ID:
        return
    clear_buttons()
    bot.reply_to(message, "🗑️ تم مسح كل الأزرار.")

# ✅ إذا رد الأدمن على رسالة تحتوي على رقم ID، يتم إرسال الرد للمستخدم
@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and message.reply_to_message)
def reply_to_user(message):
    try:
        # نحصل على نص الرسالة التي تم الرد عليها
        replied_text = message.reply_to_message.text.strip()
        # تأكد أن الرسالة تحتوي على رقم ID صالح
        if not replied_text.isdigit():
            bot.reply_to(message, "⚠️ الرسالة التي ترد عليها لا تحتوي على رقم ID صحيح.")
            return
        user_id = int(replied_text)
        bot.send_message(user_id, f"💬 رد المسؤول:\n{message.text}")
        bot.reply_to(message, "✅ تم إرسال الرد للمستخدم.")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ:\n{e}")

# 📝 استقبال رسائل المستخدمين اليومية
@bot.message_handler(func=lambda message: message.from_user.id != ADMIN_ID)
def handle_message(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_state = user_states.get(user_id)

    # التحقق من الاشتراك الإجباري
    if not check_subscription(user_id):
        bot.send_message(chat_id, f"❌ لا يمكنك استخدام البوت حتى تشترك في القناة {REQUIRED_CHANNEL}")
        return

    # أي رسالة أخرى من المستخدم
    bot.reply_to(
        message,
        "📡 أرسل رابط قناتك وتأكد من جعل البوت مشرفًا فيها.\n"
        "✳️ سيتم إضافتها إلى قائمة الدعم.\n"
        "راسل المسؤول: @RohThoryaBot"
    )
    bot.forward_message(ADMIN_ID, chat_id, message.message_id)
    bot.send_message(ADMIN_ID, f"{user_id}")
    return

def safe_get_chat_member(chat_id, user_id, retries=3):
    for i in range(retries):
        try:
            return bot.get_chat_member(chat_id, user_id)
        except Exception as e:
            if i < retries - 1:
                time.sleep(2)  # انتظر ثانيتين ثم حاول مجددًا
            else:
                raise e

# 🛰️ تسجيل أي قناة أُضيف إليها البوت فقط لو كان أدمن
@bot.channel_post_handler(func=lambda m: True)
def register_channel(message):
    chat = message.chat

    try:
        # التحقق من صلاحيات البوت في القناة (مع إعادة المحاولة)
        try:
            member = safe_get_chat_member(chat.id, bot.get_me().id)
        except Exception as e:
            bot.send_message(ADMIN_ID, f"❌ لم أستطع التحقق من القناة {chat.title}\n🔎 السبب: {e}")
            return

        if member.status in ["administrator", "creator"]:
            channels = load_channels()
            if chat.id not in channels:
                save_channel(chat.id)
                bot.send_message(ADMIN_ID, f"✅ تم تسجيل القناة: {chat.title}\n🆔 {chat.id}")
        else:
            # ❌ البوت مش أدمن
            if chat.username:
                invite_link = f"https://t.me/{chat.username}"
            else:
                try:
                    invite_link = bot.create_chat_invite_link(chat.id).invite_link
                except:
                    invite_link = "🔒 لا يمكن جلب الرابط (قناة خاصة أو صلاحيات ناقصة)"

            bot.send_message(
                ADMIN_ID,
                f"⚠️ القناة لم تُسجَّل لأن البوت ليس مشرفًا:\n\n"
                f"📛 الاسم: {chat.title}\n"
                f"🆔 ID: {chat.id}\n"
                f"🔗 الرابط: {invite_link}"
            )

    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ خطأ أثناء التحقق من قناة: {chat.title}\n{e}")

@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID)
def handle_admin_message(message):
    # 📝 حفظ الرسالة اليومية
    save_message(message.text)
    bot.reply_to(message, "✅ تم حفظ الرسالة اليومية بنجاح.")

# 📤 نشر الرسالة الساعة 11 مساءً
def post_scheduled_message():
    text = load_message()
    if not text:
        bot.send_message(ADMIN_ID,"لا يوجد ما يتم نشرة .")
        return
    channels = load_channels()
    for chat_id in channels:
        try:
            msg = bot.send_message(chat_id, text, reply_markup=get_dynamic_buttons())
            save_posted(chat_id, msg.message_id)
        except Exception as e:
            bot.send_message(ADMIN_ID,f"⚠️ خطأ في {chat_id}: {e}")
    bot.send_message(ADMIN_ID,"✅ تم النشر.")

# 🗑️ حذف الرسائل الساعة 6 صباحًا
def delete_scheduled_messages():
    posted = load_posted()
    for chat_id, msg_id in posted:
        try:
            bot.delete_message(chat_id, msg_id)
        except Exception as e:
            bot.send_message(ADMIN_ID, f"⚠️ خطأ عند الحذف من {chat_id}: {e}")
    clear_posted()
    bot.send_message(ADMIN_ID,"🗑️ تم الحذف.")

# ⏱️ جدولة المهام
scheduler = BackgroundScheduler(timezone="Asia/Aden")
scheduler.add_job(post_scheduled_message, 'cron', hour=23, minute=0)  # 11:00 PM
scheduler.add_job(delete_scheduled_messages, 'cron', hour=6, minute=0)  # 6:00 AM

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()


# 🚀 تشغيل
if __name__ == "__main__":
    init_db()
    keep_alive()
    scheduler.start()
    print("🤖 البوت يعمل الآن...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"❌ خطأ: {e}")
            time.sleep(30)








