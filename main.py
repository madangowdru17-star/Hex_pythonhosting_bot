import telebot
import os
import zipfile
import subprocess
import shutil
import time
import threading
import signal
import sys
from datetime import datetime, timedelta
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import requests
import json
import re

BOT_TOKEN = "8389147569:AAGF2RxBRe8AiaW0_wN4rooJ5WF06zYtMho"

# Admin Configuration
ADMIN_ID = 7643981409

bot = telebot.TeleBot(BOT_TOKEN)

BASE_DIR = "projects"
os.makedirs(BASE_DIR, exist_ok=True)

# Store running processes per user
running_projects = {}
project_errors = {}

# Monthly user tracking with leaderboard
monthly_stats = {
    "current_month": datetime.now().strftime("%Y-%m"),
    "users": {},  # {user_id: {"first_seen": date, "last_active": date, "commands_used": 0, "projects_deployed": 0, "username": ""}}
    "total_commands": 0,
    "total_projects_deployed": 0
}

# Load monthly stats from file
STATS_FILE = "monthly_stats.json"

def load_monthly_stats():
    global monthly_stats
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r') as f:
                loaded = json.load(f)
                current_month = datetime.now().strftime("%Y-%m")
                if loaded.get("current_month") == current_month:
                    monthly_stats.update(loaded)
                else:
                    # New month, reset stats but keep previous month data
                    old_month = loaded.get("current_month")
                    if old_month:
                        # Save previous month to archive
                        archive_file = f"monthly_stats_{old_month}.json"
                        with open(archive_file, 'w') as af:
                            json.dump(loaded, af, indent=2)
                    
                    monthly_stats = {
                        "current_month": current_month,
                        "users": {},
                        "total_commands": 0,
                        "total_projects_deployed": 0
                    }
        except Exception as e:
            print(f"Error loading stats: {e}")

def save_monthly_stats():
    try:
        with open(STATS_FILE, 'w') as f:
            json.dump(monthly_stats, f, indent=2)
    except Exception as e:
        print(f"Error saving stats: {e}")

def update_user_stats(user_id, command_used=True, project_deployed=False, username=None):
    """Update user statistics for monthly tracking"""
    current_month = datetime.now().strftime("%Y-%m")
    
    if monthly_stats["current_month"] != current_month:
        # Reset for new month
        old_month = monthly_stats["current_month"]
        if old_month and monthly_stats["users"]:
            archive_file = f"monthly_stats_{old_month}.json"
            with open(archive_file, 'w') as af:
                json.dump(monthly_stats, af, indent=2)
        
        monthly_stats["current_month"] = current_month
        monthly_stats["users"] = {}
        monthly_stats["total_commands"] = 0
        monthly_stats["total_projects_deployed"] = 0
    
    user_id_str = str(user_id)
    
    # Get username if not provided
    if not username:
        try:
            user = bot.get_chat(user_id)
            username = user.username or user.first_name or str(user_id)
        except:
            username = str(user_id)
    
    if user_id_str not in monthly_stats["users"]:
        monthly_stats["users"][user_id_str] = {
            "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "commands_used": 0,
            "projects_deployed": 0,
            "username": username[:30]
        }
    else:
        monthly_stats["users"][user_id_str]["username"] = username[:30]
    
    if command_used:
        monthly_stats["users"][user_id_str]["commands_used"] += 1
        monthly_stats["total_commands"] += 1
    
    if project_deployed:
        monthly_stats["users"][user_id_str]["projects_deployed"] += 1
        monthly_stats["total_projects_deployed"] += 1
    
    monthly_stats["users"][user_id_str]["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_monthly_stats()

def get_top_users(limit=10, sort_by="commands"):
    """Get top users leaderboard"""
    users_list = []
    for user_id, stats in monthly_stats["users"].items():
        users_list.append({
            "user_id": user_id,
            "username": stats.get("username", user_id[:8]),
            "commands": stats.get("commands_used", 0),
            "projects": stats.get("projects_deployed", 0),
            "last_active": stats.get("last_active", "")
        })
    
    if sort_by == "commands":
        users_list.sort(key=lambda x: x["commands"], reverse=True)
    elif sort_by == "projects":
        users_list.sort(key=lambda x: x["projects"], reverse=True)
    
    return users_list[:limit]

# Auto-delete message handler for ALL messages
class AutoDeleteBot(telebot.TeleBot):
    def send_message(self, chat_id, text, *args, **kwargs):
        # Default delay for all messages
        if 'reply_markup' not in kwargs or kwargs.get('reply_markup') is None:
            # For regular messages without buttons, delete after 30 seconds
            msg = super().send_message(chat_id, text, *args, **kwargs)
            
            def delete_later():
                time.sleep(30)
                try:
                    super().delete_message(chat_id, msg.message_id)
                except:
                    pass
            
            threading.Thread(target=delete_later, daemon=True).start()
            return msg
        else:
            # For messages with buttons, delete after 60 seconds (give time to interact)
            msg = super().send_message(chat_id, text, *args, **kwargs)
            
            def delete_later():
                time.sleep(60)
                try:
                    super().delete_message(chat_id, msg.message_id)
                except:
                    pass
            
            threading.Thread(target=delete_later, daemon=True).start()
            return msg

# Replace bot with auto-delete version
original_bot = bot
bot = AutoDeleteBot(BOT_TOKEN)

def safe_send_message(chat_id, text, delay=30, reply_markup=None, parse_mode=None):
    """Safely send message with auto-delete"""
    try:
        msg = bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
        
        # Auto-delete after delay
        def delete_later():
            time.sleep(delay)
            try:
                bot.delete_message(chat_id, msg.message_id)
            except:
                pass
        
        threading.Thread(target=delete_later, daemon=True).start()
        return msg
    except Exception as e:
        plain_text = re.sub(r'[*_`~]', '', text)
        msg = bot.send_message(chat_id, plain_text, reply_markup=reply_markup)
        
        def delete_later():
            time.sleep(delay)
            try:
                bot.delete_message(chat_id, msg.message_id)
            except:
                pass
        
        threading.Thread(target=delete_later, daemon=True).start()
        return msg

# ============== SIMPLE UI ==============

def get_main_keyboard(user_id):
    is_admin = (user_id == ADMIN_ID)
    
    if is_admin:
        markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        buttons = [
            "📦 Upload Project", "🐙 GitHub Deploy",
            "📁 My Projects", "▶️ Start", "⏹️ Stop",
            "🔄 Restart", "🗑️ Delete", "🗑️ Delete All",
            "📊 Stats", "🔄 Refresh", "📝 Errors",
            "⚙️ Env Vars", "🏆 Top Users", "👑 Admin Panel", "❓ Help"
        ]
        markup.add(*buttons)
        return markup
    else:
        markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        buttons = [
            "📦 Upload", "🐙 GitHub Deploy", "📁 Projects",
            "▶️ Start", "⏹️ Stop", "🔄 Restart", "🗑️ Delete",
            "🗑️ Delete All", "📊 Stats", "🔄 Refresh",
            "📝 Errors", "⚙️ Env Vars", "🏆 Top Users", "❓ Help"
        ]
        markup.add(*buttons)
        return markup

def get_admin_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("👥 All Users", callback_data="admin_users"),
        InlineKeyboardButton("📦 All Projects", callback_data="admin_projects"),
        InlineKeyboardButton("🟢 Running Projects", callback_data="admin_running"),
        InlineKeyboardButton("⚠️ Error Logs", callback_data="admin_errors"),
        InlineKeyboardButton("💾 Server Stats", callback_data="admin_server"),
        InlineKeyboardButton("📊 Bot Stats", callback_data="admin_botstats"),
        InlineKeyboardButton("🏆 Top Users", callback_data="admin_top_users"),
        InlineKeyboardButton("🗑️ Clean Orphaned", callback_data="admin_clean"),
        InlineKeyboardButton("🔄 Broadcast", callback_data="admin_broadcast"),
        InlineKeyboardButton("❌ Close", callback_data="admin_close")
    )
    return markup

