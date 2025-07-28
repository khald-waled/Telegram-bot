import telebot
from telebot import types
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import time
import json
import os
from flask import Flask
from threading import Thread



# 🛡️ معرفك الشخصي (لتقييد التحكم بك فقط)
ADMIN_ID = 6459379370  # 🔁 استبدله بـ Telegram ID 

# 🎯 توكن البوت
TOKEN = '8295507669:AAEDIgSPlKMEzCxFWe9CDRSZaF-OMPbagPE'
bot = telebot.TeleBot(TOKEN)

# 📂 ملفات التخزين
CHANNELS_FILE = 'channels.json'
MESSAGE_FILE = 'message.json'
POSTED_FILE = 'posted.json'

# قبل أي شيء:
REQUIRED_CHANNEL = "@YMN_SPIRIT"  # القناة المطلوبة

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
def load_channels():
    if os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_channels(channels):
    with open(CHANNELS_FILE, 'w') as f:
        json.dump(channels, f)

# 📥 تحميل/حفظ الرسالة
def load_message():
    if os.path.exists(MESSAGE_FILE):
        with open(MESSAGE_FILE, 'r') as f:
            return json.load(f).get('text')
    return None

def save_message(text):
    with open(MESSAGE_FILE, 'w') as f:
        json.dump({'text': text}, f)

# 📥 حفظ/تحميل رسائل تم نشرها (لحذفها لاحقًا)
def save_posted(posted):
    with open(POSTED_FILE, 'w') as f:
        json.dump(posted, f)

def load_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, 'r') as f:
            return json.load(f)
    return {}


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
    if message.from_user.id != ADMIN_ID:
        if not check_subscription(message.from_user.id):
            bot.send_message(message.chat.id, f"❌ لا يمكنك استخدام البوت حتى تشترك في القناة {REQUIRED_CHANNEL}")
            return
        else:
            bot.reply_to(message,
                "📡 أرسل رابط قناتك وتأكد من جعل البوت مشرفًا فيها.\n"
                "✳️ سيتم إضافتها إلى قائمة الدعم.\n"
                "راسل المسؤول: @RohThoryaBot"
            )
            bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
            bot.send_message(ADMIN_ID, f"{message.from_user.id}")
            return

    # فقط لو المرسل هو الأدمن
    save_message(message.text)
    bot.reply_to(message, "✅ تم حفظ الرسالة اليومية بنجاح.")

# 📝 استقبال رسالتك اليومية
@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID)
def handle_admin_message(message):
    if message.from_user.id != ADMIN_ID:
        if not check_subscription(message.from_user.id):
            bot.send_message(message.chat.id, f"❌ لا يمكنك استخدام البوت حتى تشترك في القناة {REQUIRED_CHANNEL}")
            return
        else:
            bot.reply_to(message,
                "📡 أرسل رابط قناتك وتأكد من جعل البوت مشرفًا فيها.\n"
                "✳️ سيتم إضافتها إلى قائمة الدعم.\n"
                "راسل المسؤول: @RohThoryaBot"
            )
            bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
            bot.send_message(ADMIN_ID, f"{message.from_user.id}")
            return

    # فقط لو المرسل هو الأدمن
    save_message(message.text)
    bot.reply_to(message, "✅ تم حفظ الرسالة اليومية بنجاح.")


# 🛰️ تسجيل أي قناة أُضيف إليها البوت
@bot.channel_post_handler(func=lambda m: True)
def register_channel(message):
    channels = load_channels()
    if message.chat.id not in channels:
        channels.append(message.chat.id)
        save_channels(channels)
        print(f"✅ تم تسجيل القناة: {message.chat.id}")

# 📤 نشر الرسالة الساعة 11 مساءً
def post_scheduled_message():
    text = load_message()
    if not text:
        return
    channels = load_channels()
    posted = {}
    for chat_id in channels:
        try:
            msg = bot.send_message(chat_id, text)
            posted[str(chat_id)] = msg.message_id
        except Exception as e:
            print(f"❌ خطأ في النشر إلى {chat_id}: {e}")
    save_posted(posted)
    print("✅ تم النشر الساعة 11 مساءً.")

# 🗑️ حذف الرسائل الساعة 6 صباحًا
def delete_scheduled_messages():
    posted = load_posted()
    for chat_id, msg_id in posted.items():
        try:
            bot.delete_message(int(chat_id), msg_id)
        except Exception as e:
            print(f"❌ خطأ في الحذف من {chat_id}: {e}")
    save_posted({})
    print("🗑️ تم الحذف الساعة 6 صباحًا.")

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

# استدعِ الدالة قبل تشغيل البوت
keep_alive()

scheduler.start()

# 🚀 بدء البوت
print("🤖 البوت يعمل الآن...")
bot.polling(none_stop=True)

