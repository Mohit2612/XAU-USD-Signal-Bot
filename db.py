import sqlite3
import os
from datetime import datetime
import json

DB_PATH = os.path.join(os.path.dirname(__file__), "market_data.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Create table for candles
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS candles (
        symbol TEXT,
        interval TEXT,
        timestamp DATETIME,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        UNIQUE(symbol, interval, timestamp)
    )
    ''')
    conn.commit()
    conn.close()

def save_candles(symbol, interval, candles):
    """
    Save a list of candles to the database.
    Candles format: [{"datetime": "2023-10-27 10:00:00", "open": 1980.5, ...}, ...]
    """
    if not candles:
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    records = []
    for c in candles:
        # Some APIs return timestamp as string, some as datetime object.
        ts = c.get("datetime") or c.get("timestamp")
        
        # Ensure it's a string for SQLite
        if isinstance(ts, datetime):
            ts = ts.strftime("%Y-%m-%d %H:%M:%S")
            
        records.append((
            symbol, 
            interval, 
            ts, 
            float(c.get("open", 0)), 
            float(c.get("high", 0)), 
            float(c.get("low", 0)), 
            float(c.get("close", 0)), 
            float(c.get("volume", 0))
        ))
        
    cursor.executemany('''
    INSERT OR REPLACE INTO candles (symbol, interval, timestamp, open, high, low, close, volume)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', records)
    
    conn.commit()
    conn.close()

def get_historical_candles(symbol, interval, limit=1000):
    """
    Retrieve historical candles from the database, ordered by timestamp ascending.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT timestamp as datetime, open, high, low, close, volume 
    FROM candles 
    WHERE symbol = ? AND interval = ? 
    ORDER BY timestamp DESC 
    LIMIT ?
    ''', (symbol, interval, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    # Reverse to get chronological order
    candles = []
    for row in reversed(rows):
        candles.append(dict(row))
        
    return candles

# Initialize the DB when the module is imported
init_db()
