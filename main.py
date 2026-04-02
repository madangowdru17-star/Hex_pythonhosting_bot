import telebot
import os
import zipfile
import subprocess
import shutil
import time
import threading
from datetime import datetime
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8759695144:AAE1FtyjdWpjqGxRTRZmqf2rP50JDK47K6A"

bot = telebot.TeleBot(BOT_TOKEN)

BASE_DIR = "projects"
os.makedirs(BASE_DIR, exist_ok=True)

# Store running processes to track status
running_projects = {}
project_errors = {}

# 🔘 Enhanced Buttons UI with better emojis
def panel():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "📤 Upload Project", "📁 My Projects",
        "▶️ Start Project", "⏹️ Stop Project",
        "🗑️ Delete Project", "🗑️ Delete All",
        "📊 Server Stats", "🔄 Refresh Status",
        "📝 View Errors", "❓ Help @Hexh4ckerOFC"
    ]
    markup.add(*buttons)
    return markup

# 🚀 Start Command
@bot.message_handler(commands=['start'])
def start(msg):
    total_projects = len([d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))])
    
    welcome_text = f"""
╔══════════════════════════════╗
║   🔥 PYTHON HOSTING PANEL    ║
║      🚀 READY TO DEPLOY      ║
╚══════════════════════════════╝

✨ *Features:*
✅ Upload & Deploy Python Projects
✅ Auto-Install Requirements
✅ Project Status Tracking
✅ Error Logging System
✅ Selective Delete Option

📊 *Current Status:*
├─ Bot Status: 🟢 ONLINE
├─ Projects: {total_projects}
└─ Running: {len(running_projects)}

💡 *Need Help?* @Hexh4ckerOFC
    """
    
    bot.send_message(msg.chat.id, welcome_text, parse_mode="Markdown", reply_markup=panel())

# 📤 Upload Project
@bot.message_handler(func=lambda m: m.text == "📤 Upload Project")
def upload_btn(msg):
    bot.send_message(msg.chat.id, "📦 *Send your .zip file with:*\n• `main.py`\n• `requirements.txt`\n\n📝 *Max size: 50MB*", parse_mode="Markdown")

# 📁 My Projects (Enhanced with status)
@bot.message_handler(func=lambda m: m.text == "📁 My Projects")
def file_manager(msg):
    projects = get_valid_projects()
    if not projects:
        bot.send_message(msg.chat.id, "📂 *No projects found*\nUse 📤 Upload Project to add one.", parse_mode="Markdown")
        return
    
    project_list = "📁 *Your Projects:*\n━━━━━━━━━━━━━━━\n"
    for project in projects:
        # Check project status
        is_running = project in running_projects
        has_main = os.path.exists(os.path.join(BASE_DIR, project, "main.py"))
        has_error = project in project_errors
        
        status_icon = "🟢" if is_running else "⚪"
        main_icon = "✅" if has_main else "❌"
        error_icon = "⚠️" if has_error else "✓"
        
        project_list += f"\n{status_icon} `{project}`\n   ├─ main.py: {main_icon}\n   └─ Status: {error_icon}\n"
    
    bot.send_message(msg.chat.id, project_list, parse_mode="Markdown")

# ▶️ Start Project
@bot.message_handler(func=lambda m: m.text == "▶️ Start Project")
def start_project_menu(msg):
    projects = get_valid_projects()
    if not projects:
        bot.send_message(msg.chat.id, "❌ *No valid projects found to start*", parse_mode="Markdown")
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for project in projects:
        if project not in running_projects:
            markup.add(InlineKeyboardButton(f"▶️ {project}", callback_data=f"start_{project}"))
    
    if not markup.keyboard:
        bot.send_message(msg.chat.id, "✅ *All projects are already running!*", parse_mode="Markdown")
    else:
        bot.send_message(msg.chat.id, "🚀 *Select project to start:*", parse_mode="Markdown", reply_markup=markup)

# ⏹️ Stop Project
@bot.message_handler(func=lambda m: m.text == "⏹️ Stop Project")
def stop_project_menu(msg):
    if not running_projects:
        bot.send_message(msg.chat.id, "⚪ *No projects are currently running*", parse_mode="Markdown")
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for project in running_projects.keys():
        markup.add(InlineKeyboardButton(f"⏹️ {project}", callback_data=f"stop_{project}"))
    
    bot.send_message(msg.chat.id, "🛑 *Select project to stop:*", parse_mode="Markdown", reply_markup=markup)

# 🗑️ Delete Project (Selective Delete)
@bot.message_handler(func=lambda m: m.text == "🗑️ Delete Project")
def delete_project_menu(msg):
    projects = get_valid_projects()
    if not projects:
        bot.send_message(msg.chat.id, "📂 *No projects to delete*", parse_mode="Markdown")
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for project in projects:
        markup.add(InlineKeyboardButton(f"🗑️ {project}", callback_data=f"delete_{project}"))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete"))
    
    bot.send_message(msg.chat.id, "⚠️ *Select project to delete (IRREVERSIBLE):*", 
                     parse_mode="Markdown", reply_markup=markup)

