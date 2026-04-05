import telebot
import os
import zipfile
import subprocess
import shutil
import time
import threading
import signal
import sys
import json
import sqlite3
import hashlib
import re
import schedule
import psutil
import requests
import random
import string
import logging
import tempfile
import mimetypes
from datetime import datetime, timedelta
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from collections import defaultdict
from pathlib import Path

BOT_TOKEN = "8759695144:AAGfZ3DKgvK3HLrQ5v5uWDLv0bsAqpoKN4Q"

# Admin Configuration
ADMIN_ID = 8446135201

bot = telebot.TeleBot(BOT_TOKEN)

BASE_DIR = "projects"
os.makedirs(BASE_DIR, exist_ok=True)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database Setup
DB_PATH = "hosting_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        join_date TEXT,
        last_active TEXT,
        total_uploads INTEGER DEFAULT 0,
        total_starts INTEGER DEFAULT 0,
        total_stops INTEGER DEFAULT 0,
        total_restarts INTEGER DEFAULT 0,
        total_deletes INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0,
        warning_count INTEGER DEFAULT 0,
        referral_code TEXT,
        referred_by INTEGER,
        language TEXT DEFAULT 'en',
        theme TEXT DEFAULT 'dark'
    )''')
    
    # Projects table
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        project_name TEXT,
        created_at TEXT,
        last_started TEXT,
        last_stopped TEXT,
        total_runs INTEGER DEFAULT 0,
        total_uptime INTEGER DEFAULT 0,
        size_mb REAL,
        auto_restart INTEGER DEFAULT 0,
        webhook_url TEXT,
        is_backed_up INTEGER DEFAULT 0,
        last_backup TEXT,
        description TEXT,
        version TEXT,
        git_repo TEXT,
        port INTEGER DEFAULT 5000,
        python_version TEXT DEFAULT '3.9',
        startup_command TEXT DEFAULT 'python main.py',
        is_docker INTEGER DEFAULT 0
    )''')
    
    # Activity logs table
    c.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        project_name TEXT,
        timestamp TEXT,
        details TEXT
    )''')
    
    # Scheduled tasks table
    c.execute('''CREATE TABLE IF NOT EXISTS scheduled_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        project_name TEXT,
        action TEXT,
        schedule_time TEXT,
        recurring INTEGER DEFAULT 0,
        recurring_interval TEXT,
        active INTEGER DEFAULT 1,
        last_run TEXT
    )''')
    
    # Backup records table
    c.execute('''CREATE TABLE IF NOT EXISTS backups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        project_name TEXT,
        backup_path TEXT,
        backup_size REAL,
        created_at TEXT
    )''')
    
    # Notifications table
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        message TEXT,
        created_at TEXT,
        read INTEGER DEFAULT 0,
        type TEXT DEFAULT 'info'
    )''')
    
    # Support tickets table
    c.execute('''CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        subject TEXT,
        message TEXT,
        status TEXT DEFAULT 'open',
        created_at TEXT,
        admin_response TEXT,
        responded_at TEXT,
        priority TEXT DEFAULT 'normal'
    )''')
    
    # Resource usage history
    c.execute('''CREATE TABLE IF NOT EXISTS resource_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        project_name TEXT,
        cpu_percent REAL,
        ram_mb REAL,
        disk_io REAL,
        network_io REAL,
        timestamp TEXT
    )''')
    
    # Project dependencies table
    c.execute('''CREATE TABLE IF NOT EXISTS project_dependencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        project_name TEXT,
        dependency_name TEXT,
        version TEXT,
        installed_at TEXT
    )''')
    
    # User settings table
    c.execute('''CREATE TABLE IF NOT EXISTS user_settings (
        user_id INTEGER PRIMARY KEY,
        auto_delete_logs INTEGER DEFAULT 7,
        max_projects INTEGER DEFAULT 15,
        backup_enabled INTEGER DEFAULT 1,
        notification_enabled INTEGER DEFAULT 1,
        log_level TEXT DEFAULT 'info'
    )''')
    
    # Port mappings table
    c.execute('''CREATE TABLE IF NOT EXISTS port_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        project_name TEXT,
        port INTEGER,
        external_port INTEGER,
        created_at TEXT
    )''')
    
    # Domain mappings table
    c.execute('''CREATE TABLE IF NOT EXISTS domain_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        project_name TEXT,
        domain TEXT,
        created_at TEXT
    )''')
    
    # Webhook logs table
    c.execute('''CREATE TABLE IF NOT EXISTS webhook_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        project_name TEXT,
        webhook_url TEXT,
        event TEXT,
        response_code INTEGER,
        created_at TEXT
    )''')
    
    # Project templates table
    c.execute('''CREATE TABLE IF NOT EXISTS project_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        description TEXT,
        template_path TEXT,
        created_at TEXT
    )''')
    
    # Analytics events table
    c.execute('''CREATE TABLE IF NOT EXISTS analytics_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        event_type TEXT,
        event_data TEXT,
        timestamp TEXT
    )''')
    
    conn.commit()
    conn.close()

init_db()

# Store running processes per user
running_projects = {}
project_errors = {}
project_stats = {}
user_cooldowns = {}
user_warnings = {}
user_sessions = {}

# Admin statistics
admin_stats = {
    "total_users": 0,
    "total_projects": 0,
    "total_running": 0,
    "bot_start_time": datetime.now(),
    "total_api_calls": 0,
    "total_backups": 0,
    "total_restores": 0
}

# System limits
MAX_PROJECTS_PER_USER = 20
MAX_FILE_SIZE_MB = 100
UPLOAD_COOLDOWN_SECONDS = 30
START_COOLDOWN_SECONDS = 10

# Available ports for projects (internal)
AVAILABLE_PORTS = list(range(10000, 10100))

# Project templates
PROJECT_TEMPLATES = {
    "flask": {
        "description": "Flask web application template",
        "files": {
            "main.py": '''from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return 'Hello from Flask!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)''',
            "requirements.txt": "flask==2.3.0"
        }
    },
    "discord_bot": {
        "description": "Discord bot template",
        "files": {
            "main.py": '''import discord
from discord.ext import commands

bot = commands.Bot(command_prefix='!')

@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user}')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

if __name__ == '__main__':
    bot.run('YOUR_BOT_TOKEN')''',
            "requirements.txt": "discord.py==2.3.0"
        }
    },
    "telegram_bot": {
        "description": "Telegram bot template",
        "files": {
            "main.py": '''import telebot

bot = telebot.TeleBot('YOUR_BOT_TOKEN')

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, 'Hello! I am a bot.')

@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.reply_to(message, message.text)

if __name__ == '__main__':
    bot.infinity_polling()''',
            "requirements.txt": "pyTelegramBotAPI==4.12.0"
        }
    },
    "fastapi": {
        "description": "FastAPI web application template",
        "files": {
            "main.py": '''from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get('/')
def home():
    return {'message': 'Hello from FastAPI!'}

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)''',
            "requirements.txt": "fastapi==0.100.0\nuvicorn==0.23.0"
        }
    }
}

# ============== CORE FUNCTIONS ==============

def get_user_dir(user_id):
    user_dir = os.path.join(BASE_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def get_user_projects(user_id):
    user_dir = get_user_dir(user_id)
    projects = []
    for item in os.listdir(user_dir):
        item_path = os.path.join(user_dir, item)
        if os.path.isdir(item_path):
            projects.append(item)
    return projects

def get_user_running_projects(user_id):
    if user_id not in running_projects:
        running_projects[user_id] = {}
    return running_projects[user_id]

def get_user_errors(user_id):
    if user_id not in project_errors:
        project_errors[user_id] = {}
    return project_errors[user_id]

def log_activity(user_id, action, project_name="", details=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''INSERT INTO activity_logs (user_id, action, project_name, timestamp, details)
                    VALUES (?, ?, ?, ?, ?)''',
                 (user_id, action, project_name, datetime.now().isoformat(), details))
    conn.commit()
    conn.close()

def send_notification(user_id, message, notif_type="info"):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''INSERT INTO notifications (user_id, message, created_at, read, type)
                    VALUES (?, ?, ?, 0, ?)''',
                 (user_id, message, datetime.now().isoformat(), notif_type))
    conn.commit()
    conn.close()
    
    try:
        icon = "🔔" if notif_type == "info" else "⚠️" if notif_type == "warning" else "✅"
        bot.send_message(user_id, f"{icon} *NOTIFICATION*\n\n{message}", parse_mode="Markdown")
    except:
        pass

def get_folder_size(folder_path):
    total = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total += os.path.getsize(fp)
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if total < 1024.0:
            return f"{total:.1f} {unit}"
        total /= 1024.0
    return f"{total:.1f} TB"

# ============== FEATURE 1: PROJECT TEMPLATES ==============

def create_project_from_template(user_id, project_name, template_name):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    
    if os.path.exists(project_path):
        return False, "Project already exists"
    
    template = PROJECT_TEMPLATES.get(template_name)
    if not template:
        return False, "Template not found"
    
    os.makedirs(project_path)
    
    for filename, content in template["files"].items():
        file_path = os.path.join(project_path, filename)
        with open(file_path, 'w') as f:
            f.write(content)
    
    size_mb = get_folder_size(project_path)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO projects (user_id, project_name, created_at, size_mb, description) VALUES (?, ?, ?, ?, ?)",
                 (user_id, project_name, datetime.now().isoformat(), size_mb, template["description"]))
    conn.commit()
    conn.close()
    
    log_activity(user_id, "template_created", project_name, f"Template: {template_name}")
    return True, f"Project '{project_name}' created from {template_name} template"

