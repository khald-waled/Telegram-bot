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
    CREATE TABLE IF NOT EXISTS bot_users (
        user_id BIGINT PRIMARY KEY
    );
    """)
    

    try:
        cur.execute("ALTER TABLE IF EXISTS channels ADD COLUMN IF NOT EXISTS owner_id BIGINT;")
    except:
        conn.rollback() # العمود موجود مسبقاً
    
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

def save_user(user_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("INSERT INTO bot_users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
    conn.commit()
    cur.close()
    conn.close()

def get_all_users():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM bot_users")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def save_users_bulk(user_ids):
    """حفظ عدة مستخدمين دفعة واحدة (أكثر كفاءة)"""
    if not user_ids:
        return 0
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # تحضير البيانات للINSERT
    data = [(user_id,) for user_id in user_ids]
    
    # إدراج متعدد مع تجاهل التكرار
    execute_values(
        cur,
        "INSERT INTO bot_users (user_id) VALUES %s ON CONFLICT DO NOTHING",
        data
    )
    
    conn.commit()
    cur.close()
    conn.close()
    
    return len(user_ids)

def user_exists(user_id):
    """التحقق من وجود مستخدم"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT EXISTS(SELECT 1 FROM bot_users WHERE user_id = %s)", (user_id,))
    exists = cur.fetchone()[0]
    cur.close()
    conn.close()
    return exists