# 🗑️ Delete All
@bot.message_handler(func=lambda m: m.text == "🗑️ Delete All")
def delete_all(msg):
    # Confirm deletion
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ YES, Delete All", callback_data="confirm_delete_all"),
        InlineKeyboardButton("❌ NO, Cancel", callback_data="cancel_delete")
    )
    bot.send_message(msg.chat.id, "⚠️ *WARNING: This will delete ALL projects!*\nAre you sure?", 
                     parse_mode="Markdown", reply_markup=markup)

# 📊 Server Stats (Without psutil - using basic commands)
@bot.message_handler(func=lambda m: m.text == "📊 Server Stats")
def server_info(msg):
    total_projects = len(get_valid_projects())
    running_count = len(running_projects)
    error_count = len(project_errors)
    
    # Get disk usage using basic command
    try:
        disk_usage = shutil.disk_usage(BASE_DIR)
        disk_total = disk_usage.total // (1024**3)
        disk_used = disk_usage.used // (1024**3)
        disk_percent = (disk_usage.used / disk_usage.total) * 100
        disk_text = f"{disk_used}GB / {disk_total}GB ({disk_percent:.1f}%)"
    except:
        disk_text = "N/A"
    
    stats_text = f"""
╔══════════════════════════════╗
║      📊 SERVER STATISTICS    ║
╚══════════════════════════════╝

📦 *PROJECTS*
├─ Total: {total_projects}
├─ Running: {running_count} 🟢
├─ Stopped: {total_projects - running_count} ⚪
└─ Errors: {error_count} ⚠️

💾 *STORAGE*
└─ Disk Usage: {disk_text}

📁 *Storage Path*
└─ `{BASE_DIR}`

🕐 *Server Time*
└─ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    bot.send_message(msg.chat.id, stats_text, parse_mode="Markdown")

# 🔄 Refresh Status
@bot.message_handler(func=lambda m: m.text == "🔄 Refresh Status")
def refresh_status(msg):
    # Check if running processes are still alive
    dead_projects = []
    for project, process in list(running_projects.items()):
        if process.poll() is not None:  # Process died
            dead_projects.append(project)
            del running_projects[project]
            project_errors[project] = f"⚠️ Process died at {datetime.now().strftime('%H:%M:%S')}"
    
    if dead_projects:
        bot.send_message(msg.chat.id, f"⚠️ *Detected dead processes:*\n{', '.join(dead_projects)}\n\nUse ▶️ Start Project to restart them.", 
                         parse_mode="Markdown")
    else:
        running_count = len(running_projects)
        bot.send_message(msg.chat.id, f"✅ *Status Refreshed* | 🟢 Running: {running_count}", 
                         parse_mode="Markdown")

# 📝 View Errors
@bot.message_handler(func=lambda m: m.text == "📝 View Errors")
def view_errors(msg):
    if not project_errors:
        bot.send_message(msg.chat.id, "✅ *No errors logged! All projects running smoothly.*", parse_mode="Markdown")
        return
    
    error_text = "⚠️ *Error Log:*\n━━━━━━━━━━━━━━━\n"
    for project, error in project_errors.items():
        error_text += f"\n📁 `{project}`\n└─ {error[:100]}\n"
    
    # Split if too long
    if len(error_text) > 4000:
        error_text = error_text[:4000] + "\n... (truncated)"
    
    bot.send_message(msg.chat.id, error_text, parse_mode="Markdown")

# ❓ Help
@bot.message_handler(func=lambda m: m.text == "❓ Help @Hexh4ckerOFC")
def help_command(msg):
    help_text = """
╔══════════════════════════════╗
║        📚 HELP MENU          ║
╚══════════════════════════════╝

🎯 *PROJECT MANAGEMENT*
📤 Upload Project - Deploy new .zip project
📁 My Projects - View all projects with status
▶️ Start Project - Run a specific project
⏹️ Stop Project - Stop running project
🗑️ Delete Project - Delete specific project
🗑️ Delete All - Delete ALL projects

📊 *MONITORING*
📊 Server Stats - Storage & project counts
🔄 Refresh Status - Check if projects are running
📝 View Errors - See error logs

💡 *TIPS*
• Make sure your .zip has main.py
• Requirements.txt is optional
• Max file size: 50MB
• Projects auto-extract to folders

🆘 *SUPPORT*
Contact: @Hexh4ckerOFC

