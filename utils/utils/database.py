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
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Database setup error: {e}")