# ============== FEATURE 2: DEPENDENCY MANAGEMENT ==============

def install_dependencies(user_id, project_name):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    req_file = os.path.join(project_path, "requirements.txt")
    
    if not os.path.exists(req_file):
        return False, "No requirements.txt found"
    
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_file], 
                              cwd=project_path, capture_output=True, text=True, timeout=120)
        
        conn = sqlite3.connect(DB_PATH)
        for line in result.stdout.split('\n'):
            if 'Successfully installed' in line:
                packages = line.replace('Successfully installed', '').strip().split()
                for pkg in packages:
                    if '==' in pkg:
                        name, version = pkg.split('==')
                        conn.execute("INSERT INTO project_dependencies (user_id, project_name, dependency_name, version, installed_at) VALUES (?, ?, ?, ?, ?)",
                                     (user_id, project_name, name, version, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        log_activity(user_id, "dependencies_installed", project_name, f"Exit code: {result.returncode}")
        return result.returncode == 0, result.stdout[:500] if result.returncode == 0 else result.stderr[:500]
    except subprocess.TimeoutExpired:
        return False, "Installation timeout"

def list_dependencies(user_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT dependency_name, version, installed_at FROM project_dependencies WHERE user_id = ? AND project_name = ? ORDER BY installed_at DESC",
                     (user_id, project_name))
    deps = c.fetchall()
    conn.close()
    return deps

# ============== FEATURE 3: PROJECT LOGS VIEWER ==============

def get_project_logs(user_id, project_name, lines=50):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    log_file = os.path.join(project_path, "project.log")
    
    if not os.path.exists(log_file):
        return None, "No logs found"
    
    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return True, ''.join(last_lines)
    except Exception as e:
        return False, str(e)

def clear_project_logs(user_id, project_name):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    log_file = os.path.join(project_path, "project.log")
    
    if os.path.exists(log_file):
        with open(log_file, 'w') as f:
            f.write(f"[LOGS CLEARED] at {datetime.now()}\n")
        return True
    return False

# ============== FEATURE 4: PROJECT DESCRIPTION & NOTES ==============

def set_project_description(user_id, project_name, description):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE projects SET description = ? WHERE user_id = ? AND project_name = ?",
                 (description, user_id, project_name))
    conn.commit()
    conn.close()
    log_activity(user_id, "description_set", project_name, description[:50])
    return True

def get_project_description(user_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT description FROM projects WHERE user_id = ? AND project_name = ?",
                     (user_id, project_name))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# ============== FEATURE 5: PROJECT STATISTICS ==============

def get_project_stats(user_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT total_runs, last_started, last_stopped, created_at, size_mb, version FROM projects WHERE user_id = ? AND project_name = ?",
                     (user_id, project_name))
    stats = c.fetchone()
    conn.close()
    
    if stats:
        return {
            "total_runs": stats[0],
            "last_started": stats[1],
            "last_stopped": stats[2],
            "created_at": stats[3],
            "size_mb": stats[4],
            "version": stats[5]
        }
    return None

# ============== FEATURE 6: BATCH OPERATIONS ==============

def batch_start_projects(user_id, project_list):
    results = []
    for project in project_list:
        if start_project(user_id, project):
            results.append(f"✅ {project}")
        else:
            results.append(f"❌ {project}")
        time.sleep(1)
    return results

def batch_stop_projects(user_id, project_list):
    results = []
    for project in project_list:
        if project in get_user_running_projects(user_id):
            stop_project(user_id, project)
            results.append(f"✅ {project}")
        else:
            results.append(f"⚠️ {project} (not running)")
    return results

def batch_delete_projects(user_id, project_list):
    results = []
    for project in project_list:
        delete_project(user_id, project)
        results.append(f"🗑️ {project}")
    return results

# ============== FEATURE 7: PROJECT CLONING ==============

def clone_project(user_id, source_project, new_project_name):
    user_dir = get_user_dir(user_id)
    source_path = os.path.join(user_dir, source_project)
    dest_path = os.path.join(user_dir, new_project_name)
    
    if not os.path.exists(source_path):
        return False, "Source project not found"
    
    if os.path.exists(dest_path):
        return False, "Destination project already exists"
    
    shutil.copytree(source_path, dest_path)
    
    size_mb = get_folder_size(dest_path)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO projects (user_id, project_name, created_at, size_mb) VALUES (?, ?, ?, ?)",
                 (user_id, new_project_name, datetime.now().isoformat(), size_mb))
    conn.commit()
    conn.close()
    
    log_activity(user_id, "project_cloned", source_project, f"Cloned to {new_project_name}")
    return True, f"Cloned successfully to '{new_project_name}'"

# ============== FEATURE 8: ACTIVITY LOGS VIEWER ==============

def get_user_activity_logs(user_id, limit=50):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT action, project_name, timestamp, details FROM activity_logs WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                     (user_id, limit))
    logs = c.fetchall()
    conn.close()
    return logs

# ============== FEATURE 9: NOTIFICATION SYSTEM ==============

def get_unread_notifications(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT id, message, created_at, type FROM notifications WHERE user_id = ? AND read = 0 ORDER BY created_at DESC",
                     (user_id,))
    notifs = c.fetchall()
    conn.close()
    return notifs

def mark_notification_read(notif_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notif_id,))
    conn.commit()
    conn.close()

def mark_all_notifications_read(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE notifications SET read = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# ============== FEATURE 10: SUPPORT TICKET SYSTEM ==============

def create_support_ticket(user_id, subject, message, priority="normal"):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''INSERT INTO support_tickets (user_id, subject, message, created_at, status, priority)
                    VALUES (?, ?, ?, ?, 'open', ?)''',
                 (user_id, subject, message, datetime.now().isoformat(), priority))
    conn.commit()
    ticket_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    
    # Notify admin
    priority_icon = "🔴" if priority == "high" else "🟡" if priority == "medium" else "🔵"
    bot.send_message(ADMIN_ID, f"{priority_icon} *NEW SUPPORT TICKET #{ticket_id}*\n\nUser: `{user_id}`\nPriority: {priority}\nSubject: {subject}\n\nMessage: {message[:200]}...", 
                     parse_mode="Markdown")
    
    log_activity(user_id, "ticket_created", "", f"Ticket #{ticket_id}: {subject}")
    return ticket_id

def get_user_tickets(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT id, subject, status, created_at, priority FROM support_tickets WHERE user_id = ? ORDER BY created_at DESC",
                     (user_id,))
    tickets = c.fetchall()
    conn.close()
    return tickets

# ============== FEATURE 11: AUTO-RESTART ON CRASH ==============

def set_auto_restart(user_id, project_name, enabled):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE projects SET auto_restart = ? WHERE user_id = ? AND project_name = ?", 
                 (1 if enabled else 0, user_id, project_name))
    conn.commit()
    conn.close()
    log_activity(user_id, "auto_restart", project_name, f"Enabled: {enabled}")
    return True

def get_auto_restart_status(user_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT auto_restart FROM projects WHERE user_id = ? AND project_name = ?", 
                     (user_id, project_name))
    result = c.fetchone()
    conn.close()
    return result[0] == 1 if result else False

# ============== FEATURE 12: SCHEDULED TASKS ==============

def schedule_task(user_id, project_name, action, schedule_time, recurring=False, interval=None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''INSERT INTO scheduled_tasks 
                     (user_id, project_name, action, schedule_time, recurring, recurring_interval)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                 (user_id, project_name, action, schedule_time, recurring, interval))
    conn.commit()
    conn.close()
    log_activity(user_id, "scheduled_task", project_name, f"Action: {action} at {schedule_time}")
    return True

def get_user_scheduled_tasks(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT id, project_name, action, schedule_time, recurring FROM scheduled_tasks WHERE user_id = ? AND active = 1", 
                     (user_id,))
    tasks = c.fetchall()
    conn.close()
    return tasks

def delete_scheduled_task(task_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE scheduled_tasks SET active = 0 WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return True

# ============== FEATURE 13: WEBHOOK NOTIFICATIONS ==============

def set_webhook(user_id, project_name, webhook_url):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE projects SET webhook_url = ? WHERE user_id = ? AND project_name = ?", 
                 (webhook_url, user_id, project_name))
    conn.commit()
    conn.close()
    log_activity(user_id, "webhook_set", project_name, webhook_url)
    return True

def get_webhook(user_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT webhook_url FROM projects WHERE user_id = ? AND project_name = ?", 
                     (user_id, project_name))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def log_webhook_event(user_id, project_name, webhook_url, event, response_code):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''INSERT INTO webhook_logs (user_id, project_name, webhook_url, event, response_code, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (user_id, project_name, webhook_url, event, response_code, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# ============== FEATURE 14: BACKUP & RESTORE ==============

def backup_project(user_id, project_name):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    backup_dir = os.path.join(BASE_DIR, "backups", str(user_id))
    os.makedirs(backup_dir, exist_ok=True)
    
    backup_name = f"{project_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    backup_path = os.path.join(backup_dir, backup_name)
    
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(project_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, project_path)
                zipf.write(file_path, arcname)
    
    backup_size = os.path.getsize(backup_path) / (1024 * 1024)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''INSERT INTO backups (user_id, project_name, backup_path, backup_size, created_at)
                     VALUES (?, ?, ?, ?, ?)''',
                 (user_id, project_name, backup_path, backup_size, datetime.now().isoformat()))
    conn.execute("UPDATE projects SET is_backed_up = 1, last_backup = ? WHERE user_id = ? AND project_name = ?",
                 (datetime.now().isoformat(), user_id, project_name))
    conn.commit()
    conn.close()
    
    admin_stats["total_backups"] += 1
    log_activity(user_id, "backup", project_name, f"Size: {backup_size:.2f} MB")
    return backup_path

