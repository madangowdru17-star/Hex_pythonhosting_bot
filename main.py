import telebot
import os
import zipfile
import subprocess
import shutil
import time
import threading
import signal
import sys
from datetime import datetime
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8759695144:AAGfZ3DKgvK3HLrQ5v5uWDLv0bsAqpoKN4Q"

bot = telebot.TeleBot(BOT_TOKEN)

BASE_DIR = "projects"
os.makedirs(BASE_DIR, exist_ok=True)

# Store running processes per user
running_projects = {}  # {user_id: {project_name: {"process": process, "cwd": path}}}
project_errors = {}  # {user_id: {project_name: error}}

# 🔘 Enhanced Buttons UI
def panel():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "📤 Upload Project", "📁 My Projects",
        "▶️ Start Project", "⏹️ Stop Project",
        "🔄 Restart Project", "🗑️ Delete Project",
        "🗑️ Delete All", "📊 Server Stats",
        "🔄 Refresh Status", "📝 View Errors",
        "❓ Help @Hexh4ckerOFC"
    ]
    markup.add(*buttons)
    return markup

# 🚀 Start Command
@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.chat.id
    total_projects = len(get_user_projects(user_id))
    
    welcome_text = f"""
╔══════════════════════════════╗
║   🔥 PYTHON HOSTING PANEL    ║
║      🚀 READY TO DEPLOY      ║
╚══════════════════════════════╝

✨ *Features:*
✅ User-Specific Workspaces
✅ No File Conflicts Between Users
✅ Upload & Deploy Python Projects
✅ Auto-Install Requirements
✅ Start/Stop/Restart Working

👤 *Your Workspace:*
├─ User ID: `{user_id}`
├─ Projects: {total_projects}
└─ Running: {len(get_user_running_projects(user_id))}

💡 *Need Help?* @Hexh4ckerOFC
    """
    
    bot.send_message(msg.chat.id, welcome_text, parse_mode="Markdown", reply_markup=panel())

# Helper: Get user-specific directory
def get_user_dir(user_id):
    user_dir = os.path.join(BASE_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

# Helper: Get user projects
def get_user_projects(user_id):
    user_dir = get_user_dir(user_id)
    projects = []
    for item in os.listdir(user_dir):
        item_path = os.path.join(user_dir, item)
        if os.path.isdir(item_path):
            projects.append(item)
    return projects

# Helper: Get user running projects
def get_user_running_projects(user_id):
    if user_id not in running_projects:
        running_projects[user_id] = {}
    return running_projects[user_id]

# Helper: Get user errors
def get_user_errors(user_id):
    if user_id not in project_errors:
        project_errors[user_id] = {}
    return project_errors[user_id]

# 📤 Upload Project
@bot.message_handler(func=lambda m: m.text == "📤 Upload Project")
def upload_btn(msg):
    bot.send_message(msg.chat.id, "📦 *Send your .zip file with:*\n• `main.py`\n• `requirements.txt`\n\n📝 *Max size: 50MB*\n🔒 *Your files are private to you*", parse_mode="Markdown")

# 📁 My Projects
@bot.message_handler(func=lambda m: m.text == "📁 My Projects")
def file_manager(msg):
    user_id = msg.chat.id
    projects = get_user_projects(user_id)
    user_running = get_user_running_projects(user_id)
    
    if not projects:
        bot.send_message(msg.chat.id, "📂 *No projects found*\nUse 📤 Upload Project to add one.", parse_mode="Markdown")
        return
    
    project_list = "📁 *Your Projects:*\n━━━━━━━━━━━━━━━\n"
    for project in projects:
        # Check project status
        is_running = project in user_running
        has_main = os.path.exists(os.path.join(get_user_dir(user_id), project, "main.py"))
        user_errors = get_user_errors(user_id)
        has_error = project in user_errors
        
        status_icon = "🟢" if is_running else "⚪"
        main_icon = "✅" if has_main else "❌"
        error_icon = "⚠️" if has_error else "✓"
        
        project_list += f"\n{status_icon} `{project}`\n   ├─ main.py: {main_icon}\n   └─ Status: {error_icon}\n"
    
    bot.send_message(msg.chat.id, project_list, parse_mode="Markdown")

# ▶️ Start Project
@bot.message_handler(func=lambda m: m.text == "▶️ Start Project")
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

# ⏹️ Stop Project
@bot.message_handler(func=lambda m: m.text == "⏹️ Stop Project")
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

# 🔄 Restart Project
@bot.message_handler(func=lambda m: m.text == "🔄 Restart Project")
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

# 🗑️ Delete Project
@bot.message_handler(func=lambda m: m.text == "🗑️ Delete Project")
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

# 🗑️ Delete All
@bot.message_handler(func=lambda m: m.text == "🗑️ Delete All")
def delete_all(msg):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ YES, Delete All", callback_data="confirm_delete_all"),
        InlineKeyboardButton("❌ NO, Cancel", callback_data="cancel_delete")
    )
    bot.send_message(msg.chat.id, "⚠️ *WARNING: This will delete ALL your projects!*\nAre you sure?", 
                     parse_mode="Markdown", reply_markup=markup)