def get_users_count():
    """الحصول على عدد المستخدمين"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM bot_users")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count

def remove_user(user_id):
    """حذف مستخدم"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM bot_users WHERE user_id = %s", (user_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    return deleted

def get_detailed_stats():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # 1. إجمالي عدد المستخدمين
    cur.execute("SELECT COUNT(*) FROM bot_users")
    total_users = cur.fetchone()[0]
    
    # 2. عدد المستخدمين الذين لديهم قناة واحدة على الأقل
    # نستخدم DISTINCT للتأكد من عدم تكرار المستخدم إذا كان يملك أكثر من قناة
    cur.execute("SELECT COUNT(DISTINCT owner_id) FROM channels")
    users_with_channels = cur.fetchone()[0]
    
    # 3. إجمالي عدد القنوات المضافة في البوت
    cur.execute("SELECT COUNT(*) FROM channels")
    total_channels = cur.fetchone()[0]
    
    # 4. حساب المستخدمين الذين ليس لديهم قنوات
    users_without_channels = total_users - users_with_channels
    
    cur.close()
    conn.close()
    
    return {
        "total_users": total_users,
        "with_channels": users_with_channels,
        "without_channels": users_without_channels,
        "total_channels": total_channels
    }

def check_subscription(user_id):
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ['member', 'creator', 'administrator']:
            return True
        return False
    except Exception as e:
        print(f"Error checking subscription: {e}")
        return False


def load_owners():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT owner_id FROM channels")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

# 📥 تحميل/حفظ القنوات
# 📥 دوال للتعامل مع القنوات
def load_channels():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id FROM channels")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def save_channel_old(chat_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("INSERT INTO channels (id) VALUES (%s) ON CONFLICT DO NOTHING", (chat_id,))
    conn.commit()
    cur.close()
    conn.close()

def save_channel(chat_id, owner_id=None):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    # حفظ القناة مع معرف المالك
    cur.execute("""
    INSERT INTO channels (id, owner_id) 
    VALUES (%s, %s) 
    ON CONFLICT (id) DO UPDATE SET owner_id = EXCLUDED.owner_id
    """, (chat_id, owner_id))
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

def escape_markdown(text):
    """
    تهريب الرموز الخاصة في Markdown لبرقية
    """
    # قائمة الرموز الخاصة في Markdown لبرقية
    special_chars = [
        '_', '*', '[', ']', '(', ')', '~', '`',
        '>', '#', '+', '-', '=', '|', '{', '}',
        '.', '!'
    ]
    
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

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

# 🔍 عرض القنوات مع الصلاحيات (قنوات فقط)
@bot.message_handler(commands=['show_channel'])
def show_channels(message):
    # يعمل فقط في الخاص + للأدمن
    if message.chat.type != "private":
        return
    if message.from_user.id != ADMIN_ID:
        return

    channels = load_channels()
    if not channels:
        bot.send_message(message.chat.id, "🚫 لا توجد قنوات مسجلة.")
        return

    me = bot.get_me()
    result = "📋 <b>القنوات المسجلة:</b>\n\n"

    for chat_id in channels:
        try:
            chat = bot.get_chat(chat_id)
            title = chat.title or "بدون اسم"
            username = chat.username

            # جلب صلاحيات البوت
            try:
                member = bot.get_chat_member(chat.id, me.id)
            except:
                member = None

            # معلومات القناة
            if username:
                result += f"🔹 <b>{title}</b>\n🔗 https://t.me/{username}\n🆔 <code>{chat.id}</code>\n"
            else:
                result += f"🔹 <b>{title}</b>\n🆔 <code>{chat.id}</code>\n"

            # الصلاحيات (الموجودة فعليًا في القنوات)
            if member and member.status in ("administrator", "creator"):
                def fmt(v): return "✅" if v else "❌"
                result += (
                    "── <b>الصلاحيات</b> ──\n"
                    f"• حذف الرسائل: {fmt(getattr(member, 'can_delete_messages', False))}\n"
                    f"• تثبيت الرسائل: {fmt(getattr(member, 'can_pin_messages', False))}\n"
                    f"• تغيير المعلومات: {fmt(getattr(member, 'can_change_info', False))}\n"
                    f"• دعوة مستخدمين: {fmt(getattr(member, 'can_invite_users', False))}\n"
                    f"• إدارة البث المباشر: {fmt(getattr(member, 'can_manage_video_chats', False))}\n\n"
                )
            else:
                result += "⚠️ <i>البوت ليس مشرفًا في هذه القناة</i>\n\n"

        except Exception:
            result += f"⚠️ تعذر جلب بيانات القناة\n🆔 <code>{chat_id}</code>\n\n"

    # تقسيم الرسالة الطويلة
    MAX_LEN = 3800
    for i in range(0, len(result), MAX_LEN):
        bot.send_message(
            message.chat.id,
            result[i:i + MAX_LEN],
            parse_mode="HTML",
            disable_web_page_preview=True
        )

# 🔍 عرض القنوات مع الصلاحيات
@bot.message_handler(commands=['show_channels'])
def show_channel(message):
    if message.from_user.id != ADMIN_ID:
        return

    channels = load_channels()
    if not channels:
        bot.reply_to(message, "🚫 لا توجد قنوات مسجلة.")
        return

    result = "📋 القنوات المسجلة:\n\n"
    me = bot.get_me()

    for chat_id in channels:
        try:
            chat = bot.get_chat(chat_id)
            title = escape_markdown(chat.title or "بدون اسم")
            username = chat.username

            # محاولة جلب صلاحيات البوت في القناة
            try:
                member = bot.get_chat_member(chat.id, me.id)
            except:
                member = None

            if username:
                result += f"🔹 [{title}](https://t.me/{username})\n🆔 {chat.id}\n"
            else:
                result += f"🔹 {title}\n🆔 {chat.id}\n"

            if member and member.status in ["administrator", "creator"]:
                def fmt(val): return "✅" if val else "❌"
                result += (
                    "   ── الصلاحيات ──\n"
                    f"   • نشر الرسائل: {fmt(getattr(member, 'can_post_messages', False))}\n"
                    f"   • تعديل الرسائل: {fmt(getattr(member, 'can_edit_messages', False))}\n"
                    f"   • حذف الرسائل: {fmt(getattr(member, 'can_delete_messages', False))}\n"
                    f"   • تثبيت الرسائل: {fmt(getattr(member, 'can_pin_messages', False))}\n"
                    f"   • تغيير المعلومات: {fmt(getattr(member, 'can_change_info', False))}\n"
                    f"   • إنشاء روابط دعوة: {fmt(getattr(member, 'can_invite_users', False))}\n"
                    f"   • إدارة البث المباشر: {fmt(getattr(member, 'can_manage_video_chats', False))}\n\n"
                )
            else:
                result += "   ⚠️ البوت ليس مشرفًا في هذه القناة\n\n"

        except Exception as e:
            result += f"⚠️ لا يمكن جلب بيانات القناة: {chat_id}\n\n"

    # تقسيم الرسالة الطويلة وإرسالها
    MAX_LEN = 4000
    for i in range(0, len(result), MAX_LEN):
        bot.send_message(message.chat.id, result[i:i+MAX_LEN], parse_mode="Markdown")


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


# ➕ إضافة قنوات (يدعم id أو @username أو رابط)
@bot.message_handler(commands=['addchannel'])
def add_channel(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ غير مسموح.")
        return
    
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(
                message,
                "⚠️ استخدم الأمر هكذا:\n"
                "`/addchannel 123456 -1001234567 @username https://t.me/username ...`",
                parse_mode="Markdown"
            )
            return
        
        raw_inputs = parts[1].split()
        added, already, failed = [], [], []
        channels = load_channels()
        
        for raw in raw_inputs:
            chat_id = normalize_chat_id(raw.strip())
            if not chat_id:
                failed.append(raw)
                continue
            
            if chat_id in channels:
                already.append(str(chat_id))
            else:
                try:
                    save_channel(chat_id)
                    chat = bot.get_chat(chat_id)
                    added.append(f"{chat.title} (`{chat_id}`)")
                except:
                    failed.append(str(chat_id))
        
        response = "📋 نتيجة الإضافة:\n"
        if added:
            response += "\n✅ تمت إضافة:\n" + "\n".join(added)
        if already:
            response += "\nℹ️ موجودة مسبقًا:\n" + "\n".join(already)
        if failed:
            response += "\n❌ فشل في التعرف/الإضافة:\n" + "\n".join(failed)
        
        bot.reply_to(message, response, parse_mode="Markdown")
    
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

# 🛰️ إرسال لآيديات أو معرفات متعددة
@bot.message_handler(commands=['sendto'])
def sendto(message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        # إزالة الأمر نفسه "/sendto "
        text = message.text[len("/sendto "):].strip()

        if not text:
            bot.reply_to(message, "⚠️ استخدم الصيغة:\n/sendto 1111,2222 @user1 3333\nالرسالة هنا")
            return

        # فصل بين المعرفات (أول سطر أو أول كلمة حتى السطر الجديد)
        if "\n" in text:
            ids_part, msg_part = text.split("\n", 1)
        else:
            bot.reply_to(message, "⚠️ ضع الآيديات أولاً ثم انتقل سطر جديد للرسالة.")
            return

        # تجهيز قائمة المعرفات
        raw_ids = ids_part.replace(",", " ").split()
        targets = [x.strip() for x in raw_ids if x.strip()]

        # تجهيز الرسالة
        msg_text = msg_part.strip()
        if not msg_text:
            bot.reply_to(message, "⚠️ الرسالة فارغة.")
            return

        success = []
        failed = []

        for t in targets:
            try:
                # إذا كان يوزر (يبدأ بـ @) نستخدمه مباشرة
                if t.startswith("@"):
                    bot.send_message(t, msg_text, parse_mode="HTML")
                else:
                    chat_id = int(t)
                    # تيليجرام أحيانًا يتطلب -100 للمجموعات والقنوات
                    if not str(chat_id).startswith("-"):
                        try:
                            # نجرب مباشرة
                            bot.send_message(chat_id, msg_text, parse_mode="HTML")
                        except:
                            # لو فشل نحاول مع -100
                            bot.send_message(f"-{chat_id}", msg_text, parse_mode="HTML")
                    else:
                        bot.send_message(chat_id, msg_text, parse_mode="HTML")

                success.append(t)

            except Exception as e:
                failed.append((t, str(e)[:80]))  # نأخذ 80 حرف فقط من الخطأ

        # 🔔 تقرير الإرسال
        report = f"📤 تقرير الإرسال:\n\n✅ نجح الإرسال لـ {len(success)}\n❌ فشل الإرسال لـ {len(failed)}\n\n"
        if success:
            report += "✔️ الناجح:\n" + ", ".join(success) + "\n\n"
        if failed:
            report += "⚠️ الفاشل:\n" + "\n".join([f"{t} → {reason}" for t, reason in failed])

        bot.send_message(message.chat.id, report)

    except Exception as e:
        bot.reply_to(message, f"❌ خطأ أثناء التنفيذ:\n{e}")

@bot.message_handler(commands=['add_user'])
def broadcast_to_users(message):
    if message.from_user.id != ADMIN_ID:
        return

    # استخراج النص بعد الأمر /broadcast
    msg_text = message.text.replace("/add_user", "").strip()
    save_user(message.from_user.id)
    bot.send_message()

@bot.message_handler(commands=['broadcast'])
def broadcast_to_users(message):
    if message.from_user.id != ADMIN_ID:
        return

    # استخراج النص بعد الأمر /broadcast
    msg_text = message.text.replace("/broadcast", "").strip()
    
    if not msg_text:
        bot.reply_to(message, "⚠️ يرجى كتابة الرسالة بعد الأمر. مثال:\n`/broadcast السلام عليكم`", parse_mode="Markdown")
        return

    users = get_all_users()
    count = 0
    send_message = bot.send_message(ADMIN_ID, f"🔄 جاري إرسال الرسالة إلى {len(users)} مستخدم...")

    for user_id in users:
        try:
            bot.send_message(user_id, msg_text)
            count += 1
            time.sleep(0.1)  # لتجنب حظر التليجرام (Flood)
        except Exception:
            pass # ربما قام المستخدم بحظر البوت

    bot.send_message(ADMIN_ID, f"✅ تمت الإذاعة بنجاح لـ {count} مستخدم.")
    bot.delete_message(ADMIN_ID, send_message.message_id)


@bot.message_handler(commands=['stats', 'users'])
def admin_dashboard(message):
    # التأكد من أن المرسل هو الأدمن
    if message.from_user.id != ADMIN_ID:
        return

    stats = get_detailed_stats()
    
    # حساب النسب المئوية (لمسة إضافية مفيدة للمدير)
    if stats['total_users'] > 0:
        active_ratio = (stats['with_channels'] / stats['total_users']) * 100
    else:
        active_ratio = 0

    response = (
        "📊 **لوحة تحكم الإحصائيات الشاملة**\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"👤 **المستخدمين:**\n"
        f"├ الإجمالي: `{stats['total_users']}` مستخدم\n"
        f"├ لديهم قنوات: `{stats['with_channels']}` ✅\n"
        f"└ ليس لديهم قنوات: `{stats['without_channels']}` ❌\n\n"
        
        f"📢 **القنوات:**\n"
        f"└ إجمالي القنوات المضافة: `{stats['total_channels']}` قناة\n\n"
        
        f"📈 **تحليل النشاط:**\n"
        f"└ نسبة التفاعل: `{active_ratio:.1f}%` من المستخدمين أضافوا قنواتهم.\n"
        "━━━━━━━━━━━━━━━\n"
        "💡 *نصيحة: استخدم /broadcast لإرسال تنبيه للمستخدمين الذين لم يضيفوا قنواتهم بعد.*"
    )

    bot.reply_to(message, response, parse_mode="Markdown")

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

def register_channel_with_owner(update):
    chat = update.chat
    new_member = update.new_chat_member
    
    # معرف الشخص الذي قام بإضافة البوت أو ترقيته
    from_user_id = update.from_user.id 

    try:
        if new_member.status in ["administrator", "creator"]:
            # حفظ القناة وربطها بالمستخدم الذي قام بالترقية
            save_channel(chat.id, from_user_id)

            # تنسيق رسالة للأدمن لإبلاغه من صاحب القناة
            bot.send_message(ADMIN_ID, f"✅ قناة جديدة مسجلة:\n"
                                       f"📛 الاسم: {chat.title}\n"
                                       f"🆔 ID: {chat.id}\n"
                                       f"👤 بواسطة: {update.from_user.first_name} ({from_user_id})")
    except Exception as e:
        print(f"Error in register_channel: {e}")


# 🛰️ تسجيل أي قناة أُضيف إليها البوت فقط لو كان مشرف
@bot.my_chat_member_handler()
def register_channel(update):
    chat = update.chat
    new_member = update.new_chat_member
    new_status = new_member.status

    try:
        if new_status in ["administrator", "creator"]:
            channels = load_channels()
            if chat.id not in channels:
                register_channel_with_owner(chat.id)

                # 🔗 الرابط
                if chat.username:
                    invite_link = f"https://t.me/{chat.username}"
                else:
                    try:
                        invite_link = bot.create_chat_invite_link(chat.id).invite_link
                    except:
                        invite_link = "🔒 لا يمكن جلب الرابط (قناة خاصة أو صلاحيات ناقصة)"

                # ✅ / ❌ تنسيق
                def fmt(val): return "✅" if val else "❌"

                rights_text = f"""
✅ تم تسجيل القناة:
📛 الاسم: {chat.title}
🆔 ID: {chat.id}
🔗 الرابط: {invite_link}

🔹 الصلاحيات:
- نشر الرسائل: {fmt(getattr(new_member, 'can_post_messages', False))}
- تعديل الرسائل: {fmt(getattr(new_member, 'can_edit_messages', False))}
- حذف الرسائل: {fmt(getattr(new_member, 'can_delete_messages', False))}
- تثبيت الرسائل: {fmt(getattr(new_member, 'can_pin_messages', False))}
- تغيير المعلومات: {fmt(getattr(new_member, 'can_change_info', False))}
- إدارة القناة: {fmt(getattr(new_member, 'can_manage_chat', False))}
- إنشاء روابط دعوة: {fmt(getattr(new_member, 'can_invite_users', False))}
- إدارة البث المباشر: {fmt(getattr(new_member, 'can_manage_video_chats', False))}
"""

                bot.send_message(ADMIN_ID, rights_text)

        else:
            # لو تم تنزيل البوت من مشرف لعضو
            bot.send_message(
                ADMIN_ID,
                f"⚠️ البوت لم يعد مشرف في القناة:\n📛 {chat.title}\n🆔 {chat.id}"
            )

    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ خطأ أثناء تسجيل القناة: {chat.title}\n{e}")

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

@bot.message_handler(commands=['my_channels'])
def show_my_channels(message):
    user_id = message.from_user.id
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id FROM channels WHERE owner_id = %s", (user_id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        bot.reply_to(message, "🚫 لم تقم بتسجيل أي قنوات باسمك بعد.")
        return

    res = "📋 قنواتك المسجلة في الدعم:\n\n"
    for r in rows:
        try:
            chat = bot.get_chat(r[0])
            res += f"🔹 {chat.title} (`{r[0]}`)\n"
        except:
            res += f"🔹 قناة غير معروفة (`{r[0]}`)\n"
    
    bot.reply_to(message, res, parse_mode="Markdown")


# 📝 استقبال رسائل المستخدمين اليومية
@bot.message_handler(func=lambda message: message.from_user.id != ADMIN_ID and message.chat.type == "private")
def handle_message(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    save_user(user_id)

    # التحقق من الاشتراك الإجباري
    if not check_subscription(user_id):
        bot.send_message(chat_id, f"❌ لا يمكنك استخدام البوت حتى تشترك في القناة {REQUIRED_CHANNEL}")
        return

    # أي رسالة أخرى من المستخدم
    bot.reply_to(
        message,
        "📡  تم الارسال الى المسؤل على القائمة\n"
        "إذا تأخر الرد راسل المسؤل : @RohThoryaBot"
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























