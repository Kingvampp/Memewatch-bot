import sqlite3
import logging
from datetime import datetime, timezone

class DatabaseManager:
    def __init__(self, db_path='token_scans.db'):
        self.db_path = db_path
        self.setup_database()

    def setup_database(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute('''CREATE TABLE IF NOT EXISTS token_scans
                            (token_address TEXT, 
                             first_scanner TEXT, 
                             scan_time TIMESTAMP,
                             first_mcap REAL, 
                             guild_id TEXT,
                             PRIMARY KEY (token_address, guild_id))''')
                
                # Price history table
                c.execute('''CREATE TABLE IF NOT EXISTS price_history
                            (token_address TEXT,
                             price REAL,
                             mcap REAL,
                             timestamp TIMESTAMP,
                             PRIMARY KEY (token_address, timestamp))''')
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Database setup error: {e}")

    async def get_scan_info(self, token_address, guild_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute('''SELECT first_scanner, scan_time, first_mcap 
                            FROM token_scans 
                            WHERE token_address = ? AND guild_id = ?''', 
                            (token_address, str(guild_id)))
                return c.fetchone()
        except sqlite3.Error as e:
            logging.error(f"Database query error: {e}")
            return None

    async def save_scan(self, token_address, scanner_id, mcap, guild_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute('''INSERT OR IGNORE INTO token_scans 
                            (token_address, first_scanner, scan_time, first_mcap, guild_id)
                            VALUES (?, ?, ?, ?, ?)''',
                            (token_address, str(scanner_id), 
                             datetime.now(timezone.utc).timestamp(),
                             mcap, str(guild_id)))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logging.error(f"Database insert error: {e}")
            return False

    async def update_price_history(self, token_address, price, mcap):
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute('''INSERT INTO price_history 
                            (token_address, price, mcap, timestamp)
                            VALUES (?, ?, ?, ?)''',
                            (token_address, price, mcap, 
                             datetime.now(timezone.utc).timestamp()))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logging.error(f"Price history update error: {e}")
            return False