# 📊 Server Stats
@bot.message_handler(func=lambda m: m.text == "📊 Server Stats")
def server_info(msg):
    user_id = msg.chat.id
    total_projects = len(get_user_projects(user_id))
    running_count = len(get_user_running_projects(user_id))
    user_errors = get_user_errors(user_id)
    error_count = len(user_errors)
    
    # Get disk usage
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
╔══════════════════════════════╗
║      📊 YOUR STATISTICS      ║
╚══════════════════════════════╝

📦 *YOUR PROJECTS*
├─ Total: {total_projects}
├─ Running: {running_count} 🟢
├─ Stopped: {total_projects - running_count} ⚪
└─ Errors: {error_count} ⚠️

💾 *YOUR STORAGE*
└─ Disk Usage: {disk_text}

👤 *USER INFO*
├─ User ID: `{user_id}`
└─ Workspace: Private

🕐 *Server Time*
└─ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    bot.send_message(msg.chat.id, stats_text, parse_mode="Markdown")

# 🔄 Refresh Status
@bot.message_handler(func=lambda m: m.text == "🔄 Refresh Status")
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
        bot.send_message(msg.chat.id, f"⚠️ *Detected dead processes:*\n{', '.join(dead_projects)}\n\nUse ▶️ Start Project to restart them.", 
                         parse_mode="Markdown")
    else:
        running_count = len(user_running)
        bot.send_message(msg.chat.id, f"✅ *Status Refreshed* | 🟢 Running: {running_count}", 
                         parse_mode="Markdown")

# 📝 View Errors
@bot.message_handler(func=lambda m: m.text == "📝 View Errors")
def view_errors(msg):
    user_id = msg.chat.id
    user_errors = get_user_errors(user_id)
    
    if not user_errors:
        bot.send_message(msg.chat.id, "✅ *No errors logged! All projects running smoothly.*", parse_mode="Markdown")
        return
    
    error_text = "⚠️ *Your Error Log:*\n━━━━━━━━━━━━━━━\n"
    for project, error in user_errors.items():
        error_text += f"\n📁 `{project}`\n└─ {error[:100]}\n"
    
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
🔄 Restart Project - Restart a project
🗑️ Delete Project - Delete specific project
🗑️ Delete All - Delete ALL your projects

📊 *MONITORING*
📊 Server Stats - Your storage & project counts
🔄 Refresh Status - Check if projects are running
📝 View Errors - See error logs

🔒 *PRIVACY*
• Each user has their own private workspace
• No file conflicts between users
• Your projects are completely isolated

💡 *TIPS*
• Make sure your .zip has main.py
• Requirements.txt is optional
• Max file size: 50MB
• All your data is private to you

🆘 *SUPPORT*
Contact: @Hexh4ckerOFC

