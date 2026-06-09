import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "hitl.db"
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_file TEXT NOT NULL,
            original_content TEXT,
            proposed_content TEXT NOT NULL,
            reasoning TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_transaction(agent_name: str, action_type: str, target_file: str, 
                    proposed_content: str, original_content: str = None, 
                    reasoning: str = None) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO transactions 
        (agent_name, action_type, target_file, original_content, proposed_content, reasoning, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
    ''', (agent_name, action_type, target_file, original_content, proposed_content, reasoning))
    tx_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return tx_id

def get_pending_transactions() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM transactions WHERE status = "pending" ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_transaction(tx_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM transactions WHERE id = ?', (tx_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_transaction_status(tx_id: int, status: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE transactions SET status = ? WHERE id = ?', (status, tx_id))
    conn.commit()
    conn.close()

# Initialize DB on import
init_db()
