import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Import our custom database functions
import database

# Load environment variables from the .env file
load_dotenv()

# Enable basic logging to help us see errors in the console
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def send_notification(context: ContextTypes.DEFAULT_TYPE):
    """Job function to send a task reminder."""
    job = context.job
    task_id = job.data["task_id"]
    user_id = job.data["user_id"]
    subject = job.data["subject"]
    description = job.data["description"]
    
    # Send the reminder
    message = f"🔔 *REMINDER FOR: {subject}*\n\nIt's time to start working on your homework: {description}!"
    await context.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
    
    # Mark as notified
    database.mark_task_notified(task_id)

def schedule_notification(job_queue, task_id, user_id, subject, description, notification_time_str):
    """Helper to schedule a notification job."""
    try:
        # Convert naive stored time to local timezone-aware time
        notif_time = datetime.fromisoformat(notification_time_str).astimezone()
        now_time = datetime.now().astimezone()
        # We need to make sure the time is valid and in the future
        if notif_time > now_time:
            job_queue.run_once(
                send_notification,
                when=notif_time,
                data={
                    "task_id": task_id,
                    "user_id": user_id,
                    "subject": subject,
                    "description": description
                },
                name=f"task_{task_id}"
            )
    except Exception as e:
        logging.error(f"Failed to schedule notification for task {task_id}: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    user = update.effective_user
    welcome_message = (
        f"Hi {user.first_name}! I'm your Homework Planner AI Bot. 📚\n\n"
        f"I can help you keep track of your assignments.\n"
        f"Type /help to see what I can do!"
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /help command."""
    help_text = (
        "Here are my available commands:\n\n"
        "/start - Greet the bot\n"
        "/help - Show this message\n"
        "/add - Add a task (Format: /add Subject | Description | YYYY-MM-DD HH:MM | Hours)\n"
        "/list - Show your pending homework tasks\n"
        "/done - Mark a task as completed\n"
        "/upcoming - Show your scheduled reminders"
    )
    await update.message.reply_text(help_text)

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles parsing and saving a new task."""
    user_id = update.effective_user.id
    user_input = " ".join(context.args)
    
    if not user_input or "|" not in user_input:
        await update.message.reply_text("Please use the format: /add Subject | Description | YYYY-MM-DD HH:MM | Hours")
        return
        
    try:
        parts = [part.strip() for part in user_input.split("|")]
        
        if len(parts) == 4:
            subject, description, due_date_str, duration_str = parts
            try:
                duration = int(duration_str)
            except ValueError:
                await update.message.reply_text("Duration must be a number (hours).")
                return
        elif len(parts) == 3:
            subject, description, due_date_str = parts
            duration = 1
        else:
            await update.message.reply_text("Oops! Make sure you provide 3 or 4 parts separated by '|'.\nFormat: /add Subject | Description | YYYY-MM-DD HH:MM | Hours")
            return
            
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d %H:%M")
        except ValueError:
            await update.message.reply_text("Invalid date format. Please use YYYY-MM-DD HH:MM (e.g., 2026-04-10 15:30)")
            return
            
        notification_time = due_date - timedelta(hours=duration)
        
        # We must insert due_date in a format we can parse later if needed, isoformat works.
        task_id = database.add_task(user_id, subject, description, due_date.isoformat(), duration, notification_time.isoformat())
        
        if context.job_queue:
            schedule_notification(context.job_queue, task_id, user_id, subject, description, notification_time.isoformat())
        
        await update.message.reply_text(f"✅ Saved! {subject}: {description} (Due: {due_date.strftime('%Y-%m-%d %H:%M')})\n⏳ I will remind you on {notification_time.strftime('%Y-%m-%d %H:%M')} ({duration} hours before).")
        
    except Exception as e:
        logging.error(f"Error adding task: {e}")
        await update.message.reply_text("Sorry, there was an unknown error saving your task.")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches and displays the user's saved tasks."""
    user_id = update.effective_user.id
    tasks = database.get_tasks(user_id)
    
    if not tasks:
        await update.message.reply_text("You have no pending homework tasks! 🎉")
        return
        
    message = "📝 *Your Homework Tasks:*\n\n"
    for task in tasks:
        task_id, subject, description, due_date, status = task
        try:
            dt = datetime.fromisoformat(due_date)
            formatted_date = dt.strftime('%Y-%m-%d %H:%M')
        except ValueError:
            # fallback to whatever was exactly in db
            formatted_date = due_date
        message += f"• **[ID: {task_id}]** *{subject}*: {description} (Due: {formatted_date})\n"
        
    await update.message.reply_text(message, parse_mode='Markdown')

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /done command to mark a task as completed."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Please provide the ID of the task. (e.g., /done 3)")
        return
        
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("The Task ID must be a number! (e.g., /done 3)")
        return
        
    success = database.mark_task_completed(task_id, user_id)
    
    if success:
        await update.message.reply_text(f"Great job! 🎉 Task #{task_id} has been marked as completed.")
    else:
        await update.message.reply_text(f"Could not find a pending task with ID #{task_id}.")

async def upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches and displays upcoming scheduled notifications."""
    user_id = update.effective_user.id
    tasks = database.get_upcoming_notifications(user_id)
    
    if not tasks:
        await update.message.reply_text("You have no upcoming notifications scheduled.")
        return
        
    message = "🔔 *Your Scheduled Reminders:*\n\n"
    for task in tasks:
        task_id, subject, description, notification_time = task
        try:
            dt = datetime.fromisoformat(notification_time)
            formatted_date = dt.strftime('%Y-%m-%d %H:%M')
        except ValueError:
            formatted_date = notification_time
        message += f"• *{subject}* remind at: {formatted_date}\n"
        
    await update.message.reply_text(message, parse_mode='Markdown')

if __name__ == '__main__':
    database.setup_database()
    
    TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
    if not TOKEN:
        print("ERROR: Could not find TELEGRAM_TOKEN. Make sure you set it in your .env file!")
        exit(1)
        
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Restore pending notifications from database
    if app.job_queue:
        print("Initializing JobQueue and restoring pending notifications...")
        pending_notifications = database.get_pending_notifications()
        for row in pending_notifications:
            t_id, u_id, subj, desc, d_date, n_time = row
            logging.info(f"Restoring notification for task {t_id} at {n_time}")
            schedule_notification(app.job_queue, t_id, u_id, subj, desc, n_time)
            
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("tasks", list_tasks))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("upcoming", upcoming))
    
    print("Bot is starting... Press Ctrl+C to stop.")
    app.run_polling()