def list_backups(user_id, project_name=None):
    conn = sqlite3.connect(DB_PATH)
    if project_name:
        c = conn.execute("SELECT id, backup_path, backup_size, created_at FROM backups WHERE user_id = ? AND project_name = ? ORDER BY created_at DESC",
                         (user_id, project_name))
    else:
        c = conn.execute("SELECT id, backup_path, backup_size, created_at FROM backups WHERE user_id = ? ORDER BY created_at DESC",
                         (user_id,))
    backups = c.fetchall()
    conn.close()
    return backups

def restore_backup(user_id, backup_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT backup_path, project_name FROM backups WHERE id = ? AND user_id = ?", (backup_id, user_id))
    result = c.fetchone()
    conn.close()
    
    if result:
        backup_path, project_name = result
        user_dir = get_user_dir(user_id)
        project_path = os.path.join(user_dir, project_name)
        
        if os.path.exists(project_path):
            shutil.rmtree(project_path)
        
        os.makedirs(project_path, exist_ok=True)
        with zipfile.ZipFile(backup_path, 'r') as zipf:
            zipf.extractall(project_path)
        
        admin_stats["total_restores"] += 1
        log_activity(user_id, "restore", project_name, f"From backup {backup_id}")
        return True
    return False

# ============== FEATURE 15: RESOURCE MONITORING ==============

def monitor_resource_usage():
    while True:
        time.sleep(60)
        for user_id, user_projects in running_projects.items():
            for project_name, info in user_projects.items():
                try:
                    process = info["process"] if isinstance(info, dict) else info
                    if process.poll() is None:
                        proc = psutil.Process(process.pid)
                        cpu_percent = proc.cpu_percent(interval=1)
                        ram_mb = proc.memory_info().rss / (1024 * 1024)
                        
                        conn = sqlite3.connect(DB_PATH)
                        conn.execute('''INSERT INTO resource_usage (user_id, project_name, cpu_percent, ram_mb, timestamp)
                                        VALUES (?, ?, ?, ?, ?)''',
                                     (user_id, project_name, cpu_percent, ram_mb, datetime.now().isoformat()))
                        conn.commit()
                        conn.close()
                except:
                    pass

# ============== FEATURE 16: PORT MAPPING ==============

def assign_port(user_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    used_ports = [row[0] for row in conn.execute("SELECT port FROM port_mappings").fetchall()]
    conn.close()
    
    available = [p for p in AVAILABLE_PORTS if p not in used_ports]
    if available:
        port = available[0]
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO port_mappings (user_id, project_name, port, external_port, created_at) VALUES (?, ?, ?, ?, ?)",
                     (user_id, project_name, port, port, datetime.now().isoformat()))
        conn.execute("UPDATE projects SET port = ? WHERE user_id = ? AND project_name = ?",
                     (port, user_id, project_name))
        conn.commit()
        conn.close()
        return port
    return None

def get_project_port(user_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT port FROM projects WHERE user_id = ? AND project_name = ?", (user_id, project_name))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# ============== FEATURE 17: ENVIRONMENT VARIABLES ==============

def save_env_vars(user_id, project_name, env_vars):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    env_file = os.path.join(project_path, ".env")
    
    with open(env_file, 'w') as f:
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")
    
    log_activity(user_id, "env_vars_saved", project_name, f"Saved {len(env_vars)} variables")
    return True

def load_env_vars(user_id, project_name):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    env_file = os.path.join(project_path, ".env")
    
    env_vars = {}
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    env_vars[key] = value
    return env_vars

# ============== FEATURE 18: FILE MANAGER ==============

def list_project_files(user_id, project_name, path=""):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name, path)
    
    if not os.path.exists(project_path):
        return None, "Path not found"
    
    files = []
    for item in os.listdir(project_path):
        item_path = os.path.join(project_path, item)
        is_dir = os.path.isdir(item_path)
        size = get_folder_size(item_path) if is_dir else os.path.getsize(item_path)
        modified = datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M')
        files.append({
            "name": item,
            "is_dir": is_dir,
            "size": size,
            "modified": modified
        })
    
    return files, None

def get_file_content(user_id, project_name, file_path):
    user_dir = get_user_dir(user_id)
    full_path = os.path.join(user_dir, project_name, file_path)
    
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        return None, "File not found"
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content, None
    except Exception as e:
        return None, str(e)

def save_file_content(user_id, project_name, file_path, content):
    user_dir = get_user_dir(user_id)
    full_path = os.path.join(user_dir, project_name, file_path)
    
    try:
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True, None
    except Exception as e:
        return False, str(e)

def delete_file(user_id, project_name, file_path):
    user_dir = get_user_dir(user_id)
    full_path = os.path.join(user_dir, project_name, file_path)
    
    if not os.path.exists(full_path):
        return False, "File not found"
    
    try:
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        return True, None
    except Exception as e:
        return False, str(e)

# ============== FEATURE 19: GIT INTEGRATION ==============

def git_clone(user_id, project_name, repo_url, branch="main"):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    
    if os.path.exists(project_path):
        return False, "Project already exists"
    
    try:
        result = subprocess.run(["git", "clone", "-b", branch, repo_url, project_path], 
                              capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE projects SET git_repo = ? WHERE user_id = ? AND project_name = ?",
                         (repo_url, user_id, project_name))
            conn.commit()
            conn.close()
            
            log_activity(user_id, "git_clone", project_name, repo_url)
            return True, "Repository cloned successfully"
        else:
            return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "Clone timeout"
    except Exception as e:
        return False, str(e)

def git_pull(user_id, project_name):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    
    if not os.path.exists(os.path.join(project_path, ".git")):
        return False, "Not a git repository"
    
    try:
        result = subprocess.run(["git", "pull"], cwd=project_path, capture_output=True, text=True, timeout=60)
        return result.returncode == 0, result.stdout if result.returncode == 0 else result.stderr
    except subprocess.TimeoutExpired:
        return False, "Pull timeout"
    except Exception as e:
        return False, str(e)

# ============== FEATURE 20: PROJECT SEARCH ==============

def search_projects(user_id, keyword):
    projects = get_user_projects(user_id)
    results = []
    
    for project in projects:
        if keyword.lower() in project.lower():
            results.append(project)
            continue
        
        # Search in description
        desc = get_project_description(user_id, project)
        if desc and keyword.lower() in desc.lower():
            results.append(project)
    
    return results

# ============== FEATURE 21: PROJECT EXPORT ==============

def export_project(user_id, project_name):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    
    if not os.path.exists(project_path):
        return None, "Project not found"
    
    export_dir = os.path.join(BASE_DIR, "exports", str(user_id))
    os.makedirs(export_dir, exist_ok=True)
    
    export_name = f"{project_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    export_path = os.path.join(export_dir, export_name)
    
    with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(project_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, project_path)
                zipf.write(file_path, arcname)
    
    return export_path, None

# ============== FEATURE 22: PROJECT IMPORT ==============

def import_project(user_id, project_name, zip_path):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    
    if os.path.exists(project_path):
        return False, "Project already exists"
    
    try:
        os.makedirs(project_path, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(project_path)
        
        size_mb = get_folder_size(project_path)
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO projects (user_id, project_name, created_at, size_mb) VALUES (?, ?, ?, ?)",
                     (user_id, project_name, datetime.now().isoformat(), size_mb))
        conn.commit()
        conn.close()
        
        log_activity(user_id, "import", project_name, f"Imported from {zip_path}")
        return True, "Project imported successfully"
    except Exception as e:
        return False, str(e)

# ============== FEATURE 23: STARTUP COMMAND CUSTOMIZATION ==============

def set_startup_command(user_id, project_name, command):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE projects SET startup_command = ? WHERE user_id = ? AND project_name = ?",
                 (command, user_id, project_name))
    conn.commit()
    conn.close()
    log_activity(user_id, "startup_command", project_name, command)
    return True

def get_startup_command(user_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT startup_command FROM projects WHERE user_id = ? AND project_name = ?",
                     (user_id, project_name))
    result = c.fetchone()
    conn.close()
    return result[0] if result else "python main.py"

# ============== FEATURE 24: PROJECT HEALTH CHECK ==============

def health_check_project(user_id, project_name):
    if project_name not in get_user_running_projects(user_id):
        return False, "Project is not running"
    
    project_info = get_user_running_projects(user_id)[project_name]
    process = project_info["process"] if isinstance(project_info, dict) else project_info
    
    if process.poll() is not None:
        return False, "Process is dead"
    
    # Check CPU and memory usage
    try:
        proc = psutil.Process(process.pid)
        cpu = proc.cpu_percent(interval=0.5)
        mem = proc.memory_info().rss / (1024 * 1024)
        
        status = "healthy" if cpu < 80 and mem < 500 else "high_usage"
        return True, f"✅ Healthy\nCPU: {cpu:.1f}%\nRAM: {mem:.1f}MB"
    except:
        return True, "✅ Running (detailed stats unavailable)"