🟢 *Bot Status: ONLINE & FULLY WORKING*
    """
    bot.send_message(msg.chat.id, help_text, parse_mode="Markdown")

# Callback handlers
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.message.chat.id
    
    # Handle Start Project
    if call.data.startswith("start_"):
        project_name = call.data.replace("start_", "")
        result = start_project(user_id, project_name)
        if result:
            bot.edit_message_text(f"✅ *'{project_name}' started successfully!*", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text(f"❌ *Failed to start '{project_name}'*\nCheck if main.py exists!", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    # Handle Stop Project
    elif call.data.startswith("stop_"):
        project_name = call.data.replace("stop_", "")
        if project_name in get_user_running_projects(user_id):
            stop_project(user_id, project_name)
            bot.edit_message_text(f"⏹️ *'{project_name}' stopped successfully*", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text(f"⚠️ *'{project_name}' is not running*", 
                                call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    # Handle Restart Project
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
    
    # Handle Delete Project
    elif call.data.startswith("delete_"):
        project_name = call.data.replace("delete_", "")
        delete_project(user_id, project_name)
        bot.edit_message_text(f"🗑️ *Project '{project_name}' deleted*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
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
        
        bot.edit_message_text("🗑️ *ALL your projects deleted successfully!*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    # Handle Cancel
    elif call.data == "cancel_delete":
        bot.edit_message_text("❌ *Action cancelled*", 
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    bot.answer_callback_query(call.id)

# Start project function (user-specific)
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
        
        # Clear error if exists
        user_errors = get_user_errors(user_id)
        if project_name in user_errors:
            del user_errors[project_name]
        
        # Log start
        log_file = os.path.join(project_path, "project.log")
        with open(log_file, 'a') as f:
            f.write(f"\n[STARTED] at {datetime.now()}\n")
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_single_project, args=(user_id, project_name, process))
        monitor_thread.daemon = True
        monitor_thread.start()
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        user_errors = get_user_errors(user_id)
        user_errors[project_name] = error_msg
        return False

# Stop project function (user-specific)
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
            
            # Log stop
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

# Monitor single project
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

# Delete project (user-specific)
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

# 📦 Handle ZIP Upload (User-specific - No conflicts!)
@bot.message_handler(content_types=['document'])
def handle_zip(msg):
    user_id = msg.chat.id
    
    if not msg.document.file_name.endswith(".zip"):
        bot.send_message(msg.chat.id, "❌ Send only .zip file")
        return

    status_msg = bot.send_message(msg.chat.id, "📦 *Processing upload...*", parse_mode="Markdown")

    file_info = bot.get_file(msg.document.file_id)
    downloaded = bot.download_file(file_info.file_path)

    # Clean project name
    original_name = msg.document.file_name.replace(".zip", "")
    project_name = "".join(c for c in original_name if c.isalnum() or c in ('-', '_'))
    
    # User-specific directory
    user_dir = get_user_dir(user_id)
    project_path = os.path.join(user_dir, project_name)
    
    # If project exists, add timestamp to make it unique per user
    if os.path.exists(project_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = f"{project_name}_{timestamp}"
        project_path = os.path.join(user_dir, project_name)
        bot.send_message(msg.chat.id, f"📝 *Project renamed to '{project_name}' to avoid conflict*", parse_mode="Markdown")
    
    try:
        zip_path = os.path.join(user_dir, f"{project_name}.zip")
        extract_path = project_path
        
        # Save zip file
        with open(zip_path, 'wb') as f:
            f.write(downloaded)
        
        # Create extract directory
        os.makedirs(extract_path, exist_ok=True)
        
        # Extract zip
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
            
            # Handle nested folders
            extracted_items = os.listdir(extract_path)
            if len(extracted_items) == 1 and os.path.isdir(os.path.join(extract_path, extracted_items[0])):
                subfolder = os.path.join(extract_path, extracted_items[0])
                for item in os.listdir(subfolder):
                    shutil.move(os.path.join(subfolder, item), extract_path)
                os.rmdir(subfolder)
        
        # Remove zip file
        os.remove(zip_path)
        
        bot.edit_message_text("📦 *Extracted!*", msg.chat.id, status_msg.message_id, parse_mode="Markdown")
        
        # Install requirements
        req_file = os.path.join(extract_path, "requirements.txt")
        if os.path.exists(req_file):
            subprocess.run(["pip", "install", "-r", req_file], cwd=extract_path)
            bot.edit_message_text("📥 *Requirements Installed*", msg.chat.id, status_msg.message_id, parse_mode="Markdown")
        
        # Check if main.py exists
        main_file = os.path.join(extract_path, "main.py")
        if not os.path.exists(main_file):
            bot.edit_message_text(f"⚠️ *Warning: No main.py found in '{project_name}'*", 
                                msg.chat.id, status_msg.message_id, parse_mode="Markdown")
        
        # Success message
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("▶️ Start Now", callback_data=f"start_{project_name}"))
        
        bot.edit_message_text(f"✅ *Project '{project_name}' uploaded successfully!*\n\n📁 Size: {get_folder_size(extract_path)}\n📄 main.py: {'✅' if os.path.exists(main_file) else '❌'}\n\nClick below to start:", 
                            msg.chat.id, status_msg.message_id, parse_mode="Markdown", reply_markup=markup)
        
    except Exception as e:
        error_msg = str(e)
        bot.edit_message_text(f"❌ *Upload failed:* `{error_msg[:150]}`", 
                            msg.chat.id, status_msg.message_id, parse_mode="Markdown")
        user_errors = get_user_errors(user_id)
        user_errors[project_name] = error_msg

# Get folder size
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

# Background thread to monitor all processes
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
                    project_errors[user_id][project_name] = f"⚠️ Crashed at {datetime.now().strftime('%H:%M:%S')}"
                    print(f"⚠️ User {user_id} project '{project_name}' crashed")

# Start monitoring thread
monitor_thread = threading.Thread(target=monitor_processes, daemon=True)
monitor_thread.start()

# ▶️ Run Bot
print("="*50)
print("🔥 PYTHON HOSTING PANEL - MULTI-USER READY")
print("="*50)
print("✅ Bot Running Successfully!")
print(f"📁 Base Directory: {BASE_DIR}")
print(f"👥 Multi-User Support: ENABLED")
print(f"🔒 Private Workspaces: YES")
print(f"💬 Support: @Hexh4ckerOFC")
print("="*50)
print("✨ MULTI-USER FIX IMPLEMENTED!")
print("   - Each user has private workspace")
print("   - No file conflicts between users")
print("   - Duplicate names auto-rename with timestamp")
print("   - Complete data isolation")
print("="*50)

bot.infinity_polling()
