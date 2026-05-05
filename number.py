#!/usr/bin/env python3
"""
🤖 HRM TEAMS - SMS BOT (Render Free Web Service এর জন্য)
গ্রুপ জয়েন চেক + নম্বর চেঞ্জ + OTP বট ও চ্যানেলে
"""

import os
import re
import sqlite3
import openpyxl
import threading
from datetime import datetime
from typing import Dict, Optional, List
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)

# ========== Render এর জন্য ডামি HTTP সার্ভার (পোর্ট বাইন্ডিং এর জন্য) ==========
class DummyHandler(BaseHTTPRequestHandler):
    """শুধু Render কে দেখানোর জন্য যে পোর্ট 8080 ওপেন আছে"""
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        # এমোজি বাদ দিয়ে plain text পাঠান
        html_content = """
        <html>
        <head><title>HRM TEAMS SMS BOT</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>HRM TEAMS SMS BOT</h1>
            <p>Bot is running successfully!</p>
            <p>Telegram Bot is active</p>
            <p>Status: Active</p>
        </body>
        </html>
        """
        self.wfile.write(html_content.encode('utf-8'))
    
    def do_POST(self):
        self.send_response(200)
        self.end_headers()
    
    def log_message(self, format, *args):
        pass  # লগ বন্ধ রাখুন

def start_dummy_server():
    """ডামি HTTP সার্ভার চালান (Render এর জন্য)"""
    try:
        server = HTTPServer(('0.0.0.0', 8080), DummyHandler)
        server.serve_forever()
    except Exception as e:
        print(f"Dummy server error: {e}")

# ========== বট কনফিগারেশন ==========
BOT_TOKEN = "8494156852:AAHTa5MiIm9wYE9SR0v_kRAGuPDjr9wHnkY"
ADMIN_IDS = [7693730274]

# গ্রুপ/চ্যানেল কনফিগারেশন
MAIN_CHANNEL_LINK = "https://t.me/+RoAO90AJpXs5NDU1"
OTP_CHANNEL_LINK = "https://t.me/+OAA82iQW08g3NjQ9"
MAIN_CHAT_ID = "-1002923060029"
OTP_CHAT_ID = "-1003147139412"

DB_FILE = "hrm_sms.db"

# ========== ডাটাবেস ফাংশন ==========
def get_db_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_date TEXT,
            total_otp INTEGER DEFAULT 0,
            current_number TEXT DEFAULT ''
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT UNIQUE,
            status TEXT DEFAULT 'available',
            assigned_to INTEGER DEFAULT 0,
            assigned_at TEXT,
            otp_received TEXT,
            created_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS otp_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            number TEXT,
            otp TEXT,
            received_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verifications (
            user_id INTEGER PRIMARY KEY,
            is_verified INTEGER DEFAULT 0,
            verified_at TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized")

def add_user(user_id: int, username: str, first_name: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, first_name, joined_date) VALUES (?, ?, ?, ?)',
                   (user_id, username or "", first_name or "", datetime.now().isoformat()))
    conn.commit()
    conn.close()