# ============== FEATURE 25: USER SETTINGS ==============

def get_user_settings(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT auto_delete_logs, max_projects, backup_enabled, notification_enabled, log_level FROM user_settings WHERE user_id = ?",
                     (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        return {
            "auto_delete_logs": result[0],
            "max_projects": result[1],
            "backup_enabled": result[2],
            "notification_enabled": result[3],
            "log_level": result[4]
        }
    else:
        # Default settings
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO user_settings (user_id, auto_delete_logs, max_projects, backup_enabled, notification_enabled, log_level) VALUES (?, 7, 15, 1, 1, 'info')",
                     (user_id,))
        conn.commit()
        conn.close()
        return {
            "auto_delete_logs": 7,
            "max_projects": 15,
            "backup_enabled": 1,
            "notification_enabled": 1,
            "log_level": "info"
        }

def update_user_setting(user_id, setting, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"UPDATE user_settings SET {setting} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()
    return True

# ============== FEATURE 26: ANALYTICS DASHBOARD ==============

def log_analytics_event(user_id, event_type, event_data=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO analytics_events (user_id, event_type, event_data, timestamp) VALUES (?, ?, ?, ?)",
                 (user_id, event_type, event_data, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user_analytics(user_id):
    conn = sqlite3.connect(DB_PATH)
    
    # Total projects created
    c = conn.execute("SELECT COUNT(*) FROM projects WHERE user_id = ?", (user_id,))
    total_projects = c.fetchone()[0]
    
    # Total runs
    c = conn.execute("SELECT SUM(total_runs) FROM projects WHERE user_id = ?", (user_id,))
    total_runs = c.fetchone()[0] or 0
    
    # Total uptime (in minutes)
    c = conn.execute("SELECT SUM(total_uptime) FROM projects WHERE user_id = ?", (user_id,))
    total_uptime = c.fetchone()[0] or 0
    
    # Most active project
    c = conn.execute("SELECT project_name, total_runs FROM projects WHERE user_id = ? ORDER BY total_runs DESC LIMIT 1", (user_id,))
    most_active = c.fetchone()
    
    conn.close()
    
    return {
        "total_projects": total_projects,
        "total_runs": total_runs,
        "total_uptime_hours": total_uptime // 60,
        "most_active_project": most_active[0] if most_active else None,
        "most_active_runs": most_active[1] if most_active else 0
    }

# ============== FEATURE 27: QUICK ACTIONS ==============

QUICK_ACTIONS = [
    "🚀 Quick Deploy",
    "📋 Duplicate Last",
    "🔄 Restart All",
    "⏹️ Stop All",
    "📊 Quick Stats"
]

def quick_deploy(user_id, template_name):
    projects = get_user_projects(user_id)
    new_name = f"{template_name}_{len(projects) + 1}"
    return create_project_from_template(user_id, new_name, template_name)

def duplicate_last_project(user_id):
    projects = get_user_projects(user_id)
    if not projects:
        return False, "No projects to duplicate"
    
    last_project = projects[-1]
    new_name = f"{last_project}_copy_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return clone_project(user_id, last_project, new_name)

def quick_stats(user_id):
    projects = get_user_projects(user_id)
    running = len(get_user_running_projects(user_id))
    total_size = 0
    
    for project in projects:
        user_dir = get_user_dir(user_id)
        project_path = os.path.join(user_dir, project)
        total_size += sum(os.path.getsize(os.path.join(dirpath, filename)) 
                         for dirpath, dirnames, filnames in os.walk(project_path) 
                         for filename in filnames)
    
    size_mb = total_size / (1024 * 1024)
    
    return {
        "total": len(projects),
        "running": running,
        "stopped": len(projects) - running,
        "size_mb": round(size_mb, 2)
    }

# ============== FEATURE 28: PROJECT TAGS ==============

def add_project_tag(user_id, project_name, tag):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO project_tags (user_id, project_name, tag) VALUES (?, ?, ?)",
                 (user_id, project_name, tag))
    conn.commit()
    conn.close()
    return True

def get_projects_by_tag(user_id, tag):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT project_name FROM project_tags WHERE user_id = ? AND tag = ?", (user_id, tag))
    projects = [row[0] for row in c.fetchall()]
    conn.close()
    return projects

# ============== FEATURE 29: BOT COMMANDS HELP ==============

COMMANDS_HELP = {
    "📦 Upload": "Upload a Python project zip file",
    "📁 Projects": "List all your projects",
    "▶️ Start": "Start a project",
    "⏹️ Stop": "Stop a running project",
    "🔄 Restart": "Restart a project",
    "🗑️ Delete": "Delete a project",
    "🗑️ Delete All": "Delete all your projects",
    "📊 Stats": "View your statistics",
    "🔄 Refresh": "Refresh project status",
    "📝 Errors": "View error logs",
    "📋 Templates": "Create from templates",
    "⚙️ Advanced": "Advanced features menu",
    "🎫 Support": "Get support",
    "❓ Help": "Show this help"
}

def get_help_text():
    text = "📚 *BOT COMMANDS HELP*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for cmd, desc in COMMANDS_HELP.items():
        text += f"• **{cmd}** - {desc}\n"
    
    text += """
💡 *TIPS:*
• Use the buttons below to navigate
• Each user has private workspace
• Max file size: 100MB
• Support available 24/7

💻 *Powered by @Hexh4ckerOFC*
    """
    return text

# ============== FEATURE 30: STARTUP COMMAND ==============

@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.chat.id
    is_admin = (user_id == ADMIN_ID)
    
    # Check if coming from referral
    if ' ' in msg.text:
        ref_code = msg.text.split(' ')[1]
        if ref_code.startswith('ref_'):
            code = ref_code.replace('ref_', '')
            # Process referral
            conn = sqlite3.connect(DB_PATH)
            c = conn.execute("SELECT user_id FROM users WHERE referral_code = ?", (code,))
            result = c.fetchone()
            if result and result[0] != user_id:
                conn.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (result[0], user_id))
                send_notification(result[0], f"🎉 You got a new referral! User {user_id} joined using your link.")
                log_activity(result[0], "referral", "", f"Referred user {user_id}")
            conn.close()
    
    # Register user
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if not c.fetchone():
        conn.execute("INSERT INTO users (user_id, username, first_name, join_date, last_active) VALUES (?, ?, ?, ?, ?)",
                     (user_id, msg.from_user.username or "", msg.from_user.first_name or "", 
                      datetime.now().isoformat(), datetime.now().isoformat()))
        # Generate referral code
        ref_code = generate_referral_code(user_id)
        conn.execute("UPDATE users SET referral_code = ? WHERE user_id = ?", (ref_code, user_id))
    conn.commit()
    conn.close()
    
    total_projects = len(get_user_projects(user_id))
    running_count = len(get_user_running_projects(user_id))
    
    welcome_text = f"""
🔥 *WELCOME TO PYTHON HOSTING*

✨ *Hex Python Hosting Panel v3.0*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 30+ Advanced Features
✅ User-Specific Workspaces
✅ No File Conflicts
✅ Template System
✅ Auto-Backup & Restore
✅ Git Integration
✅ File Manager
✅ Analytics Dashboard

👤 *Your Workspace:*
├─ User ID: `{user_id}`
├─ Projects: {total_projects}
├─ Running: {running_count}
└─ Role: {'👑 ADMIN' if is_admin else '👤 USER'}

💡 *New Features:* Templates, Git, File Manager, Analytics!

💻 *Powered by @Hexh4ckerOFC*
    """
    
    bot.send_message(msg.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

# ============== MAIN KEYBOARD ==============

def get_main_keyboard(user_id):
    is_admin = (user_id == ADMIN_ID)
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "📦 Upload", "📁 Projects",
        "▶️ Start", "⏹️ Stop",
        "🔄 Restart", "🗑️ Delete",
        "🗑️ Delete All", "📊 Stats",
        "🔄 Refresh", "📝 Errors",
        "📋 Templates", "⚙️ Advanced",
        "🎫 Support", "❓ Help"
    ]
    
    if is_admin:
        buttons.append("👑 Admin Panel")
    
    markup.add(*buttons)
    return markup

# ============== MESSAGE HANDLERS ==============

@bot.message_handler(func=lambda m: m.text == "📦 Upload")
def upload_btn(msg):
    bot.send_message(msg.chat.id, "📦 *Send your .zip file with:*\n• `main.py`\n• `requirements.txt` (optional)\n\n📝 *Max size: 100MB*\n🔒 *Your files are private*", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📁 Projects")
def file_manager(msg):
    user_id = msg.chat.id
    projects = get_user_projects(user_id)
    user_running = get_user_running_projects(user_id)
    
    if not projects:
        bot.send_message(msg.chat.id, "📂 *No projects found*\nUse 📦 Upload to add one.", parse_mode="Markdown")
        return
    
    project_list = f"📁 *YOUR PROJECTS*\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for project in projects:
        is_running = project in user_running
        status_icon = "🟢" if is_running else "⚪"
        project_list += f"\n{status_icon} `{project}`\n"
    
    project_list += f"\n💻 *Powered by @Hexh4ckerOFC*"
    bot.send_message(msg.chat.id, project_list, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📋 Templates")
def templates_menu(msg):
    user_id = msg.chat.id
    
    text = "📋 *PROJECT TEMPLATES*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for name, template in PROJECT_TEMPLATES.items():
        text += f"• **{name}** - {template['description']}\n"
    
    text += "\n💡 *Select a template below to create a new project:*"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for name in PROJECT_TEMPLATES.keys():
        markup.add(InlineKeyboardButton(f"📁 {name.upper()}", callback_data=f"template_{name}"))
    
    bot.send_message(msg.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "⚙️ Advanced")
def advanced_menu(msg):
    user_id = msg.chat.id
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 Analytics", callback_data="adv_analytics"),
        InlineKeyboardButton("💾 Backup/Restore", callback_data="adv_backup"),
        InlineKeyboardButton("🔄 Auto-Restart", callback_data="adv_autorestart"),
        InlineKeyboardButton("⏰ Scheduled Tasks", callback_data="adv_scheduled"),
        InlineKeyboardButton("🔗 Webhooks", callback_data="adv_webhook"),
        InlineKeyboardButton("📝 Logs Viewer", callback_data="adv_logs"),
        InlineKeyboardButton("📁 File Manager", callback_data="adv_filemanager"),
        InlineKeyboardButton("🐙 Git Integration", callback_data="adv_git"),
        InlineKeyboardButton("🔧 Dependencies", callback_data="adv_deps"),
        InlineKeyboardButton("🌍 Environment Vars", callback_data="adv_env"),
        InlineKeyboardButton("📋 Batch Ops", callback_data="adv_batch"),
        InlineKeyboardButton("🔄 Clone Project", callback_data="adv_clone"),
        InlineKeyboardButton("📤 Export Project", callback_data="adv_export"),
        InlineKeyboardButton("🔍 Search Projects", callback_data="adv_search"),
        InlineKeyboardButton("⚙️ Settings", callback_data="adv_settings"),
        InlineKeyboardButton("📊 Quick Stats", callback_data="adv_quickstats"),
        InlineKeyboardButton("🏥 Health Check", callback_data="adv_health"),
        InlineKeyboardButton("🔙 Back", callback_data="back_to_main")
    )
    
    bot.send_message(msg.chat.id, "⚙️ *ADVANCED FEATURES*\n\nSelect an option below:", 
                     parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🎫 Support")
def support_menu(msg):
    user_id = msg.chat.id
    
    text = f"🎫 *SUPPORT SYSTEM*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "Need help? Create a support ticket and we'll respond within 24 hours.\n\n"
    text += "💡 *Common issues:*\n"
    text += "• Check if main.py exists\n"
    text += "• Ensure all dependencies are installed\n"
    text += "• Check logs for errors\n\n"
    text += "💻 *Powered by @Hexh4ckerOFC*"
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("📝 Create Ticket", callback_data="create_ticket"),
        InlineKeyboardButton("📋 My Tickets", callback_data="my_tickets")
    )
    
    bot.send_message(msg.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "❓ Help")
def help_command(msg):
    bot.send_message(msg.chat.id, get_help_text(), parse_mode="Markdown")

# ============== CALLBACK HANDLERS ==============

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.message.chat.id
    
    # Template selection
    if call.data.startswith("template_"):
        template_name = call.data.replace("template_", "")
        user_sessions[user_id] = {"state": "template_name", "template": template_name}
        bot.edit_message_text(f"📝 *Create from {template_name.upper()} template*\n\nSend a name for your new project:", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    # Advanced features callbacks
    elif call.data == "adv_analytics":
        analytics = get_user_analytics(user_id)
        text = f"""
📊 *YOUR ANALYTICS*
━━━━━━━━━━━━━━━━━━━━━━

📦 *Projects*
├─ Total: {analytics['total_projects']}
├─ Total Runs: {analytics['total_runs']}
└─ Uptime: {analytics['total_uptime_hours']} hours

🏆 *Most Active*
├─ Project: {analytics['most_active_project'] or 'None'}
└─ Runs: {analytics['most_active_runs']}

💻 *Powered by @Hexh4ckerOFC*
        """
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "adv_backup":
        projects = get_user_projects(user_id)
        if not projects:
            bot.edit_message_text("❌ *No projects found*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            return
        
        markup = InlineKeyboardMarkup(row_width=2)
        for project in projects:
            markup.add(InlineKeyboardButton(f"💾 {project}", callback_data=f"backup_{project}"))
        markup.add(InlineKeyboardButton("📋 List Backups", callback_data="list_backups"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_advanced"))
        
        bot.edit_message_text("💾 *BACKUP SYSTEM*\n\nSelect a project to backup:", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data.startswith("backup_"):
        project_name = call.data.replace("backup_", "")
        backup_path = backup_project(user_id, project_name)
        bot.answer_callback_query(call.id, f"Backup created for {project_name}")
        bot.edit_message_text(f"✅ *Backup created for '{project_name}'!*\n\n📁 Backup saved.\n\nUse 'List Backups' to restore.", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "list_backups":
        backups = list_backups(user_id)
        if not backups:
            bot.edit_message_text("📭 *No backups found*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            return
        
        text = "💾 *YOUR BACKUPS*\n━━━━━━━━━━━━━━━━━━━━━━\n"
        markup = InlineKeyboardMarkup(row_width=1)
        for backup in backups[:10]:
            backup_id, backup_path, backup_size, created_at = backup
            text += f"\n📦 #{backup_id}: {os.path.basename(backup_path)}\n   ├─ Size: {backup_size:.2f} MB\n   └─ Date: {created_at[:16]}\n"
            markup.add(InlineKeyboardButton(f"🔄 Restore #{backup_id}", callback_data=f"restore_{backup_id}"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="adv_backup"))
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data.startswith("restore_"):
        backup_id = int(call.data.replace("restore_", ""))
        if restore_backup(user_id, backup_id):
            bot.answer_callback_query(call.id, "Project restored successfully!")
            bot.edit_message_text("✅ *Project restored from backup!*\n\nYou may need to restart the project.", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, "Restore failed!")
    
    elif call.data == "adv_autorestart":
        projects = get_user_projects(user_id)
        if not projects:
            bot.edit_message_text("❌ *No projects found*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            return
        
        markup = InlineKeyboardMarkup(row_width=1)
        for project in projects:
            status = get_auto_restart_status(user_id, project)
            icon = "✅" if status else "❌"
            markup.add(InlineKeyboardButton(f"{icon} {project}", callback_data=f"toggle_auto_{project}"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_advanced"))
        
        bot.edit_message_text("🔄 *AUTO-RESTART SETTINGS*\n\nToggle auto-restart for each project:", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data.startswith("toggle_auto_"):
        project_name = call.data.replace("toggle_auto_", "")
        current = get_auto_restart_status(user_id, project_name)
        set_auto_restart(user_id, project_name, not current)
        bot.answer_callback_query(call.id, f"Auto-restart {'enabled' if not current else 'disabled'} for {project_name}")
        
        # Refresh menu
        projects = get_user_projects(user_id)
        markup = InlineKeyboardMarkup(row_width=1)
        for proj in projects:
            status = get_auto_restart_status(user_id, proj)
            icon = "✅" if status else "❌"
            markup.add(InlineKeyboardButton(f"{icon} {proj}", callback_data=f"toggle_auto_{proj}"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_advanced"))
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif call.data == "adv_scheduled":
        tasks = get_user_scheduled_tasks(user_id)
        if not tasks:
            text = "⏰ *SCHEDULED TASKS*\n━━━━━━━━━━━━━━━━━━━━━━\n\n📭 *No scheduled tasks*\n\nUse the button below to create one."
        else:
            text = "⏰ *SCHEDULED TASKS*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            for task in tasks:
                task_id, project_name, action, schedule_time, recurring = task
                recurring_icon = "🔄" if recurring else "⏰"
                text += f"\n{recurring_icon} #{task_id}: {project_name} - {action}\n   └─ Time: {schedule_time[:16]}\n"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ Create Task", callback_data="create_task"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_advanced"))
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "adv_logs":
        projects = get_user_projects(user_id)
        if not projects:
            bot.edit_message_text("❌ *No projects found*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            return
        
        markup = InlineKeyboardMarkup(row_width=1)
        for project in projects:
            markup.add(InlineKeyboardButton(f"📝 {project}", callback_data=f"view_logs_{project}"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_advanced"))
        
        bot.edit_message_text("📝 *PROJECT LOGS*\n\nSelect a project to view logs:", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data.startswith("view_logs_"):
        project_name = call.data.replace("view_logs_", "")
        success, logs = get_project_logs(user_id, project_name, 100)
        
        if success and logs:
            log_text = f"📝 *LOGS: {project_name}*\n━━━━━━━━━━━━━━━━━━━━━━\n```\n{logs[-2000:]}\n```"
            if len(log_text) > 4000:
                log_text = log_text[:4000] + "\n... (truncated)"
        else:
            log_text = f"📝 *LOGS: {project_name}*\n━━━━━━━━━━━━━━━━━━━━━━\n\n{logs or 'No logs found'}"
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🔄 Refresh", callback_data=f"view_logs_{project_name}"),
            InlineKeyboardButton("🗑️ Clear", callback_data=f"clear_logs_{project_name}"),
            InlineKeyboardButton("🔙 Back", callback_data="adv_logs")
        )
        
        bot.edit_message_text(log_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data.startswith("clear_logs_"):
        project_name = call.data.replace("clear_logs_", "")
        clear_project_logs(user_id, project_name)
        bot.answer_callback_query(call.id, f"Logs cleared for {project_name}")
        bot.edit_message_text(f"✅ *Logs cleared for '{project_name}'*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "adv_filemanager":
        projects = get_user_projects(user_id)
        if not projects:
            bot.edit_message_text("❌ *No projects found*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            return
        
        markup = InlineKeyboardMarkup(row_width=1)
        for project in projects:
            markup.add(InlineKeyboardButton(f"📁 {project}", callback_data=f"fm_project_{project}"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_advanced"))
        
        bot.edit_message_text("📁 *FILE MANAGER*\n\nSelect a project to browse files:", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data.startswith("fm_project_"):
        project_name = call.data.replace("fm_project_", "")
        user_sessions[user_id] = {"state": "fm_browse", "project": project_name, "path": ""}
        
        files, error = list_project_files(user_id, project_name)
        if error:
            bot.edit_message_text(f"❌ *Error:* {error}", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            return
        
        text = f"📁 *{project_name}* /\n━━━━━━━━━━━━━━━━━━━━━━\n"
        markup = InlineKeyboardMarkup(row_width=2)
        
        for file in files:
            icon = "📁" if file["is_dir"] else "📄"
            markup.add(InlineKeyboardButton(f"{icon} {file['name']}", callback_data=f"fm_open_{project_name}_{file['name']}"))
        
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="adv_filemanager"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "adv_deps":
        projects = get_user_projects(user_id)
        if not projects:
            bot.edit_message_text("❌ *No projects found*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            return
        
        markup = InlineKeyboardMarkup(row_width=1)
        for project in projects:
            markup.add(InlineKeyboardButton(f"📦 {project}", callback_data=f"deps_{project}"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_advanced"))
        
        bot.edit_message_text("📦 *DEPENDENCY MANAGER*\n\nSelect a project to manage dependencies:", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data.startswith("deps_"):
        project_name = call.data.replace("deps_", "")
        deps = list_dependencies(user_id, project_name)
        
        if deps:
            text = f"📦 *DEPENDENCIES: {project_name}*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            for dep in deps[:30]:
                dep_name, version, installed_at = dep
                text += f"\n• {dep_name}=={version}\n  └─ Installed: {installed_at[:10]}\n"
        else:
            text = f"📦 *DEPENDENCIES: {project_name}*\n━━━━━━━━━━━━━━━━━━━━━━\n\n📭 *No dependencies installed yet*\n\nRun 'pip install -r requirements.txt' to install."
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("📥 Install Dependencies", callback_data=f"install_deps_{project_name}"),
            InlineKeyboardButton("🔙 Back", callback_data="adv_deps")
        )
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data.startswith("install_deps_"):
        project_name = call.data.replace("install_deps_", "")
        bot.edit_message_text(f"📥 *Installing dependencies for '{project_name}'...*\n\nThis may take a moment.", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
        success, output = install_dependencies(user_id, project_name)
        
        if success:
            bot.edit_message_text(f"✅ *Dependencies installed successfully for '{project_name}'!*", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text(f"❌ *Installation failed for '{project_name}'*\n\nError: {output[:200]}", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "adv_batch":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("▶️ Start All", callback_data="batch_start_all"),
            InlineKeyboardButton("⏹️ Stop All", callback_data="batch_stop_all"),
            InlineKeyboardButton("🔄 Restart All", callback_data="batch_restart_all"),
            InlineKeyboardButton("🗑️ Delete All", callback_data="batch_delete_all"),
            InlineKeyboardButton("🔙 Back", callback_data="back_to_advanced")
        )
        
        bot.edit_message_text("📋 *BATCH OPERATIONS*\n\nSelect an operation:", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "batch_start_all":
        projects = get_user_projects(user_id)
        if not projects:
            bot.edit_message_text("❌ *No projects to start*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            return
        
        bot.edit_message_text(f"🔄 *Starting {len(projects)} projects...*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
        results = batch_start_projects(user_id, projects)
        result_text = "✅ *Batch Start Complete*\n\n" + "\n".join(results)
        
        bot.send_message(call.message.chat.id, result_text, parse_mode="Markdown")
        bot.delete_message(call.message.chat.id, call.message.message_id)
    
    elif call.data == "batch_stop_all":
        running = list(get_user_running_projects(user_id).keys())
        if not running:
            bot.edit_message_text("⚠️ *No running projects to stop*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            return
        
        bot.edit_message_text(f"⏹️ *Stopping {len(running)} projects...*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
        results = batch_stop_projects(user_id, running)
        result_text = "⏹️ *Batch Stop Complete*\n\n" + "\n".join(results)
        
        bot.send_message(call.message.chat.id, result_text, parse_mode="Markdown")
        bot.delete_message(call.message.chat.id, call.message.message_id)
    
    elif call.data == "batch_delete_all":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ YES, Delete All", callback_data="confirm_delete_all"),
            InlineKeyboardButton("❌ NO, Cancel", callback_data="cancel_delete")
        )
        bot.edit_message_text("⚠️ *WARNING: This will delete ALL your projects!*\nAre you sure?", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "adv_clone":
        projects = get_user_projects(user_id)
        if not projects:
            bot.edit_message_text("❌ *No projects to clone*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            return
        
        markup = InlineKeyboardMarkup(row_width=1)
        for project in projects:
            markup.add(InlineKeyboardButton(f"📋 {project}", callback_data=f"clone_select_{project}"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_advanced"))
        
        bot.edit_message_text("🔄 *CLONE PROJECT*\n\nSelect a project to clone:", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data.startswith("clone_select_"):
        source_project = call.data.replace("clone_select_", "")
        user_sessions[user_id] = {"state": "awaiting_clone_name", "source": source_project}
        bot.edit_message_text(f"📝 *Clone '{source_project}'\n\nSend the new project name:", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "adv_search":
        user_sessions[user_id] = {"state": "awaiting_search"}
        bot.edit_message_text("🔍 *SEARCH PROJECTS*\n\nSend a keyword to search for:", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "adv_quickstats":
        stats = quick_stats(user_id)
        text = f"""
📊 *QUICK STATS*
━━━━━━━━━━━━━━━━━━━━━━

📦 *Projects*
├─ Total: {stats['total']}
├─ Running: {stats['running']} 🟢
├─ Stopped: {stats['stopped']} ⚪
└─ Size: {stats['size_mb']} MB

💡 *Pro Tip:* Use templates for quick deployment!

💻 *Powered by @Hexh4ckerOFC*
        """
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "adv_health":
        running = get_user_running_projects(user_id)
        if not running:
            bot.edit_message_text("⚠️ *No running projects to check*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            return
        
        text = "🏥 *HEALTH CHECK*\n━━━━━━━━━━━━━━━━━━━━━━\n"
        
        for project in running.keys():
            success, result = health_check_project(user_id, project)
            icon = "✅" if success else "❌"
            text += f"\n{icon} **{project}**\n{result}\n"
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "adv_settings":
        settings = get_user_settings(user_id)
        text = f"""
⚙️ *USER SETTINGS*
━━━━━━━━━━━━━━━━━━━━━━

📝 *Logs*
├─ Auto-delete: {settings['auto_delete_logs']} days
└─ Log level: {settings['log_level']}

📦 *Projects*
└─ Max projects: {settings['max_projects']}

🔔 *Notifications*
├─ Enabled: {'✅' if settings['notification_enabled'] else '❌'}
└─ Auto-backup: {'✅' if settings['backup_enabled'] else '❌'}

💻 *Powered by @Hexh4ckerOFC*
        """
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "create_ticket":
        user_sessions[user_id] = {"state": "ticket_subject"}
        bot.edit_message_text("📝 *Create Support Ticket*\n\nSend the ticket subject:", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "my_tickets":
        tickets = get_user_tickets(user_id)
        if not tickets:
            bot.edit_message_text("📭 *No tickets found*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            return
        
        text = "🎫 *YOUR TICKETS*\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for ticket in tickets:
            ticket_id, subject, status, created, priority = ticket
            priority_icon = "🔴" if priority == "high" else "🟡" if priority == "medium" else "🔵"
            status_icon = "🟢" if status == "open" else "🟡" if status == "responded" else "🔴"
            text += f"\n{priority_icon} #{ticket_id}: {subject[:30]}\n├─ Status: {status_icon} {status}\n└─ Created: {created[:16]}\n"
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "confirm_delete_all":
        projects = get_user_projects(user_id)
        for project in projects:
            delete_project(user_id, project)
        bot.edit_message_text("🗑️ *ALL your projects deleted successfully!*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "cancel_delete":
        bot.edit_message_text("❌ *Action cancelled*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "back_to_main":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        start(call.message)
    
    elif call.data == "back_to_advanced":
        advanced_menu(call.message)
    
    bot.answer_callback_query(call.id)

# ============== MESSAGE HANDLERS FOR SESSIONS ==============

@bot.message_handler(func=lambda m: m.text and m.chat.id in user_sessions)
def handle_session_messages(msg):
    user_id = msg.chat.id
    session = user_sessions.get(user_id, {})
    state = session.get("state")
    
    if state == "template_name":
        template_name = session.get("template")
        project_name = msg.text.strip().replace(" ", "_")
        success, message = create_project_from_template(user_id, project_name, template_name)
        
        if success:
            bot.send_message(user_id, f"✅ {message}\n\nUse ▶️ Start to run your project!", parse_mode="Markdown")
        else:
            bot.send_message(user_id, f"❌ {message}", parse_mode="Markdown")
        
        del user_sessions[user_id]
    
    elif state == "awaiting_clone_name":
        source = session.get("source")
        new_name = msg.text.strip().replace(" ", "_")
        success, message = clone_project(user_id, source, new_name)
        
        if success:
            bot.send_message(user_id, f"✅ {message}", parse_mode="Markdown")
        else:
            bot.send_message(user_id, f"❌ {message}", parse_mode="Markdown")
        
        del user_sessions[user_id]
    
    elif state == "awaiting_search":
        keyword = msg.text.strip()
        results = search_projects(user_id, keyword)
        
        if results:
            text = f"🔍 *Search Results for '{keyword}'*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            for project in results:
                text += f"\n• `{project}`\n"
            text += f"\n💻 *Powered by @Hexh4ckerOFC*"
        else:
            text = f"🔍 *No projects found matching '{keyword}'*"
        
        bot.send_message(user_id, text, parse_mode="Markdown")
        del user_sessions[user_id]
    
    elif state == "ticket_subject":
        user_sessions[user_id]["subject"] = msg.text
        user_sessions[user_id]["state"] = "ticket_message"
        bot.send_message(user_id, "📝 *Ticket Subject Received*\n\nNow send your detailed message:", parse_mode="Markdown")
    
    elif state == "ticket_message":
        subject = user_sessions[user_id].get("subject")
        message = msg.text
        ticket_id = create_support_ticket(user_id, subject, message)
        bot.send_message(user_id, f"✅ *Ticket #{ticket_id} created!*\n\nWe'll respond within 24 hours.\n\nYou can check status with '📋 My Tickets' button.", 
                        parse_mode="Markdown")
        del user_sessions[user_id]

# ============== FILE UPLOAD HANDLER ==============

@bot.message_handler(content_types=['document'])
def handle_zip(msg):
    user_id = msg.chat.id
    
    if not msg.document.file_name.endswith(".zip"):
        bot.send_message(msg.chat.id, "❌ *Send only .zip file*", parse_mode="Markdown")
        return
    
    status_msg = bot.send_message(msg.chat.id, "📦 *Processing upload...*", parse_mode="Markdown")
    
    file_info = bot.get_file(msg.document.file_id)
    downloaded = bot.download_file(file_info.file_path)
    
    original_name = msg.document.file_name.replace(".zip", "")
    project_name = "".join(c for c in original_name if c.isalnum() or c in ('-', '_'))
    
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    
    if os.path.exists(project_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = f"{project_name}_{timestamp}"
        project_path = os.path.join(user_dir, project_name)
        bot.send_message(msg.chat.id, f"📝 *Project renamed to '{project_name}' to avoid conflict*", parse_mode="Markdown")
    
    try:
        zip_path = os.path.join(user_dir, f"{project_name}.zip")
        extract_path = project_path
        
        with open(zip_path, 'wb') as f:
            f.write(downloaded)
        
        os.makedirs(extract_path, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
            
            extracted_items = os.listdir(extract_path)
            if len(extracted_items) == 1 and os.path.isdir(os.path.join(extract_path, extracted_items[0])):
                subfolder = os.path.join(extract_path, extracted_items[0])
                for item in os.listdir(subfolder):
                    shutil.move(os.path.join(subfolder, item), extract_path)
                os.rmdir(subfolder)
        
        os.remove(zip_path)
        
        size_mb = get_folder_size(extract_path)
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO projects (user_id, project_name, created_at, size_mb) VALUES (?, ?, ?, ?)",
                     (user_id, project_name, datetime.now().isoformat(), size_mb))
        conn.commit()
        conn.close()
        
        bot.edit_message_text(f"✅ *Project '{project_name}' uploaded successfully!*\n\n📁 Size: {size_mb}\n\nUse ▶️ Start to run your project.", 
                            msg.chat.id, status_msg.message_id, parse_mode="Markdown")
        
        log_activity(user_id, "upload", project_name, f"Size: {size_mb}")
        
    except Exception as e:
        bot.edit_message_text(f"❌ *Upload failed:* `{str(e)[:150]}`", 
                            msg.chat.id, status_msg.message_id, parse_mode="Markdown")

# ============== START/STOP/RESTART/DELETE FUNCTIONS ==============

def start_project(user_id, project_name):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    main_file = os.path.join(project_path, "main.py")
    user_running = get_user_running_projects(user_id)
    
    if not os.path.exists(main_file):
        error_msg = f"main.py not found in '{project_name}'"
        user_errors = get_user_errors(user_id)
        user_errors[project_name] = error_msg
        return False
    
    if project_name in user_running:
        return False
    
    try:
        process = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True
        )
        
        user_running[project_name] = {
            "process": process,
            "cwd": project_path,
            "started_at": datetime.now()
        }
        
        user_errors = get_user_errors(user_id)
        if project_name in user_errors:
            del user_errors[project_name]
        
        log_file = os.path.join(project_path, "project.log")
        with open(log_file, 'a') as f:
            f.write(f"\n[STARTED] at {datetime.now()}\n")
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE projects SET total_runs = total_runs + 1, last_started = ? WHERE user_id = ? AND project_name = ?",
                     (datetime.now().isoformat(), user_id, project_name))
        conn.commit()
        conn.close()
        
        monitor_thread = threading.Thread(target=monitor_single_project, args=(user_id, project_name, process))
        monitor_thread.daemon = True
        monitor_thread.start()
        
        log_activity(user_id, "start", project_name, "Started successfully")
        return True
        
    except Exception as e:
        error_msg = str(e)
        user_errors = get_user_errors(user_id)
        user_errors[project_name] = error_msg
        return False

def stop_project(user_id, project_name):
    user_running = get_user_running_projects(user_id)
    
    if project_name in user_running:
        try:
            project_info = user_running[project_name]
            process = project_info["process"] if isinstance(project_info, dict) else project_info
            
            process.terminate()
            
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            
            del user_running[project_name]
            
            user_dir = get_user_dir(user_id)
            project_path = os.path.join(user_dir, project_name)
            log_file = os.path.join(project_path, "project.log")
            if os.path.exists(log_file):
                with open(log_file, 'a') as f:
                    f.write(f"[STOPPED] at {datetime.now()}\n")
            
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE projects SET last_stopped = ? WHERE user_id = ? AND project_name = ?",
                         (datetime.now().isoformat(), user_id, project_name))
            conn.commit()
            conn.close()
            
            log_activity(user_id, "stop", project_name, "Stopped successfully")
            return True
            
        except Exception as e:
            if project_name in user_running:
                del user_running[project_name]
            return False
    return False

def monitor_single_project(user_id, project_name, process):
    try:
        process.wait()
        
        user_running = get_user_running_projects(user_id)
        if project_name in user_running:
            del user_running[project_name]
            user_errors = get_user_errors(user_id)
            user_errors[project_name] = f"Process stopped at {datetime.now().strftime('%H:%M:%S')}"
            
            # Auto-restart if enabled
            if get_auto_restart_status(user_id, project_name):
                time.sleep(5)
                start_project(user_id, project_name)
                send_notification(user_id, f"🔄 Project '{project_name}' was auto-restarted after crash.")
            
    except Exception as e:
        logger.error(f"Monitor error for {project_name}: {e}")

def delete_project(user_id, project_name):
    user_running = get_user_running_projects(user_id)
    
    if project_name in user_running:
        stop_project(user_id, project_name)
    
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
    
    user_errors = get_user_errors(user_id)
    if project_name in user_errors:
        del user_errors[project_name]
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET total_deletes = total_deletes + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    log_activity(user_id, "delete", project_name, "Deleted")

@bot.message_handler(func=lambda m: m.text == "▶️ Start")
def start_project_menu(msg):
    user_id = msg.chat.id
    projects = get_user_projects(user_id)
    user_running = get_user_running_projects(user_id)
    
    if not projects:
        bot.send_message(msg.chat.id, "❌ *No projects found to start*", parse_mode="Markdown")
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for project in projects:
        if project not in user_running:
            markup.add(InlineKeyboardButton(f"▶️ {project}", callback_data=f"start_{project}"))
    
    if not markup.keyboard:
        bot.send_message(msg.chat.id, f"✅ *All your projects are already running!*", parse_mode="Markdown")
    else:
        bot.send_message(msg.chat.id, "🚀 *Select project to start:*", parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "⏹️ Stop")
def stop_project_menu(msg):
    user_id = msg.chat.id
    user_running = get_user_running_projects(user_id)
    
    if not user_running:
        bot.send_message(msg.chat.id, "⚪ *No projects are currently running*", parse_mode="Markdown")
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for project in user_running.keys():
        markup.add(InlineKeyboardButton(f"⏹️ {project}", callback_data=f"stop_{project}"))
    
    bot.send_message(msg.chat.id, "🛑 *Select project to stop:*", parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🔄 Restart")
def restart_project_menu(msg):
    user_id = msg.chat.id
    projects = get_user_projects(user_id)
    
    if not projects:
        bot.send_message(msg.chat.id, "❌ *No projects found to restart*", parse_mode="Markdown")
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for project in projects:
        markup.add(InlineKeyboardButton(f"🔄 {project}", callback_data=f"restart_{project}"))
    
    bot.send_message(msg.chat.id, "🔄 *Select project to restart:*", parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🗑️ Delete")
def delete_project_menu(msg):
    user_id = msg.chat.id
    projects = get_user_projects(user_id)
    
    if not projects:
        bot.send_message(msg.chat.id, "📂 *No projects to delete*", parse_mode="Markdown")
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for project in projects:
        markup.add(InlineKeyboardButton(f"🗑️ {project}", callback_data=f"delete_{project}"))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete"))
    
    bot.send_message(msg.chat.id, "⚠️ *Select project to delete (IRREVERSIBLE):*", 
                     parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🗑️ Delete All")
def delete_all(msg):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ YES, Delete All", callback_data="confirm_delete_all"),
        InlineKeyboardButton("❌ NO, Cancel", callback_data="cancel_delete")
    )
    bot.send_message(msg.chat.id, "⚠️ *WARNING: This will delete ALL your projects!*\nAre you sure?", 
                     parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📊 Stats")
def server_info(msg):
    user_id = msg.chat.id
    total_projects = len(get_user_projects(user_id))
    running_count = len(get_user_running_projects(user_id))
    user_errors = get_user_errors(user_id)
    error_count = len(user_errors)
    
    analytics = get_user_analytics(user_id)
    
    stats_text = f"""
📊 *YOUR STATISTICS*
━━━━━━━━━━━━━━━━━━━━━━

📦 *PROJECTS*
├─ Total: {total_projects}
├─ Running: {running_count} 🟢
├─ Stopped: {total_projects - running_count} ⚪
└─ Errors: {error_count} ⚠️

📈 *ACTIVITY*
├─ Total Runs: {analytics['total_runs']}
└─ Uptime: {analytics['total_uptime_hours']} hours

👤 *USER INFO*
├─ User ID: `{user_id}`
└─ Workspace: Private

🕐 *Server Time*
└─ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

💻 *Powered by @Hexh4ckerOFC*
    """
    bot.send_message(msg.chat.id, stats_text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔄 Refresh")
def refresh_status(msg):
    user_id = msg.chat.id
    user_running = get_user_running_projects(user_id)
    dead_projects = []
    
    for project, info in list(user_running.items()):
        process = info["process"] if isinstance(info, dict) else info
        if process.poll() is not None:
            dead_projects.append(project)
            del user_running[project]
            user_errors = get_user_errors(user_id)
            user_errors[project] = f"⚠️ Process died at {datetime.now().strftime('%H:%M:%S')}"
    
    if dead_projects:
        bot.send_message(msg.chat.id, f"⚠️ *Detected dead processes:*\n{', '.join(dead_projects)}\n\nUse ▶️ Start to restart them.", 
                         parse_mode="Markdown")
    else:
        running_count = len(user_running)
        bot.send_message(msg.chat.id, f"✅ *Status Refreshed* | 🟢 Running: {running_count}", 
                         parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📝 Errors")
def view_errors(msg):
    user_id = msg.chat.id
    user_errors = get_user_errors(user_id)
    
    if not user_errors:
        bot.send_message(msg.chat.id, "✅ *No errors logged! All projects running smoothly.*", parse_mode="Markdown")
        return
    
    error_text = f"⚠️ *ERROR LOG*\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for project, error in user_errors.items():
        error_text += f"\n📁 `{project}`\n└─ {error[:100]}\n"
    
    if len(error_text) > 4000:
        error_text = error_text[:4000] + "\n... (truncated)"
    
    error_text += f"\n💻 *Powered by @Hexh4ckerOFC*"
    bot.send_message(msg.chat.id, error_text, parse_mode="Markdown")

# ============== ADDITIONAL CALLBACK HANDLERS ==============

@bot.callback_query_handler(func=lambda call: call.data.startswith("start_") or call.data.startswith("stop_") or 
                                          call.data.startswith("restart_") or call.data.startswith("delete_"))
def handle_project_actions(call):
    user_id = call.message.chat.id
    
    if call.data.startswith("start_"):
        project_name = call.data.replace("start_", "")
        result = start_project(user_id, project_name)
        if result:
            bot.edit_message_text(f"✅ *'{project_name}' started successfully!*", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text(f"❌ *Failed to start '{project_name}'*\nCheck if main.py exists!", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data.startswith("stop_"):
        project_name = call.data.replace("stop_", "")
        if project_name in get_user_running_projects(user_id):
            stop_project(user_id, project_name)
            bot.edit_message_text(f"⏹️ *'{project_name}' stopped successfully*", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text(f"⚠️ *'{project_name}' is not running*", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data.startswith("restart_"):
        project_name = call.data.replace("restart_", "")
        bot.edit_message_text(f"🔄 *Restarting '{project_name}'...*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
        if project_name in get_user_running_projects(user_id):
            stop_project(user_id, project_name)
            time.sleep(2)
        
        result = start_project(user_id, project_name)
        if result:
            bot.send_message(call.message.chat.id, f"✅ *'{project_name}' restarted successfully!*", parse_mode="Markdown")
        else:
            bot.send_message(call.message.chat.id, f"❌ *Failed to restart '{project_name}'*", parse_mode="Markdown")
    
    elif call.data.startswith("delete_"):
        project_name = call.data.replace("delete_", "")
        delete_project(user_id, project_name)
        bot.edit_message_text(f"🗑️ *Project '{project_name}' deleted*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    bot.answer_callback_query(call.id)

# ============== MONITORING THREAD ==============

def monitor_processes():
    while True:
        time.sleep(30)
        for user_id, user_projects in list(running_projects.items()):
            for project_name, info in list(user_projects.items()):
                process = info["process"] if isinstance(info, dict) else info
                if process.poll() is not None:
                    del running_projects[user_id][project_name]
                    if user_id not in project_errors:
                        project_errors[user_id] = {}
                    project_errors[user_id][project_name] = f"⚠️ Crashed at {datetime.now().strftime('%H:%M:%S')}"
                    
                    # Auto-restart if enabled
                    if get_auto_restart_status(user_id, project_name):
                        time.sleep(5)
                        start_project(user_id, project_name)
                        send_notification(user_id, f"🔄 Project '{project_name}' was auto-restarted after crash.")
                    
                    logger.info(f"⚠️ User {user_id} project '{project_name}' crashed")

# Start monitoring threads
monitor_thread = threading.Thread(target=monitor_processes, daemon=True)
monitor_thread.start()

resource_monitor_thread = threading.Thread(target=monitor_resource_usage, daemon=True)
resource_monitor_thread.start()

# ============== ADMIN PANEL (SIMPLIFIED) ==============

@bot.message_handler(func=lambda m: m.text == "👑 Admin Panel")
def admin_panel(msg):
    if msg.chat.id != ADMIN_ID:
        bot.send_message(msg.chat.id, "⛔ *Access Denied!*", parse_mode="Markdown")
        return
    
    conn = sqlite3.connect(DB_PATH)
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    total_running = len(running_projects)
    total_tickets = conn.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'open'").fetchone()[0]
    conn.close()
    
    uptime = datetime.now() - admin_stats["bot_start_time"]
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    admin_text = f"""
👑 *ADMIN PANEL*
━━━━━━━━━━━━━━━━━━━━━━

📊 *STATISTICS*
├─ 👥 Users: {total_users}
├─ 📦 Projects: {total_projects}
├─ 🟢 Running: {total_running}
├─ 🎫 Open Tickets: {total_tickets}
└─ ⏱️ Uptime: {hours}h {minutes}m

📈 *PERFORMANCE*
├─ Backups: {admin_stats['total_backups']}
├─ Restores: {admin_stats['total_restores']}
└─ API Calls: {admin_stats['total_api_calls']}

💻 *Powered by @Hexh4ckerOFC*
    """
    
    bot.send_message(msg.chat.id, admin_text, parse_mode="Markdown")

# ============== BOT STARTUP ==============

def generate_referral_code(user_id):
    return hashlib.md5(f"{user_id}{datetime.now()}".encode()).hexdigest()[:8]

print("="*50)
print("🔥 PYTHON HOSTING PANEL v3.0 - READY")
print("="*50)
print("✅ Bot Running Successfully!")
print(f"📁 Base Directory: {BASE_DIR}")
print(f"👥 Multi-User Support: ENABLED")
print(f"🔒 Private Workspaces: YES")
print(f"📋 30+ Features Loaded:")
print("   • Templates System")
print("   • Git Integration")
print("   • File Manager")
print("   • Backup/Restore")
print("   • Auto-Restart")
print("   • Scheduled Tasks")
print("   • Webhooks")
print("   • Dependency Manager")
print("   • Environment Variables")
print("   • Batch Operations")
print("   • Project Cloning")
print("   • Analytics Dashboard")
print("   • And more...")
print(f"👑 Admin ID: {ADMIN_ID}")
print(f"💬 Support: @Hexh4ckerOFC")
print("="*50)

bot.infinity_polling()