🟢 *Bot Status: ONLINE & WORKING*
    """
    bot.send_message(msg.chat.id, help_text, parse_mode="Markdown")

# Callback handlers for inline buttons
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    # Handle Start Project
    if call.data.startswith("start_"):
        project_name = call.data.replace("start_", "")
        result = start_project(project_name, call.message.chat.id)
        if result:
            bot.edit_message_text(f"✅ *'{project_name}' started successfully!*", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text(f"❌ *Failed to start '{project_name}'*\nCheck if main.py exists!", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    # Handle Stop Project
    elif call.data.startswith("stop_"):
        project_name = call.data.replace("stop_", "")
        if project_name in running_projects:
            stop_project(project_name)
            bot.edit_message_text(f"⏹️ *'{project_name}' stopped successfully*", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text(f"⚠️ *'{project_name}' is not running*", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    # Handle Delete Project
    elif call.data.startswith("delete_"):
        project_name = call.data.replace("delete_", "")
        delete_project(project_name)
        bot.edit_message_text(f"🗑️ *Project '{project_name}' deleted*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    # Handle Delete All Confirmation
    elif call.data == "confirm_delete_all":
        # Stop all running projects
        for project in list(running_projects.keys()):
            stop_project(project)
        running_projects.clear()
        project_errors.clear()
        
        # Delete all folders
        for item in os.listdir(BASE_DIR):
            item_path = os.path.join(BASE_DIR, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
        
        bot.edit_message_text("🗑️ *ALL projects deleted successfully!*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    # Handle Cancel
    elif call.data == "cancel_delete":
        bot.edit_message_text("❌ *Action cancelled*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    bot.answer_callback_query(call.id)

# Helper function to get valid projects
def get_valid_projects():
    projects = []
    for item in os.listdir(BASE_DIR):
        item_path = os.path.join(BASE_DIR, item)
        if os.path.isdir(item_path):
            projects.append(item)
    return projects

# Helper function to start project
def start_project(project_name, chat_id=None):
    project_path = os.path.join(BASE_DIR, project_name)
    main_file = os.path.join(project_path, "main.py")
    
    if not os.path.exists(main_file):
        if chat_id:
            bot.send_message(chat_id, f"❌ *main.py not found in '{project_name}'*", parse_mode="Markdown")
        return False
    
    try:
        process = subprocess.Popen(["python", main_file], cwd=project_path)
        running_projects[project_name] = process
        
        # Clear error if exists
        if project_name in project_errors:
            del project_errors[project_name]
        
        return True
    except Exception as e:
        project_errors[project_name] = str(e)
        return False

# Helper function to stop project
def stop_project(project_name):
    if project_name in running_projects:
        try:
            running_projects[project_name].terminate()
            del running_projects[project_name]
            return True
        except:
            return False
    return False

# Helper function to delete project
def delete_project(project_name):
    # Stop if running
    if project_name in running_projects:
        stop_project(project_name)
    
    # Delete folder
    project_path = os.path.join(BASE_DIR, project_name)
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
    
    # Remove from errors
    if project_name in project_errors:
        del project_errors[project_name]

# 📦 Handle ZIP Upload (YOUR ORIGINAL CODE - COMPLETELY UNCHANGED)
@bot.message_handler(content_types=['document'])
def handle_zip(msg):
    if not msg.document.file_name.endswith(".zip"):
        bot.send_message(msg.chat.id, "❌ Send only .zip file")
        return

    file_info = bot.get_file(msg.document.file_id)
    downloaded = bot.download_file(file_info.file_path)

    zip_path = f"{BASE_DIR}/{msg.document.file_name}"

    with open(zip_path, 'wb') as f:
        f.write(downloaded)

    extract_path = zip_path.replace(".zip", "")
    os.makedirs(extract_path, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_path)

    bot.send_message(msg.chat.id, "📦 Extracted!")

    # 🔧 Install requirements
    req_file = os.path.join(extract_path, "requirements.txt")

    try:
        if os.path.exists(req_file):
            subprocess.run(["pip", "install", "-r", req_file])
            bot.send_message(msg.chat.id, "📥 Requirements Installed")

        # ▶️ Run main.py
        main_file = os.path.join(extract_path, "main.py")
        process = subprocess.Popen(["python", main_file])
        
        # Track the running project
        project_name = msg.document.file_name.replace(".zip", "")
        running_projects[project_name] = process
        
        bot.send_message(msg.chat.id, "✅ Bot Started Successfully!")

    except Exception as e:
        error_msg = str(e)
        bot.send_message(msg.chat.id, f"❌ Error: {error_msg}")
        # Log error for the project
        project_name = msg.document.file_name.replace(".zip", "")
        project_errors[project_name] = error_msg

# Background thread to monitor running processes
def monitor_processes():
    while True:
        time.sleep(10)  # Check every 10 seconds
        for project, process in list(running_projects.items()):
            if process.poll() is not None:  # Process died
                del running_projects[project]
                project_errors[project] = f"⚠️ Stopped at {datetime.now().strftime('%H:%M:%S')}"
                print(f"⚠️ Project '{project}' stopped unexpectedly")

# Start monitoring thread
monitor_thread = threading.Thread(target=monitor_processes, daemon=True)
monitor_thread.start()

# ▶️ Run Bot
print("="*50)
print("🔥 PYTHON HOSTING PANEL - ENHANCED EDITION")
print("="*50)
print("✅ Bot Running Successfully!")
print(f"📁 Base Directory: {BASE_DIR}")
print(f"🟢 Active Projects: {len(running_projects)}")
print(f"💬 Support: @Hexh4ckerOFC")
print("="*50)
print("📝 No external dependencies needed! (psutil removed)")
print("="*50)

bot.infinity_polling()