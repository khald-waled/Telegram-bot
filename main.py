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
ADMIN_ID = int(os.getenv('ADMIN_ID'))  # 🔁 استبدله بـ Telegram ID 

# 🎯 توكن البوت
TOKEN = os.getenv('BOT_TOKEN')
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
user_states = {}

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
/addchannel – إضافة قناتك إلى قائمة الدعم  
/removechannel – إزالة قناتك من القائمة

🔐 أوامر المشرف (Admin Commands):
/show_channels – عرض جميع القنوات المسجلة  
/show_message – عرض رسالة اليوم المجدولة  
/delete_message – حذف الرسالة يدويًا

🕙 ملاحظة | Note:
⏰ يتم نشر الرسالة تلقائيًا الساعة 11:00 مساءً  
🗑 ويتم حذفها تلقائيًا الساعة 6:00 صباحًا

📢 هل تريد إضافة قناتك؟ استخدم الأمر /addchannel  
Want to add your channel? Use /addchannel

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
                result += f"🔹 [{title}](https://t.me/{username})\n"
            else:
                result += f"🔹 {title} (لا يوجد معرف)\n"
        except Exception as e:
            result += f"⚠️ لا يمكن جلب بيانات القناة: {chat_id}\n"
    bot.send_message(message.chat.id, result)

# ➕ إدخال قناة
@bot.message_handler(commands=['addchannel'])
def request_channel_add(message):
    user_states[message.from_user.id] = 'adding_channel'
    bot.reply_to(message, "🔗 أرسل الآن رابط القناة لإضافتها.")

# ➖ حذف قناة
@bot.message_handler(commands=['removechannel'])
def request_channel_delete(message):
    user_states[message.from_user.id] = 'deleting_channel'
    bot.reply_to(message, "🗑️ أرسل الآن رابط القناة أو رقمها لحذفها.")

@bot.message_handler(commands=['show_message'])
def show_scheduled_message(message):
    if message.from_user.id != ADMIN_ID:
        return
    msg = load_message()
    if msg:
        bot.reply_to(message, f"📨 الرسالة الحالية:\n\n{msg}",reply_markup=get_fixed_button())
    else:
        bot.reply_to(message, "📭 لا توجد رسالة محفوظة حالياً.")

@bot.message_handler(commands=['delete_message'])
def delete_scheduled_message(message):
    if message.from_user.id != ADMIN_ID:
        return
    if os.path.exists(MESSAGE_FILE):
        os.remove(MESSAGE_FILE)
        bot.reply_to(message, "🗑️ تم حذف الرسالة المجدولة.")
    else:
        bot.reply_to(message, "❌ لا توجد رسالة محفوظة لحذفها.")


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
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_state = user_states.get(user_id)

    # التحقق من الاشتراك الإجباري
    if not check_subscription(user_id):
        bot.send_message(chat_id, f"❌ لا يمكنك استخدام البوت حتى تشترك في القناة {REQUIRED_CHANNEL}")
        return

    # حالة إضافة قناة
    if user_state == 'adding_channel':
        try:
            chat = bot.get_chat(message.text)
            chat_id = chat.id
            # تحقق أن البوت مشرف
            member = bot.get_chat_member(chat_id, bot.get_me().id)
            if member.status not in ['administrator', 'creator']:
                bot.reply_to(message, "❌ يجب أن يكون البوت مشرفًا في القناة.")
                return
                
            channels = load_channels()
            if chat_id not in channels:
                channels.append(chat_id)
                save_channels(channels)
                bot.reply_to(message, f"✅ تم إضافة القناة: {chat.title or chat_id}")
                bot.send_message(ADMIN_ID, f"📢 تمت إضافة قناة جديدة: {chat.title or chat_id}")
            else:
                bot.reply_to(message, "⚠️ القناة موجودة بالفعل.")
        except Exception as e:
            bot.reply_to(message, "❌ فشل في إضافة القناة:\nتأكد ان الصيغة  تكون @yourChannel")
            user_states.pop(message.from_user.id, None)
        return
    
    # حالة حذف قناة
    elif user_state == 'deleting_channel':
        try:
            chat = bot.get_chat(message.text)
            target_id = chat.id
        except:
            try:
                target_id = int(message.text)
            except:
                bot.reply_to(message, "❌ صيغة غير صحيحة. أرسل رابط القناة مثل: @yourChanel أو رقمها.")
                return

        channels = load_channels()
        if target_id in channels:
            channels.remove(target_id)
            save_channels(channels)
            bot.reply_to(message, f"🗑️ تم حذف القناة: {target_id}")
        else:
            bot.reply_to(message, "⚠️ هذه القناة غير مسجلة.")
        user_states.pop(user_id, None)
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

