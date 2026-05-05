import sqlite3
import os

DB_NAME = "homework.db"

def get_connection():
    """Helper function to get a database connection."""
    return sqlite3.connect(DB_NAME)

def setup_database():
    """Creates the 'tasks' table if it doesn't already exist."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # We use IF NOT EXISTS so this safely runs every time the bot starts
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'duration' not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN duration INTEGER DEFAULT 1")
    if 'notification_time' not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN notification_time TEXT")
    if 'notified' not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN notified INTEGER DEFAULT 0")
        
    conn.commit()
    conn.close()

def add_task(user_id, subject, description, due_date, duration=1, notification_time=None):
    """Inserts a new homework task into the database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO tasks (user_id, subject, description, due_date, duration, notification_time, notified)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    ''', (user_id, subject, description, due_date, duration, notification_time))
    
    task_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    return task_id

def get_tasks(user_id):
    """Fetches all pending tasks for a specific user ID."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # We only get tasks that belong to the user asking for them
    cursor.execute('''
        SELECT id, subject, description, due_date, status 
        FROM tasks 
        WHERE user_id = ? AND status = 'pending'
    ''', (user_id,))
    
    # Fetch all matching rows
    tasks = cursor.fetchall()
    conn.close()
    
    return tasks

def get_pending_notifications():
    """Fetches tasks that haven't been notified yet."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, user_id, subject, description, due_date, notification_time 
        FROM tasks 
        WHERE status = 'pending' AND notified = 0 AND notification_time IS NOT NULL
    ''')
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def mark_task_notified(task_id):
    """Marks a task as notified."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET notified = 1 WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    
def get_upcoming_notifications(user_id):
    """Fetches upcoming notifications for a specific user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, subject, description, notification_time 
        FROM tasks 
        WHERE user_id = ? AND status = 'pending' AND notified = 0 AND notification_time IS NOT NULL
        ORDER BY notification_time ASC
    ''')
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def mark_task_completed(task_id, user_id):
    """Marks a task as completed so it no longer shows up in pending lists."""
    conn = get_connection()
    cursor = conn.cursor()
    # Ensure they can only complete their own tasks
    cursor.execute("UPDATE tasks SET status = 'completed' WHERE id = ? AND user_id = ?", (task_id, user_id))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0
