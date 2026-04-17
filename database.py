import os
import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager
from threading import Lock

DB_FILE = os.path.join(os.path.dirname(__file__), "parking_orders.db")
_db_lock = Lock()

def init_database():
    """Initialize the database with required tables."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate TEXT UNIQUE NOT NULL,
                name TEXT,
                surname TEXT,
                start_datetime TIMESTAMP NOT NULL,
                end_datetime TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    logging.info("Database initialized successfully")

@contextmanager
def get_connection():
    """Thread-safe database connection context manager."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row  # Enable dict-like row access
    try:
        yield conn
    finally:
        conn.close()

def update_order_status(plate: str, status: str) -> bool:
    """Update order status in the database."""
    with _db_lock:
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE orders
                    SET status = ?, updated_at = ?
                    WHERE plate = ?
                ''', (status, datetime.now(), plate))

                if cursor.rowcount == 0:
                    logging.warning(f"No order found for plate: {plate}")
                    return False

                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Failed to update status: {e}")
            return False

def get_order_status(plate: str) -> str | None:
    """Get the current status of an order by plate number."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT status FROM orders WHERE plate = ?', (plate,))
            row = cursor.fetchone()
            return row['status'] if row else None
    except Exception as e:
        logging.error(f"Failed to get status: {e}")
        return None

def create_order(name: str, surname: str, plate: str, start_datetime: datetime, end_datetime: datetime) -> bool:
    """Create a new parking order."""
    with _db_lock:
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO orders (name, surname, plate, start_datetime, end_datetime, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                ''', (name, surname, plate, start_datetime, end_datetime, datetime.now(), datetime.now()))
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Failed to create order: {e}")
            return False

def get_order(plate: str) -> dict | None:
    """Get full order details by plate number."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM orders WHERE plate = ?', (plate,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logging.error(f"Failed to get order: {e}")
        return None

# Initialize database on module import
init_database()