# ============== TOP USERS LEADERBOARD ==============

@bot.message_handler(func=lambda m: m.text == "🏆 Top Users")
def top_users_command(msg):
    user_id = msg.chat.id
    update_user_stats(user_id, command_used=True)
    
    # Get top users by commands
    top_by_commands = get_top_users(10, "commands")
    top_by_projects = get_top_users(10, "projects")
    
    current_month = datetime.now().strftime("%B %Y")
    
    # Build leaderboard text
    leaderboard_text = f"🏆 *TOP USERS - {current_month}*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    leaderboard_text += "📊 *Most Active (Commands)*\n"
    if top_by_commands:
        for i, user in enumerate(top_by_commands, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            leaderboard_text += f"{medal} `{user['username'][:15]}` - {user['commands']} commands\n"
    else:
        leaderboard_text += "No data yet\n"
    
    leaderboard_text += "\n🚀 *Top Deployers (Projects)*\n"
    if top_by_projects:
        for i, user in enumerate(top_by_projects, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            leaderboard_text += f"{medal} `{user['username'][:15]}` - {user['projects']} projects\n"
    else:
        leaderboard_text += "No data yet\n"
    
    # Add your rank
    user_id_str = str(user_id)
    user_stats = monthly_stats["users"].get(user_id_str, {})
    user_commands = user_stats.get("commands_used", 0)
    user_projects = user_stats.get("projects_deployed", 0)
    
    # Calculate rank
    all_users_by_cmd = list(monthly_stats["users"].items())
    all_users_by_cmd.sort(key=lambda x: x[1].get("commands_used", 0), reverse=True)
    
    rank = 1
    for i, (uid, stats) in enumerate(all_users_by_cmd, 1):
        if uid == user_id_str:
            rank = i
            break
    
    total_users = len(monthly_stats["users"])
    
    leaderboard_text += f"\n👤 *Your Stats*\n"
    leaderboard_text += f"├─ Rank: #{rank} / {total_users}\n"
    leaderboard_text += f"├─ Commands: {user_commands}\n"
    leaderboard_text += f"└─ Projects: {user_projects}\n"
    
    leaderboard_text += f"\n📅 *Global Stats*\n"
    leaderboard_text += f"├─ Total Users: {total_users}\n"
    leaderboard_text += f"├─ Total Commands: {monthly_stats['total_commands']}\n"
    leaderboard_text += f"└─ Total Projects: {monthly_stats['total_projects_deployed']}\n"
    
    leaderboard_text += f"\n💡 *Stats reset on the 1st of each month*\n"
    leaderboard_text += f"💻 *Powered by @Hexh4ckerOFC*"
    
    safe_send_message(msg.chat.id, leaderboard_text, parse_mode="Markdown", delay=60)

# ============== ENHANCED GITHUB INTEGRATION ==============

def find_entry_point(project_path):
    """Find the main entry point file"""
    entry_points = [
        "main.py", "app.py", "bot.py", "run.py", "server.py",
        "application.py", "wsgi.py", "manage.py", "index.py",
        "start.py", "backend.py", "api.py", "web.py"
    ]
    
    for entry in entry_points:
        entry_path = os.path.join(project_path, entry)
        if os.path.exists(entry_path):
            return entry_path, entry
    
    py_files = []
    for file in os.listdir(project_path):
        if file.endswith('.py') and file not in ['setup.py', 'requirements.py', '__init__.py', 'test_']:
            file_path = os.path.join(project_path, file)
            if os.path.getsize(file_path) > 100:
                py_files.append(file)
    
    if py_files:
        py_files.sort(key=lambda x: (
            0 if 'main' in x.lower() else 
            1 if 'app' in x.lower() else 
            2 if 'run' in x.lower() else 3
        ))
        return os.path.join(project_path, py_files[0]), py_files[0]
    
    return None, None

def get_project_type(project_path):
    """Detect project type"""
    files = os.listdir(project_path)
    
    if 'requirements.txt' in files:
        with open(os.path.join(project_path, 'requirements.txt'), 'r') as f:
            content = f.read().lower()
            if 'django' in content:
                return 'Django', 'python manage.py runserver 0.0.0.0:8000'
            elif 'flask' in content:
                return 'Flask', 'python app.py'
            elif 'fastapi' in content:
                return 'FastAPI', 'uvicorn main:app --host 0.0.0.0 --port 8000'
            elif 'discord' in content:
                return 'Discord Bot', 'python bot.py'
            elif 'telegram' in content or 'pytelegram' in content:
                return 'Telegram Bot', 'python bot.py'
    
    if 'package.json' in files:
        return 'Node.js', 'npm start'
    
    return 'Python Script', 'python {entry_point}'

@bot.message_handler(func=lambda m: m.text == "🐙 GitHub Deploy")
def github_deploy_menu(msg):
    update_user_stats(msg.chat.id, command_used=True)
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📦 Deploy from GitHub URL", callback_data="github_url"),
        InlineKeyboardButton("📋 My GitHub Projects", callback_data="github_my")
    )
    safe_send_message(msg.chat.id, "🐙 GitHub Deployment\n\nChoose deployment method:", reply_markup=markup, delay=60)

@bot.callback_query_handler(func=lambda call: call.data == "github_url")
def handle_github_url(call):
    bot.edit_message_text("🔗 Enter GitHub Repository URL\n\nExample: https://github.com/username/repo\n\nSend /cancel to cancel",
                        call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(call.message, process_github_download)

@bot.callback_query_handler(func=lambda call: call.data == "github_my")
def show_github_projects(call):
    user_id = call.message.chat.id
    user_dir = get_user_dir(user_id)
    github_projects = []
    
    for project in os.listdir(user_dir):
        if project.startswith("github_"):
            github_projects.append(project)
    
    if not github_projects:
        bot.edit_message_text("📭 No GitHub projects found\n\nUse GitHub Deploy to add one.",
                            call.message.chat.id, call.message.message_id)
        return
    
    text = "🐙 YOUR GITHUB PROJECTS\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for proj in github_projects:
        is_running = proj in get_user_running_projects(user_id)
        status = "🟢 Running" if is_running else "⚪ Stopped"
        text += f"\n📁 {proj}\n└─ Status: {status}\n"
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id)

def process_github_download(msg):
    if msg.text == "/cancel":
        safe_send_message(msg.chat.id, "❌ Cancelled.", reply_markup=get_main_keyboard(msg.chat.id), delay=30)
        return
    
    url = msg.text.strip()
    
    if "github.com" in url:
        parts = url.replace("https://", "").replace("http://", "").replace("github.com/", "").split('/')
        if len(parts) >= 2:
            username = parts[0]
            repo = parts[1].replace(".git", "")
            download_url = f"https://github.com/{username}/{repo}/archive/refs/heads/main.zip"
            
            status_msg = safe_send_message(msg.chat.id, f"⏳ Downloading {repo} from GitHub...")
            
            try:
                response = requests.get(download_url, timeout=30)
                
                if response.status_code == 404:
                    download_url = f"https://github.com/{username}/{repo}/archive/refs/heads/master.zip"
                    response = requests.get(download_url, timeout=30)
                
                if response.status_code == 200:
                    user_id = msg.chat.id
                    project_name = f"github_{repo}_{int(time.time())}"
                    user_dir = get_user_dir(user_id)
                    zip_path = os.path.join(user_dir, f"{project_name}.zip")
                    
                    with open(zip_path, 'wb') as f:
                        f.write(response.content)
                    
                    extract_path = os.path.join(user_dir, project_name)
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
                    
                    bot.edit_message_text("📦 Extracted!", msg.chat.id, status_msg.message_id)
                    
                    entry_path, entry_file = find_entry_point(extract_path)
                    
                    if not entry_path:
                        bot.edit_message_text(f"⚠️ No Python entry file found!",
                                            msg.chat.id, status_msg.message_id)
                        return
                    
                    main_path = os.path.join(extract_path, "main.py")
                    if entry_path != main_path:
                        shutil.move(entry_path, main_path)
                        bot.edit_message_text(f"📝 Detected entry point: {entry_file} → renamed to main.py",
                                            msg.chat.id, status_msg.message_id)
                    
                    project_type, _ = get_project_type(extract_path)
                    bot.edit_message_text(f"🔍 Detected project type: {project_type}",
                                        msg.chat.id, status_msg.message_id)
                    
                    req_file = os.path.join(extract_path, "requirements.txt")
                    if os.path.exists(req_file):
                        bot.edit_message_text("📥 Installing requirements...", msg.chat.id, status_msg.message_id)
                        subprocess.Popen(["pip", "install", "-r", req_file], cwd=extract_path,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    
                    size = get_folder_size(extract_path)
                    
                    update_user_stats(user_id, project_deployed=True)
                    
                    markup = InlineKeyboardMarkup()
                    markup.add(
                        InlineKeyboardButton("▶️ Start Now", callback_data=f"start_{project_name}"),
                        InlineKeyboardButton("⚙️ Set Env Vars", callback_data=f"env_{project_name}")
                    )
                    
                    bot.edit_message_text(
                        f"✅ GitHub Project Deployed!\n\n"
                        f"📁 Name: {project_name}\n"
                        f"📦 Size: {size}\n"
                        f"📄 Entry: {entry_file} → main.py\n"
                        f"🔧 Type: {project_type}\n"
                        f"🐙 Repo: {url}\n\n"
                        f"Click below to start:",
                        msg.chat.id, status_msg.message_id, reply_markup=markup)
                else:
                    bot.edit_message_text(f"❌ Failed to download repository\nStatus: {response.status_code}", 
                                        msg.chat.id, status_msg.message_id)
            except Exception as e:
                bot.edit_message_text(f"❌ Error: {str(e)[:100]}", msg.chat.id, status_msg.message_id)
        else:
            safe_send_message(msg.chat.id, "❌ Invalid GitHub URL", delay=30)
    else:
        safe_send_message(msg.chat.id, "❌ Please provide a valid GitHub URL", delay=30)

# ============== ENVIRONMENT VARIABLES ==============

@bot.message_handler(func=lambda m: m.text == "⚙️ Env Vars")
def env_vars_menu(msg):
    user_id = msg.chat.id
    update_user_stats(user_id, command_used=True)
    projects = get_user_projects(user_id)
    
    if not projects:
        safe_send_message(msg.chat.id, "📂 No projects found", delay=30)
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for project in projects:
        markup.add(InlineKeyboardButton(f"⚙️ {project}", callback_data=f"env_{project}"))
    
    safe_send_message(msg.chat.id, "⚙️ Select project to configure environment variables:",
                     reply_markup=markup, delay=60)

@bot.callback_query_handler(func=lambda call: call.data.startswith("env_"))
def handle_env_vars(call):
    user_id = call.message.chat.id
    project_name = call.data.replace("env_", "")
    
    if user_id not in project_env_vars:
        project_env_vars[user_id] = {}
    if project_name not in project_env_vars[user_id]:
        project_env_vars[user_id][project_name] = {}
    
    current_vars = project_env_vars[user_id][project_name]
    
    text = f"⚙️ Environment Variables for {project_name}\n\n"
    if current_vars:
        text += "📋 Current Variables:\n"
        for key, value in current_vars.items():
            text += f"├─ {key} = {value[:20]}\n"
    else:
        text += "📭 No environment variables set\n"
    
    text += "\n🔧 Actions:"
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Add Variable", callback_data=f"env_add_{project_name}"),
        InlineKeyboardButton("🗑️ Remove Variable", callback_data=f"env_remove_{project_name}"),
        InlineKeyboardButton("📋 List All", callback_data=f"env_list_{project_name}"),
        InlineKeyboardButton("🔙 Back", callback_data="env_back")
    )
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("env_add_"))
def env_add_var(call):
    project_name = call.data.replace("env_add_", "")
    bot.edit_message_text(f"📝 Add Environment Variable for {project_name}\n\n"
                         f"Send in format: KEY=value\n\nExample: PORT=8080\n\nSend /cancel to cancel",
                         call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(call.message, process_env_add, project_name)

def process_env_add(msg, project_name):
    if msg.text == "/cancel":
        safe_send_message(msg.chat.id, "❌ Cancelled.", reply_markup=get_main_keyboard(msg.chat.id), delay=30)
        return
    
    user_id = msg.chat.id
    
    try:
        if '=' not in msg.text:
            raise ValueError("No equals sign found")
            
        key, value = msg.text.split('=', 1)
        key = key.strip().upper()
        value = value.strip()
        
        if not key or not value:
            raise ValueError("Empty key or value")
        
        if user_id not in project_env_vars:
            project_env_vars[user_id] = {}
        if project_name not in project_env_vars[user_id]:
            project_env_vars[user_id][project_name] = {}
        
        project_env_vars[user_id][project_name][key] = value
        
        project_path = os.path.join(get_user_dir(user_id), project_name)
        env_file = os.path.join(project_path, ".env")
        
        with open(env_file, 'w') as f:
            for k, v in project_env_vars[user_id][project_name].items():
                f.write(f"{k}={v}\n")
        
        safe_send_message(msg.chat.id, f"✅ Variable added: {key}={value[:30]}", delay=30)
        
        if project_name in get_user_running_projects(user_id):
            stop_project(user_id, project_name)
            time.sleep(1)
            start_project(user_id, project_name)
            safe_send_message(msg.chat.id, f"🔄 Project {project_name} restarted to apply changes", delay=30)
        
    except Exception as e:
        safe_send_message(msg.chat.id, f"❌ Invalid format! Use KEY=value\nError: {str(e)}", delay=30)

@bot.callback_query_handler(func=lambda call: call.data.startswith("env_remove_"))
def env_remove_var(call):
    project_name = call.data.replace("env_remove_", "")
    user_id = call.message.chat.id
    
    if user_id in project_env_vars and project_name in project_env_vars[user_id]:
        vars_list = project_env_vars[user_id][project_name]
        
        if not vars_list:
            bot.answer_callback_query(call.id, "No variables to remove")
            return
        
        markup = InlineKeyboardMarkup(row_width=1)
        for key in vars_list.keys():
            markup.add(InlineKeyboardButton(f"🗑️ {key}", callback_data=f"env_del_{project_name}_{key}"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data=f"env_{project_name}"))
        
        bot.edit_message_text(f"🗑️ Select variable to remove from {project_name}:",
                            call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("env_del_"))
def env_delete_var(call):
    parts = call.data.replace("env_del_", "").split('_', 1)
    project_name = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    
    user_id = call.message.chat.id
    
    if user_id in project_env_vars and project_name in project_env_vars[user_id]:
        if key in project_env_vars[user_id][project_name]:
            del project_env_vars[user_id][project_name][key]
            
            project_path = os.path.join(get_user_dir(user_id), project_name)
            env_file = os.path.join(project_path, ".env")
            
            if project_env_vars[user_id][project_name]:
                with open(env_file, 'w') as f:
                    for k, v in project_env_vars[user_id][project_name].items():
                        f.write(f"{k}={v}\n")
            elif os.path.exists(env_file):
                os.remove(env_file)
            
            bot.answer_callback_query(call.id, f"Removed {key}")
            bot.edit_message_text(f"✅ Removed variable: {key}",
                                call.message.chat.id, call.message.message_id)
            
            if project_name in get_user_running_projects(user_id):
                stop_project(user_id, project_name)
                time.sleep(1)
                start_project(user_id, project_name)

@bot.callback_query_handler(func=lambda call: call.data.startswith("env_list_"))
def env_list_vars(call):
    project_name = call.data.replace("env_list_", "")
    user_id = call.message.chat.id
    
    if user_id in project_env_vars and project_name in project_env_vars[user_id]:
        vars_dict = project_env_vars[user_id][project_name]
        
        if vars_dict:
            text = f"📋 Environment Variables for {project_name}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for key, value in vars_dict.items():
                text += f"🔑 {key}\n└─ {value[:50]}\n\n"
            
            if len(text) > 4000:
                text = text[:4000] + "\n... (truncated)"
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Back", callback_data=f"env_{project_name}"))
            
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "No variables set")