# إذا المرسل هو الأدمن
@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID)
def handle_admin_message(message):
    save_message(message.text)
    bot.reply_to(message, "✅ تم حفظ الرسالة اليومية بنجاح.")


# 🛰️ تسجيل أي قناة أُضيف إليها البوت
@bot.channel_post_handler(func=lambda m: True)
def register_channel(message):
    channels = load_channels()
    if message.chat.id not in channels:
        channels.append(message.chat.id)
        save_channels(channels)
        bot.send_message(ADMIN_ID,f"✅ تم تسجيل القناة: {message.chat.id}")

@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID)
def handle_admin_message(message):
    state = user_states.get(message.from_user.id)

    if state == 'adding_channel':
        try:
            chat = bot.get_chat(message.text)
            chat_id = chat.id
            channels = load_channels()
            if chat_id not in channels:
                channels.append(chat_id)
                save_channels(channels)
                bot.reply_to(message, f"✅ تم إضافة القناة: {chat.title or chat_id}")
                bot.send_message(ADMIN_ID, f"📢 تمت إضافة قناة جديدة: {chat.title or chat_id}")
            else:
                bot.reply_to(message, "⚠️ القناة موجودة بالفعل.")
        except Exception as e:
            bot.reply_to(message, f"❌ فشل في إضافة القناة:\n{e}")
        user_states.pop(message.from_user.id, None)
        return

    elif state == 'deleting_channel':
        try:
            chat = bot.get_chat(message.text)
            chat_id = chat.id
        except:
            try:
                chat_id = int(message.text)
            except:
                bot.reply_to(message, "❌ صيغة غير صحيحة. أرسل رابط القناة أو رقمها.")
                return
        channels = load_channels()
        if chat_id in channels:
            channels.remove(chat_id)
            save_channels(channels)
            bot.reply_to(message, f"🗑️ تم حذف القناة: {chat_id}")
        else:
            bot.reply_to(message, "⚠️ هذه القناة غير مسجلة.")
        user_states.pop(message.from_user.id, None)
        return

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
    posted = {}
    for chat_id in channels:
        try:
            msg = bot.send_message(chat_id, text,reply_markup=get_fixed_button())
            posted[str(chat_id)] = msg.message_id
        except Exception as e:
            bot.send_message(ADMIN_ID,f"❌ خطأ في النشر إلى {chat_id}: {e}")
    save_posted(posted)
    bot.send_message(ADMIN_ID,"✅ تم النشر الساعة 11 مساءً.")

# 🗑️ حذف الرسائل الساعة 6 صباحًا
def delete_scheduled_messages():
    posted = load_posted()
    for chat_id, msg_id in posted.items():
        try:
            bot.delete_message(int(chat_id), msg_id)
        except Exception as e:
            bot.send_message(ADMIN_ID, f"❌ خطأ في الحذف من {chat_id}: {e}")
    save_posted({})
    bot.send_message(ADMIN_ID,"🗑️ تم الحذف الساعة 6 صباحًا.")

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
while True:
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        print(f"❌ خطأ: {e}")
        print("🔄 إعادة المحاولة بعد 30 ثانية...")
        time.sleep(30)