def update_user_number(user_id: int, number: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET current_number = ? WHERE user_id = ?', (number, user_id))
    conn.commit()
    conn.close()

def add_numbers_from_excel(file_path: str) -> int:
    """Excel ফাইল থেকে নম্বর যোগ করুন"""
    numbers = []
    try:
        wb = openpyxl.load_workbook(file_path)
        sheet = wb.active
        for row in sheet.iter_rows(values_only=True):
            for cell in row:
                if cell:
                    num = str(cell).strip()
                    num = re.sub(r'[^0-9+]', '', num)
                    if num and len(num) >= 8 and num not in numbers:
                        numbers.append(num)
    except Exception as e:
        print(f"Error reading Excel: {e}")
        return 0
    
    conn = get_db_connection()
    cursor = conn.cursor()
    added = 0
    
    print(f"Found {len(numbers)} numbers in Excel file")
    
    for num in numbers:
        try:
            cursor.execute('SELECT id FROM numbers WHERE number = ?', (num,))
            if cursor.fetchone():
                print(f"Number already exists: {num}")
                continue
            
            cursor.execute('INSERT INTO numbers (number, status, created_at) VALUES (?, ?, ?)',
                           (num, 'available', datetime.now().isoformat()))
            added += 1
            print(f"Added: {num}")
        except Exception as e:
            print(f"Failed to add {num}: {e}")
    
    conn.commit()
    
    total = cursor.execute('SELECT COUNT(*) FROM numbers').fetchone()[0]
    available = cursor.execute('SELECT COUNT(*) FROM numbers WHERE status = "available"').fetchone()[0]
    
    print(f"Total numbers in DB: {total}")
    print(f"Available numbers: {available}")
    print(f"Successfully added: {added} new numbers")
    
    conn.close()
    return added

def get_total_numbers_count() -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    count = cursor.execute('SELECT COUNT(*) FROM numbers').fetchone()[0]
    conn.close()
    return count

def get_available_numbers_count() -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    count = cursor.execute('SELECT COUNT(*) FROM numbers WHERE status = "available"').fetchone()[0]
    conn.close()
    return count

def get_all_available_numbers() -> List[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, number FROM numbers WHERE status = "available" ORDER BY id')
    rows = cursor.fetchall()
    conn.close()
    return [{'id': row[0], 'number': row[1]} for row in rows]

def get_available_number():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, number FROM numbers WHERE status = "available" ORDER BY RANDOM() LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    return {'id': row[0], 'number': row[1]} if row else None

def get_different_available_number(current_number_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, number FROM numbers WHERE status = "available" AND id != ? ORDER BY RANDOM() LIMIT 1', 
                   (current_number_id,))
    row = cursor.fetchone()
    conn.close()
    return {'id': row[0], 'number': row[1]} if row else None

def assign_number(user_id: int, number_id: int, number: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE numbers SET status = "assigned", assigned_to = ?, assigned_at = ? WHERE id = ?',
                   (user_id, datetime.now().isoformat(), number_id))
    conn.commit()
    conn.close()
    update_user_number(user_id, number)
    return True

def release_number(number_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE numbers SET status = "available", assigned_to = 0, assigned_at = NULL WHERE id = ?', (number_id,))
    conn.commit()
    conn.close()

def save_otp(user_id: int, number: str, otp: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO otp_logs (user_id, number, otp, received_at) VALUES (?, ?, ?, ?)',
                   (user_id, number, otp, datetime.now().isoformat()))
    cursor.execute('UPDATE users SET total_otp = total_otp + 1 WHERE user_id = ?', (user_id,))
    cursor.execute('UPDATE numbers SET otp_received = ?, status = "completed" WHERE number = ?', (otp, number))
    conn.commit()
    conn.close()

def check_verification(user_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_verified FROM verifications WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] == 1 if row else False

def verify_user(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO verifications (user_id, is_verified, verified_at) VALUES (?, ?, ?)',
                   (user_id, 1, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user_stats(user_id: int) -> Dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT total_otp, current_number FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    cursor.execute('SELECT COUNT(*) FROM otp_logs WHERE user_id = ?', (user_id,))
    otp_count = cursor.fetchone()[0]
    conn.close()
    return {
        'total_otp': row[0] if row else 0,
        'otp_count': otp_count,
        'current_number': row[1] if row and row[1] else "None"
    }

def get_admin_stats() -> Dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    total_users = cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    available = cursor.execute('SELECT COUNT(*) FROM numbers WHERE status = "available"').fetchone()[0]
    total_numbers = cursor.execute('SELECT COUNT(*) FROM numbers').fetchone()[0]
    total_otp = cursor.execute('SELECT COUNT(*) FROM otp_logs').fetchone()[0]
    assigned = cursor.execute('SELECT COUNT(*) FROM numbers WHERE status = "assigned"').fetchone()[0]
    completed = cursor.execute('SELECT COUNT(*) FROM numbers WHERE status = "completed"').fetchone()[0]
    conn.close()
    return {
        'total_users': total_users,
        'available_numbers': available,
        'total_numbers': total_numbers,
        'total_otp': total_otp,
        'assigned_numbers': assigned,
        'completed_numbers': completed
    }

# ========== OTP ডিটেক্টর ==========
def detect_otp_from_message(text: str) -> Optional[str]:
    if not text:
        return None
    
    patterns = [
        r'\b\d{4,8}\b',
        r'code[:\s]*(\d{4,8})',
        r'otp[:\s]*(\d{4,8})',
        r'is[:\s]*(\d{4,8})',
        r'#(\d{6,8})',
        r'Your verification code is: (\d{4,8})',
        r'verification code:? (\d{4,8})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if match.groups():
                otp = match.group(1)
            else:
                otp = match.group(0)
            
            if otp and len(otp) >= 4 and len(otp) <= 8:
                return otp
    
    return None

# ========== গ্রুপ জয়েন চেক ==========
async def check_user_joined_groups(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        main_member = await context.bot.get_chat_member(chat_id=MAIN_CHAT_ID, user_id=user_id)
        if main_member.status in ['member', 'administrator', 'creator']:
            otp_member = await context.bot.get_chat_member(chat_id=OTP_CHAT_ID, user_id=user_id)
            if otp_member.status in ['member', 'administrator', 'creator']:
                return True
    except:
        pass
    return False

# ========== কীবোর্ড ==========
def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Get a Phone Number", callback_data="get_number")],
        [InlineKeyboardButton("My Status", callback_data="my_status")],
        [InlineKeyboardButton("Change Number", callback_data="change_number")],
        [InlineKeyboardButton("Help", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_verify_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Main Channel", url=MAIN_CHANNEL_LINK)],
        [InlineKeyboardButton("OTP Channel", url=OTP_CHANNEL_LINK)],
        [InlineKeyboardButton("Check Verification", callback_data="check_verify")],
        [InlineKeyboardButton("Back", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("Upload Excel", callback_data="admin_upload")],
        [InlineKeyboardButton("Show All Numbers", callback_data="admin_show_numbers")],
        [InlineKeyboardButton("Users List", callback_data="admin_users")],
        [InlineKeyboardButton("OTP Logs", callback_data="admin_otp_logs")],
        [InlineKeyboardButton("Back", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_number_action_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Change Number", callback_data="change_number")],
        [InlineKeyboardButton("My Status", callback_data="my_status")],
        [InlineKeyboardButton("Back to Menu", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== বট হ্যান্ডলার ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    add_user(user_id, user.username, user.first_name)
    is_member = await check_user_joined_groups(user_id, context)
    
    if is_member:
        verify_user(user_id)
    
    total_numbers = get_total_numbers_count()
    available_numbers = get_available_numbers_count()
    
    welcome_text = f"""HRM TEAMS
================================
User: {user.first_name}
Numbers Available: {available_numbers}/{total_numbers}

Features:
- Temporary phone numbers
- Instant OTP detection
- 24/7 availability

================================"""

    if is_member:
        welcome_text += "\nYou are verified!"
        await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=get_main_keyboard())
    else:
        welcome_text += "\nVerification Required!\nPlease verify to use the bot."
        await update.message.reply_text(
            welcome_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Verify Now", callback_data="verify")]
            ])
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    print(f"Clicked: {data} by user {user_id}")
    
    is_member = await check_user_joined_groups(user_id, context)
    if is_member:
        verify_user(user_id)
    
    if data == "verify":
        await query.edit_message_text(
            "Verification Required\n================================\n\n"
            "Join both channels using the buttons below, then click 'Check Verification'.\n\n"
            "After verification, you can start getting numbers!",
            parse_mode='HTML',
            reply_markup=get_verify_keyboard()
        )
        return
    
    if data == "check_verify":
        if await check_user_joined_groups(user_id, context):
            verify_user(user_id)
            await query.edit_message_text(
                "Verification Successful!\n\nYou can now use the bot!",
                parse_mode='HTML',
                reply_markup=get_main_keyboard()
            )
        else:
            await query.edit_message_text(
                "Verification Failed!\n\nYou haven't joined both channels yet.",
                parse_mode='HTML',
                reply_markup=get_verify_keyboard()
            )
        return
    
    if data == "back_to_main":
        await query.edit_message_text(
            "HRM TEAMS\n================================\nWhat would you like to do?",
            parse_mode='HTML',
            reply_markup=get_main_keyboard()
        )
        return
    
    if data == "get_number":
        number_data = get_available_number()
        if number_data:
            if assign_number(user_id, number_data['id'], number_data['number']):
                context.user_data['assigned_number'] = number_data['number']
                context.user_data['number_id'] = number_data['id']
                print(f"Assigned number: {number_data['number']} to user {user_id}")
                await query.edit_message_text(
                    f"Number assigned!\n================================\nNumber: <code>{number_data['number']}</code>\n\nForward OTP message to this bot!",
                    parse_mode='HTML',
                    reply_markup=get_number_action_keyboard()
                )
        else:
            await query.edit_message_text(
                "No numbers available!\n\nPlease contact admin to upload numbers.",
                parse_mode='HTML',
                reply_markup=get_main_keyboard()
            )
        return
    
    if data == "my_status":
        stats = get_user_stats(user_id)
        await query.edit_message_text(
            f"Your Status\n================================\n"
            f"Total OTP: {stats['total_otp']}\n"
            f"Total SMS: {stats['otp_count']}\n"
            f"Current Number: <code>{stats['current_number']}</code>",
            parse_mode='HTML',
            reply_markup=get_main_keyboard()
        )
        return
    
    if data == "change_number":
        print(f"Change number requested for user {user_id}")
        
        if 'number_id' not in context.user_data:
            await query.edit_message_text(
                "You don't have any number assigned yet!\n\nClick 'Get a Phone Number' first.",
                parse_mode='HTML',
                reply_markup=get_main_keyboard()
            )
            return
        
        current_number_id = context.user_data['number_id']
        current_number = context.user_data.get('assigned_number', 'Unknown')
        print(f"   Current number: {current_number} (ID: {current_number_id})")
        
        new_number_data = get_different_available_number(current_number_id)
        
        if new_number_data:
            release_number(current_number_id)
            print(f"   Released old number ID: {current_number_id}")
            
            if assign_number(user_id, new_number_data['id'], new_number_data['number']):
                context.user_data['assigned_number'] = new_number_data['number']
                context.user_data['number_id'] = new_number_data['id']
                print(f"   Assigned new number: {new_number_data['number']}")
                await query.edit_message_text(
                    f"Number changed successfully!\n================================\n"
                    f"Old Number: <code>{current_number}</code>\n"
                    f"New Number: <code>{new_number_data['number']}</code>\n\n"
                    f"Forward OTP message to this bot!",
                    parse_mode='HTML',
                    reply_markup=get_number_action_keyboard()
                )
            else:
                await query.edit_message_text(
                    "Failed to assign new number!",
                    parse_mode='HTML',
                    reply_markup=get_main_keyboard()
                )
        else:
            total = get_total_numbers_count()
            available = get_available_numbers_count()
            await query.edit_message_text(
                f"No other numbers available for change!\n\n"
                f"Total Numbers: {total}\n"
                f"Available: {available}\n"
                f"Your Number: {current_number}\n\n"
                f"Please try again later or contact admin.",
                parse_mode='HTML',
                reply_markup=get_main_keyboard()
            )
        return
    
    if data == "help":
        help_text = """Help & Guide
================================

How to use:
1- Click "Get a Phone Number"
2- Use that number for OTP
3- Forward the OTP message to this bot
4- OTP will be detected automatically

Admin Commands:
- /admin - Open admin panel
- Upload Excel file with numbers

Support: @HRM_TEAMS
================================"""
        await query.edit_message_text(
            help_text,
            parse_mode='HTML',
            reply_markup=get_main_keyboard()
        )
        return
    
    if user_id in ADMIN_IDS:
        if data == "admin_panel":
            stats = get_admin_stats()
            panel_text = f"""Admin Panel
================================
Users: {stats['total_users']}
Available: {stats['available_numbers']}
Assigned: {stats['assigned_numbers']}
Completed: {stats['completed_numbers']}
Total Numbers: {stats['total_numbers']}
Total OTPs: {stats['total_otp']}
================================"""
            await query.edit_message_text(panel_text, parse_mode='HTML', reply_markup=get_admin_keyboard())
            return
        
        if data == "admin_stats":
            stats = get_admin_stats()
            await query.edit_message_text(
                f"Statistics\n================================\n"
                f"Users: {stats['total_users']}\n"
                f"Available: {stats['available_numbers']}\n"
                f"Assigned: {stats['assigned_numbers']}\n"
                f"Completed: {stats['completed_numbers']}\n"
                f"Total Numbers: {stats['total_numbers']}\n"
                f"Total OTPs: {stats['total_otp']}",
                parse_mode='HTML', reply_markup=get_admin_keyboard()
            )
            return
        
        if data == "admin_upload":
            await query.edit_message_text(
                "Upload Excel File\n================================\n\n"
                "Please send an Excel file (.xlsx) with phone numbers.\n\n"
                "Format:\n- One number per cell\n- Any column\n- With or without country code\n\n"
                "Example:\n+1234567890\n9876543210\n+44123456789",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="admin_panel")]])
            )
            context.user_data['awaiting_upload'] = True
            return
        
        if data == "admin_show_numbers":
            numbers = get_all_available_numbers()
            if numbers:
                text = "Available Numbers\n================================\n"
                for i, num in enumerate(numbers[:30], 1):
                    text += f"{i}. <code>{num['number']}</code>\n"
                if len(numbers) > 30:
                    text += f"\n... and {len(numbers) - 30} more"
            else:
                text = "No available numbers found."
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=get_admin_keyboard())
            return
        
        if data == "admin_users":
            conn = get_db_connection()
            cursor = conn.cursor()
            users = cursor.execute('SELECT first_name, total_otp FROM users ORDER BY total_otp DESC LIMIT 20').fetchall()
            conn.close()
            if users:
                text = "Top Users\n================================\n"
                for i, (name, otp) in enumerate(users, 1):
                    text += f"{i}. {name[:15]} - {otp} OTPs\n"
            else:
                text = "No users found."
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=get_admin_keyboard())
            return
        
        if data == "admin_otp_logs":
            conn = get_db_connection()
            cursor = conn.cursor()
            logs = cursor.execute('SELECT otp, number, received_at FROM otp_logs ORDER BY received_at DESC LIMIT 20').fetchall()
            conn.close()
            if logs:
                text = "Recent OTPs\n================================\n"
                for otp, number, received_at in logs:
                    text += f"OTP: {otp} | Number: {number[-8:]}\n"
            else:
                text = "No OTP logs found."
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=get_admin_keyboard())
            return

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    
    if user_id in ADMIN_IDS and context.user_data.get('awaiting_upload'):
        if message.document:
            file = await message.document.get_file()
            file_path = f"numbers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            await file.download_to_drive(file_path)
            added = add_numbers_from_excel(file_path)
            os.remove(file_path)
            context.user_data['awaiting_upload'] = False
            
            total = get_total_numbers_count()
            available = get_available_numbers_count()
            
            await message.reply_text(
                f"Numbers uploaded successfully!\n================================\n"
                f"Added: {added} new numbers\n"
                f"Total Numbers: {total}\n"
                f"Available: {available}\n\n"
                f"Users can now get these numbers!",
                parse_mode='HTML',
                reply_markup=get_admin_keyboard()
            )
            return
        else:
            await message.reply_text(
                "Please send an Excel file (.xlsx) with phone numbers.",
                parse_mode='HTML'
            )
            return
    
    if not await check_user_joined_groups(user_id, context):
        await message.reply_text(
            "Please verify first!\nUse /start to verify.",
            parse_mode='HTML'
        )
        return
    
    text = message.text or message.caption or ""
    otp = detect_otp_from_message(text)
    
    if otp and 'assigned_number' in context.user_data:
        number = context.user_data['assigned_number']
        
        save_otp(user_id, number, otp)
        
        await message.reply_text(
            f"OTP Detected!\n================================\nOTP: <code>{otp}</code>\nNumber: <code>{number}</code>\n\nYou can now use this OTP!",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("New Number", callback_data="get_number")],
                [InlineKeyboardButton("Status", callback_data="my_status")]
            ])
        )
        
        channel_msg = f"""New OTP!
================================
User: {update.effective_user.first_name}
Number: <code>{number}</code>
OTP: <code>{otp}</code>
Time: {datetime.now().strftime('%I:%M %p')}
================================
HRM TEAMS"""
        
        try:
            await context.bot.send_message(chat_id=OTP_CHAT_ID, text=channel_msg, parse_mode='HTML')
        except:
            pass
        
        if 'number_id' in context.user_data:
            release_number(context.user_data['number_id'])
            del context.user_data['assigned_number']
            del context.user_data['number_id']
    else:
        if not otp:
            await message.reply_text(
                "No OTP found.\n\nPlease forward the exact OTP message.",
                parse_mode='HTML'
            )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in ADMIN_IDS:
        await update.message.reply_text("Admin Panel", parse_mode='HTML', reply_markup=get_admin_keyboard())
    else:
        await update.message.reply_text("Unauthorized!")

# ========== মেইন ==========
def main():
    # ডামি HTTP সার্ভার চালান (Render Free Tier এর জন্য)
    server_thread = threading.Thread(target=start_dummy_server, daemon=True)
    server_thread.start()
    print("Dummy HTTP Server started on port 8080 (for Render)")
    
    # ডাটাবেস চেক
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print("Old database deleted. Creating new one...")
    
    init_db()
    
    print("=" * 50)
    print("HRM TEAMS Bot is running...")
    print(f"Admin ID: {ADMIN_IDS[0]}")
    print("Type /admin to open admin panel")
    print("Upload Excel file to add numbers")
    print("Numbers will be assigned randomly")
    print("=" * 50)
    
    # টেলিগ্রাম বট চালান
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    
    # Polling mode এ চালান (Webhook না)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