@bot.callback_query_handler(func=lambda call: call.data == "env_back")
def env_back(call):
    env_vars_menu(call.message)

# Store environment variables
project_env_vars = {}

# Admin statistics
admin_stats = {
    "total_users": 0,
    "total_projects": 0,
    "total_running": 0,
    "bot_start_time": datetime.now()
}

# ============== START COMMAND ==============

@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.chat.id
    username = msg.from_user.username or msg.from_user.first_name
    update_user_stats(user_id, command_used=True, username=username)
    is_admin = (user_id == ADMIN_ID)
    total_projects = len(get_user_projects(user_id))
    
    # Get user rank
    all_users = list(monthly_stats["users"].items())
    all_users.sort(key=lambda x: x[1].get("commands_used", 0), reverse=True)
    rank = 1
    for i, (uid, stats) in enumerate(all_users, 1):
        if uid == str(user_id):
            rank = i
            break
    
    welcome_text = f"""
🔥 WELCOME TO PYTHON HOSTING

✨ Hex Python Hosting Panel v3.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ User-Specific Workspaces
✅ GitHub Repository Deploy
✅ Auto-Detect Entry Points
✅ Environment Variables Support
✅ Monthly Statistics & Leaderboard
✅ Auto-Delete Messages (30 sec)
✅ 24/7 Project Hosting

👤 Your Workspace:
├─ User ID: {user_id}
├─ Projects: {total_projects}
├─ Running: {len(get_user_running_projects(user_id))}
├─ Monthly Rank: #{rank}
└─ Role: {'👑 ADMIN' if is_admin else '👤 USER'}

🏆 *Check your monthly ranking with '🏆 Top Users'*

💡 Need Help? @Hexh4ckerOFC

💻 Powered by @Hexh4ckerOFC
    """
    
    safe_send_message(msg.chat.id, welcome_text, reply_markup=get_main_keyboard(user_id), delay=60)
    
    if is_admin:
        update_admin_stats()
        uptime = datetime.now() - admin_stats["bot_start_time"]
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        admin_notice = f"""
👑 ADMIN PANEL LOADED

📊 Quick Stats:
├─ Total Users: {admin_stats['total_users']}
├─ Total Projects: {admin_stats['total_projects']}
├─ Running: {admin_stats['total_running']}
└─ Uptime: {hours}h {minutes}m

Use the Admin Panel button for full control.

💻 Powered by @Hexh4ckerOFC
        """
        safe_send_message(msg.chat.id, admin_notice, delay=60)

# ============== ADMIN PANEL HANDLER ==============

@bot.message_handler(func=lambda m: m.text == "👑 Admin Panel")
def admin_panel(msg):
    if msg.chat.id != ADMIN_ID:
        safe_send_message(msg.chat.id, "⛔ Access Denied!", delay=30)
        return
    
    update_admin_stats()
    uptime = datetime.now() - admin_stats["bot_start_time"]
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    admin_text = f"""
👑 ADMIN CONTROL PANEL

📈 SYSTEM STATISTICS
├─ 👥 Total Users: {admin_stats['total_users']}
├─ 📦 Total Projects: {admin_stats['total_projects']}
├─ 🟢 Running: {admin_stats['total_running']}
├─ ⚪ Stopped: {admin_stats['total_projects'] - admin_stats['total_running']}
└─ ⏱️ Uptime: {hours}h {minutes}m

🎛️ CONTROLS
└─ Use the buttons below to manage the system

💻 Powered by @Hexh4ckerOFC
    """
    
    safe_send_message(msg.chat.id, admin_text, reply_markup=get_admin_keyboard())

# ============== ADMIN CALLBACK HANDLERS ==============

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def handle_admin_callbacks(call):
    if call.message.chat.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Admin access only!")
        return
    
    action = call.data.replace("admin_", "")
    
    if action == "users":
        users = get_all_users()
        if not users:
            bot.edit_message_text("📭 No users found", call.message.chat.id, call.message.message_id)
        else:
            user_list = "👥 ALL USERS LIST\n━━━━━━━━━━━━━━━━━━━━━━\n"
            for uid in users:
                project_count = get_user_project_count(uid)
                running_count = len(running_projects.get(uid, {}))
                user_list += f"\n👤 {uid}\n├─ 📦 {project_count} projects\n└─ 🟢 {running_count} running\n"
            user_list += f"\n💻 Powered by @Hexh4ckerOFC"
            
            if len(user_list) > 4000:
                user_list = user_list[:4000] + "\n... (truncated)"
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back"))
            bot.edit_message_text(user_list, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif action == "projects":
        update_admin_stats()
        text = f"📦 ALL PROJECTS SUMMARY\n━━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"├─ Total Projects: {admin_stats['total_projects']}\n"
        text += f"├─ Running: {admin_stats['total_running']} 🟢\n"
        text += f"└─ Stopped: {admin_stats['total_projects'] - admin_stats['total_running']} ⚪\n"
        
        users = get_all_users()
        for uid in users[:10]:
            user_projects = get_user_projects(uid)
            if user_projects:
                text += f"\n👤 User {uid}:\n"
                for proj in user_projects[:5]:
                    is_running = proj in running_projects.get(uid, {})
                    icon = "🟢" if is_running else "⚪"
                    text += f"  {icon} {proj}\n"
                if len(user_projects) > 5:
                    text += f"  ... and {len(user_projects)-5} more\n"
        
        text += f"\n💻 Powered by @Hexh4ckerOFC"
        
        if len(text) > 4000:
            text = text[:4000] + "\n... (truncated)"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif action == "running":
        running_list = "🟢 RUNNING PROJECTS\n━━━━━━━━━━━━━━━━━━━━━━\n"
        has_running = False
        for user_id, user_projects in running_projects.items():
            if user_projects:
                has_running = True
                running_list += f"\n👤 User {user_id}:\n"
                for proj in user_projects.keys():
                    running_list += f"  🟢 {proj}\n"
        
        if not has_running:
            running_list += "\n📭 No projects currently running"
        
        running_list += f"\n💻 Powered by @Hexh4ckerOFC"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back"))
        bot.edit_message_text(running_list, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif action == "errors":
        error_list = "⚠️ ERROR LOGS\n━━━━━━━━━━━━━━━━━━━━━━\n"
        has_errors = False
        for user_id, errors in project_errors.items():
            if errors:
                has_errors = True
                error_list += f"\n👤 User {user_id}:\n"
                for proj, err in errors.items():
                    error_list += f"  📁 {proj}: {err[:50]}...\n"
        
        if not has_errors:
            error_list += "\n✅ No errors logged"
        
        error_list += f"\n💻 Powered by @Hexh4ckerOFC"
        
        if len(error_list) > 4000:
            error_list = error_list[:4000] + "\n... (truncated)"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back"))
        bot.edit_message_text(error_list, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif action == "server":
        try:
            disk_usage = shutil.disk_usage("/")
            disk_total = disk_usage.total // (1024**3)
            disk_used = disk_usage.used // (1024**3)
            disk_free = disk_usage.free // (1024**3)
            disk_percent = (disk_usage.used / disk_usage.total) * 100
            
            server_text = f"""
💾 SERVER STATISTICS
━━━━━━━━━━━━━━━━━━━━━━

💿 DISK USAGE
├─ Total: {disk_total} GB
├─ Used: {disk_used} GB ({disk_percent:.1f}%)
├─ Free: {disk_free} GB
└─ Status: {'⚠️ Low Space' if disk_free < 5 else '✅ Healthy'}

📂 STORAGE PATHS
├─ Base Dir: {BASE_DIR}
└─ Projects Path: {os.path.abspath(BASE_DIR)}

💻 Powered by @Hexh4ckerOFC
            """
        except:
            server_text = "💾 SERVER STATISTICS\n━━━━━━━━━━━━━━━━━━━━━━\n❌ Unable to fetch disk statistics\n\n💻 Powered by @Hexh4ckerOFC"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back"))
        bot.edit_message_text(server_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif action == "botstats":
        update_admin_stats()
        uptime = datetime.now() - admin_stats["bot_start_time"]
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        stats_text = f"""
📊 BOT STATISTICS
━━━━━━━━━━━━━━━━━━━━━━

📈 USAGE STATS
├─ 👥 Total Users: {admin_stats['total_users']}
├─ 📦 Total Projects: {admin_stats['total_projects']}
├─ 🟢 Running Projects: {admin_stats['total_running']}
└─ 📁 Projects/User: {admin_stats['total_projects']/max(admin_stats['total_users'],1):.1f}

⏱️ BOT INFO
├─ Uptime: {hours}h {minutes}m {seconds}s
├─ Started: {admin_stats['bot_start_time'].strftime('%Y-%m-%d %H:%M:%S')}
└─ Admin ID: {ADMIN_ID}

🔧 SYSTEM
├─ Python: {sys.version.split()[0]}
└─ Platform: {sys.platform}

💻 Powered by @Hexh4ckerOFC
        """
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back"))
        bot.edit_message_text(stats_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif action == "top_users":
        top_by_commands = get_top_users(15, "commands")
        
        current_month = datetime.now().strftime("%B %Y")
        text = f"🏆 TOP USERS LEADERBOARD - {current_month}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        if top_by_commands:
            for i, user in enumerate(top_by_commands, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                text += f"{medal} `{user['username'][:20]}`\n"
                text += f"    ├─ Commands: {user['commands']}\n"
                text += f"    └─ Projects: {user['projects']}\n\n"
        else:
            text += "No data available yet\n"
        
        text += f"📊 Total Users: {len(monthly_stats['users'])}\n"
        text += f"📊 Total Commands: {monthly_stats['total_commands']}\n"
        text += f"📊 Total Projects: {monthly_stats['total_projects_deployed']}\n"
        text += f"\n💻 Powered by @Hexh4ckerOFC"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif action == "clean":
        cleaned = clean_orphaned_processes()
        bot.edit_message_text(f"✅ Cleanup Complete\n\n🗑️ Removed {cleaned} orphaned process entries", 
                            call.message.chat.id, call.message.message_id)
        time.sleep(2)
        admin_panel(call.message)
    
    elif action == "broadcast":
        bot.edit_message_text("📢 Broadcast Mode\n\nSend the message you want to broadcast to all users.\n\nType /cancel to cancel.", 
                            call.message.chat.id, call.message.message_id)
        bot.register_next_step_handler(call.message, process_broadcast)
    
    elif action == "back":
        admin_panel(call.message)
    
    elif action == "close":
        bot.delete_message(call.message.chat.id, call.message.message_id)
    
    bot.answer_callback_query(call.id)

def process_broadcast(msg):
    if msg.text == "/cancel":
        safe_send_message(msg.chat.id, "❌ Broadcast cancelled.", reply_markup=get_main_keyboard(msg.chat.id), delay=30)
        return
    
    status_msg = safe_send_message(msg.chat.id, "📡 Broadcasting message...")
    
    success, failed = broadcast_message(msg.text)
    
    bot.edit_message_text(f"✅ Broadcast Complete\n\n📨 Sent: {success}\n❌ Failed: {failed}", 
                        msg.chat.id, status_msg.message_id)
    
    safe_send_message(msg.chat.id, "👑 Admin Panel", reply_markup=get_admin_keyboard())

# ============== USER COMMANDS ==============

@bot.message_handler(func=lambda m: m.text == "📦 Upload" or m.text == "📦 Upload Project")
def upload_btn(msg):
    update_user_stats(msg.chat.id, command_used=True)
    safe_send_message(msg.chat.id, "📦 Send your .zip file with:\n• main.py (or any Python file)\n• requirements.txt\n\n📝 Max size: 50MB\n🔒 Your files are private to you\n\n🐙 Or use GitHub Deploy for repositories!", delay=60)

@bot.message_handler(func=lambda m: m.text == "📁 Projects" or m.text == "📁 My Projects")
def file_manager(msg):
    user_id = msg.chat.id
    update_user_stats(user_id, command_used=True)
    projects = get_user_projects(user_id)
    user_running = get_user_running_projects(user_id)
    
    if not projects:
        safe_send_message(msg.chat.id, "📂 No projects found\nUse 📦 Upload or 🐙 GitHub Deploy to add one.", delay=30)
        return
    
    project_list = "📁 YOUR PROJECTS\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for project in projects:
        is_running = project in user_running
        has_main = os.path.exists(os.path.join(get_user_dir(user_id), project, "main.py"))
        user_errors = get_user_errors(user_id)
        has_error = project in user_errors
        is_github = project.startswith("github_")
        
        status_icon = "🟢" if is_running else "⚪"
        main_icon = "✅" if has_main else "❌"
        error_icon = "⚠️" if has_error else "✓"
        github_icon = "🐙" if is_github else "📦"
        
        project_list += f"\n{status_icon} {project}\n   ├─ Type: {github_icon}\n   ├─ main.py: {main_icon}\n   └─ Status: {error_icon}\n"
    
    project_list += f"\n💻 Powered by @Hexh4ckerOFC"
    safe_send_message(msg.chat.id, project_list, delay=60)

@bot.message_handler(func=lambda m: m.text == "▶️ Start")
def start_project_menu(msg):
    user_id = msg.chat.id
    update_user_stats(user_id, command_used=True)
    projects = get_user_projects(user_id)
    user_running = get_user_running_projects(user_id)
    
    if not projects:
        safe_send_message(msg.chat.id, "❌ No projects found to start", delay=30)
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for project in projects:
        if project not in user_running:
            markup.add(InlineKeyboardButton(f"▶️ {project}", callback_data=f"start_{project}"))
    
    if not markup.keyboard:
        safe_send_message(msg.chat.id, f"✅ All your projects are already running!", delay=30)
    else:
        safe_send_message(msg.chat.id, "🚀 Select project to start:", reply_markup=markup, delay=60)

@bot.message_handler(func=lambda m: m.text == "⏹️ Stop")
def stop_project_menu(msg):
    user_id = msg.chat.id
    update_user_stats(user_id, command_used=True)
    user_running = get_user_running_projects(user_id)
    
    if not user_running:
        safe_send_message(msg.chat.id, "⚪ No projects are currently running", delay=30)
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for project in user_running.keys():
        markup.add(InlineKeyboardButton(f"⏹️ {project}", callback_data=f"stop_{project}"))
    
    safe_send_message(msg.chat.id, "🛑 Select project to stop:", reply_markup=markup, delay=60)

@bot.message_handler(func=lambda m: m.text == "🔄 Restart")
def restart_project_menu(msg):
    user_id = msg.chat.id
    update_user_stats(user_id, command_used=True)
    projects = get_user_projects(user_id)
    
    if not projects:
        safe_send_message(msg.chat.id, "❌ No projects found to restart", delay=30)
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for project in projects:
        markup.add(InlineKeyboardButton(f"🔄 {project}", callback_data=f"restart_{project}"))
    
    safe_send_message(msg.chat.id, "🔄 Select project to restart:", reply_markup=markup, delay=60)

@bot.message_handler(func=lambda m: m.text == "🗑️ Delete")
def delete_project_menu(msg):
    user_id = msg.chat.id
    update_user_stats(user_id, command_used=True)
    projects = get_user_projects(user_id)
    
    if not projects:
        safe_send_message(msg.chat.id, "📂 No projects to delete", delay=30)
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for project in projects:
        markup.add(InlineKeyboardButton(f"🗑️ {project}", callback_data=f"delete_{project}"))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete"))
    
    safe_send_message(msg.chat.id, "⚠️ Select project to delete (IRREVERSIBLE):", reply_markup=markup, delay=60)

@bot.message_handler(func=lambda m: m.text == "🗑️ Delete All")
def delete_all(msg):
    update_user_stats(msg.chat.id, command_used=True)
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ YES, Delete All", callback_data="confirm_delete_all"),
        InlineKeyboardButton("❌ NO, Cancel", callback_data="cancel_delete")
    )
    safe_send_message(msg.chat.id, "⚠️ WARNING: This will delete ALL your projects!\nAre you sure?", reply_markup=markup, delay=60)

@bot.message_handler(func=lambda m: m.text == "📊 Stats")
def server_info(msg):
    user_id = msg.chat.id
    update_user_stats(user_id, command_used=True)
    total_projects = len(get_user_projects(user_id))
    running_count = len(get_user_running_projects(user_id))
    user_errors = get_user_errors(user_id)
    error_count = len(user_errors)
    github_count = len([p for p in get_user_projects(user_id) if p.startswith("github_")])
    
    try:
        user_dir = get_user_dir(user_id)
        disk_usage = shutil.disk_usage(user_dir)
        disk_total = disk_usage.total // (1024**3)
        disk_used = disk_usage.used // (1024**3)
        disk_percent = (disk_usage.used / disk_usage.total) * 100
        disk_text = f"{disk_used}GB / {disk_total}GB ({disk_percent:.1f}%)"
    except:
        disk_text = "N/A"
    
    stats_text = f"""
📊 YOUR STATISTICS
━━━━━━━━━━━━━━━━━━━━━━

📦 PROJECTS
├─ Total: {total_projects}
├─ Running: {running_count} 🟢
├─ Stopped: {total_projects - running_count} ⚪
├─ GitHub: {github_count} 🐙
└─ Errors: {error_count} ⚠️

💾 STORAGE
└─ Disk Usage: {disk_text}

👤 USER INFO
├─ User ID: {user_id}
└─ Workspace: Private

🕐 Server Time
└─ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

💻 Powered by @Hexh4ckerOFC
    """
    safe_send_message(msg.chat.id, stats_text, parse_mode="Markdown", delay=60)

@bot.message_handler(func=lambda m: m.text == "🔄 Refresh")
def refresh_status(msg):
    user_id = msg.chat.id
    update_user_stats(user_id, command_used=True)
    user_running = get_user_running_projects(user_id)
    dead_projects = []
    
    for project, info in list(user_running.items()):
        process = info["process"] if isinstance(info, dict) else info
        if process.poll() is not None:
            dead_projects.append(project)
            del user_running[project]
            user_errors = get_user_errors(user_id)
            user_errors[project] = f"Process died at {datetime.now().strftime('%H:%M:%S')}"
    
    if dead_projects:
        safe_send_message(msg.chat.id, f"⚠️ Detected dead processes:\n{', '.join(dead_projects)}\n\nUse Start to restart them.", delay=30)
    else:
        running_count = len(user_running)
        safe_send_message(msg.chat.id, f"✅ Status Refreshed | 🟢 Running: {running_count}", delay=30)

@bot.message_handler(func=lambda m: m.text == "📝 Errors")
def view_errors(msg):
    user_id = msg.chat.id
    update_user_stats(user_id, command_used=True)
    user_errors = get_user_errors(user_id)
    
    if not user_errors:
        safe_send_message(msg.chat.id, "✅ No errors logged! All projects running smoothly.", delay=30)
        return
    
    error_text = f"⚠️ ERROR LOG\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for project, error in user_errors.items():
        error_text += f"\n📁 {project}\n└─ {error[:100]}\n"
    
    if len(error_text) > 4000:
        error_text = error_text[:4000] + "\n... (truncated)"
    
    error_text += f"\n💻 Powered by @Hexh4ckerOFC"
    safe_send_message(msg.chat.id, error_text, delay=60)

@bot.message_handler(func=lambda m: m.text == "❓ Help")
def help_command(msg):
    update_user_stats(msg.chat.id, command_used=True)
    help_text = """
📚 HELP MENU v3.0
━━━━━━━━━━━━━━━━━━━━━━

🎯 PROJECT MANAGEMENT
📦 Upload - Deploy new .zip project
🐙 GitHub Deploy - Clone from GitHub (auto-detects entry points)
📁 Projects - View all projects with status
▶️ Start - Run a specific project
⏹️ Stop - Stop running project
🔄 Restart - Restart a project
🗑️ Delete - Delete specific project
🗑️ Delete All - Delete ALL your projects

⚙️ ENVIRONMENT VARIABLES
⚙️ Env Vars - Set environment variables for projects
• KEY=value format
• Saved to .env file
• Auto-applied on restart

📊 MONITORING & STATS
📊 Stats - Your storage & project counts
🔄 Refresh - Check if projects are running
📝 Errors - See error logs
🏆 Top Users - Monthly leaderboard (most active users)

🔍 AUTO-DETECTION FEATURES
• Entry Points: main.py, app.py, bot.py, run.py, server.py, etc.
• Project Types: Django, Flask, FastAPI, Discord Bot, Telegram Bot
• Auto-renames detected entry file to main.py

💡 MESSAGE FEATURES
• All messages auto-delete after 30 seconds
• Clean and organized chat

🔒 PRIVACY
• Each user has their own private workspace
• No file conflicts between users
• Your projects are completely isolated

🆘 SUPPORT
Contact: @Hexh4ckerOFC

🟢 Bot Status: ONLINE & FULLY WORKING

💻 Powered by @Hexh4ckerOFC
    """
    safe_send_message(msg.chat.id, help_text, parse_mode="Markdown", delay=120)

# ============== CALLBACK HANDLERS ==============

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.message.chat.id
    update_user_stats(user_id, command_used=True)
    
    # Handle Start Project
    if call.data.startswith("start_"):
        project_name = call.data.replace("start_", "")
        result = start_project(user_id, project_name)
        if result:
            bot.edit_message_text(f"✅ {project_name} started successfully!", 
                                call.message.chat.id, call.message.message_id)
        else:
            bot.edit_message_text(f"❌ Failed to start {project_name}\nCheck if main.py exists!", 
                                call.message.chat.id, call.message.message_id)
        
        # Auto-delete after 30 seconds
        def delete_after():
            time.sleep(30)
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
        threading.Thread(target=delete_after, daemon=True).start()
    
    # Handle Stop Project
    elif call.data.startswith("stop_"):
        project_name = call.data.replace("stop_", "")
        if project_name in get_user_running_projects(user_id):
            stop_project(user_id, project_name)
            bot.edit_message_text(f"⏹️ {project_name} stopped successfully", 
                                call.message.chat.id, call.message.message_id)
        else:
            bot.edit_message_text(f"⚠️ {project_name} is not running", 
                                call.message.chat.id, call.message.message_id)
    
    # Handle Restart Project
    elif call.data.startswith("restart_"):
        project_name = call.data.replace("restart_", "")
        bot.edit_message_text(f"🔄 Restarting {project_name}...", 
                            call.message.chat.id, call.message.message_id)
        
        if project_name in get_user_running_projects(user_id):
            stop_project(user_id, project_name)
            time.sleep(2)
        
        result = start_project(user_id, project_name)
        if result:
            safe_send_message(call.message.chat.id, f"✅ {project_name} restarted successfully!", delay=30)
        else:
            safe_send_message(call.message.chat.id, f"❌ Failed to restart {project_name}", delay=30)
    
    # Handle Delete Project
    elif call.data.startswith("delete_"):
        project_name = call.data.replace("delete_", "")
        delete_project(user_id, project_name)
        bot.edit_message_text(f"🗑️ Project {project_name} deleted", 
                            call.message.chat.id, call.message.message_id)
    
    # Handle Delete All
    elif call.data == "confirm_delete_all":
        user_dir = get_user_dir(user_id)
        user_running = get_user_running_projects(user_id)
        
        for project in list(user_running.keys()):
            stop_project(user_id, project)
        
        user_running.clear()
        
        if user_id in project_errors:
            project_errors[user_id].clear()
        
        for item in os.listdir(user_dir):
            item_path = os.path.join(user_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
        
        bot.edit_message_text("🗑️ ALL your projects deleted successfully!", 
                            call.message.chat.id, call.message.message_id)
    
    # Handle Cancel
    elif call.data == "cancel_delete":
        bot.edit_message_text("❌ Action cancelled", 
                            call.message.chat.id, call.message.message_id)
    
    bot.answer_callback_query(call.id)

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

def start_project(user_id, project_name):
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    main_file = os.path.join(project_path, "main.py")
    user_running = get_user_running_projects(user_id)
    
    if not os.path.exists(main_file):
        error_msg = f"main.py not found in {project_name}"
        user_errors = get_user_errors(user_id)
        user_errors[project_name] = error_msg
        return False
    
    if project_name in user_running:
        return False
    
    try:
        env = os.environ.copy()
        env_file = os.path.join(project_path, ".env")
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            env[key] = value
        
        process = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env=env
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
        
        monitor_thread = threading.Thread(target=monitor_single_project, args=(user_id, project_name, process))
        monitor_thread.daemon = True
        monitor_thread.start()
        
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
            
    except Exception as e:
        print(f"Monitor error for {project_name}: {e}")

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
    
    if user_id in project_env_vars and project_name in project_env_vars[user_id]:
        del project_env_vars[user_id][project_name]

@bot.message_handler(content_types=['document'])
def handle_zip(msg):
    user_id = msg.chat.id
    update_user_stats(user_id, project_deployed=True)
    
    if not msg.document.file_name.endswith(".zip"):
        safe_send_message(msg.chat.id, "❌ Send only .zip file", delay=30)
        return

    status_msg = safe_send_message(msg.chat.id, "📦 Processing upload...")

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
        safe_send_message(msg.chat.id, f"📝 Project renamed to {project_name} to avoid conflict", delay=30)
    
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
        
        bot.edit_message_text("📦 Extracted!", msg.chat.id, status_msg.message_id)
        
        # Auto-detect entry point
        entry_path, entry_file = find_entry_point(extract_path)
        
        if entry_path and entry_path != os.path.join(extract_path, "main.py"):
            shutil.move(entry_path, os.path.join(extract_path, "main.py"))
            bot.edit_message_text(f"📝 Detected entry point: {entry_file} → renamed to main.py",
                                msg.chat.id, status_msg.message_id)
        
        project_type, _ = get_project_type(extract_path)
        bot.edit_message_text(f"🔍 Detected project type: {project_type}",
                            msg.chat.id, status_msg.message_id)
        
        req_file = os.path.join(extract_path, "requirements.txt")
        if os.path.exists(req_file):
            subprocess.Popen(["pip", "install", "-r", req_file], cwd=extract_path,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            bot.edit_message_text("📥 Installing requirements...", msg.chat.id, status_msg.message_id)
        
        main_file = os.path.join(extract_path, "main.py")
        size = get_folder_size(extract_path)
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("▶️ Start Now", callback_data=f"start_{project_name}"),
            InlineKeyboardButton("⚙️ Set Env Vars", callback_data=f"env_{project_name}")
        )
        
        bot.edit_message_text(f"✅ Project {project_name} uploaded successfully!\n\n📁 Size: {size}\n📄 Entry: {'✅' if os.path.exists(main_file) else '❌'}\n🔧 Type: {project_type}\n\nClick below to start:", 
                            msg.chat.id, status_msg.message_id, reply_markup=markup)
        
    except Exception as e:
        error_msg = str(e)
        bot.edit_message_text(f"❌ Upload failed: {error_msg[:150]}", 
                            msg.chat.id, status_msg.message_id)
        user_errors = get_user_errors(user_id)
        user_errors[project_name] = error_msg

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

def get_all_users():
    users = []
    for user_id in os.listdir(BASE_DIR):
        user_path = os.path.join(BASE_DIR, user_id)
        if os.path.isdir(user_path) and user_id.isdigit():
            users.append(int(user_id))
    return users

def get_user_project_count(user_id):
    user_dir = os.path.join(BASE_DIR, str(user_id))
    if not os.path.exists(user_dir):
        return 0
    return len([d for d in os.listdir(user_dir) if os.path.isdir(os.path.join(user_dir, d))])

def update_admin_stats():
    users = set()
    total_projects = 0
    total_running = 0
    
    for user_id, user_projects in running_projects.items():
        users.add(user_id)
        total_running += len(user_projects)
    
    for user_id in os.listdir(BASE_DIR):
        user_path = os.path.join(BASE_DIR, user_id)
        if os.path.isdir(user_path):
            users.add(int(user_id) if user_id.isdigit() else user_id)
            for project in os.listdir(user_path):
                project_path = os.path.join(user_path, project)
                if os.path.isdir(project_path):
                    total_projects += 1
    
    admin_stats["total_users"] = len(users)
    admin_stats["total_projects"] = total_projects
    admin_stats["total_running"] = total_running

def broadcast_message(message_text, user_ids=None):
    if user_ids is None:
        user_ids = get_all_users()
    
    success = 0
    failed = 0
    
    for uid in user_ids:
        try:
            safe_send_message(uid, f"📢 ANNOUNCEMENT\n\n{message_text}")
            success += 1
        except:
            failed += 1
        time.sleep(0.1)
    
    return success, failed

def clean_orphaned_processes():
    cleaned = 0
    for user_id, user_projects in list(running_projects.items()):
        for project_name, info in list(user_projects.items()):
            process = info["process"] if isinstance(info, dict) else info
            if process.poll() is not None:
                del running_projects[user_id][project_name]
                cleaned += 1
    return cleaned

def monitor_processes():
    while True:
        time.sleep(10)
        for user_id, user_projects in list(running_projects.items()):
            for project_name, info in list(user_projects.items()):
                process = info["process"] if isinstance(info, dict) else info
                if process.poll() is not None:
                    del running_projects[user_id][project_name]
                    if user_id not in project_errors:
                        project_errors[user_id] = {}
                    project_errors[user_id][project_name] = f"Crashed at {datetime.now().strftime('%H:%M:%S')}"
                    print(f"User {user_id} project {project_name} crashed")

# Load saved stats on startup
load_monthly_stats()

monitor_thread = threading.Thread(target=monitor_processes, daemon=True)
monitor_thread.start()

# ============== BOT STARTUP ==============

print("="*50)
print("PYTHON HOSTING PANEL v3.0 - READY")
print("="*50)
print("Bot Running Successfully!")
print(f"Base Directory: {BASE_DIR}")
print(f"Multi-User Support: ENABLED")
print(f"Private Workspaces: YES")
print(f"Admin ID: {ADMIN_ID}")
print(f"GitHub Integration: ENHANCED")
print(f"Auto-Detection: main.py, app.py, bot.py, run.py, server.py")
print(f"Project Types: Django, Flask, FastAPI, Discord, Telegram")
print(f"Environment Variables: ENABLED")
print(f"Monthly Leaderboard: ENABLED")
print(f"Auto-Delete Messages: 30-60 seconds")
print("="*50)

# Start bot with error handling
while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Bot error: {e}")
        time.sleep(5)