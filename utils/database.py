import sqlite3
import logging
import os
from datetime import datetime, timezone

class DatabaseManager:
    def __init__(self, db_path='token_scans.db'):
        self.db_path = db_path
        # Ensure database directory exists
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.setup_database()
        self.logger = logging.getLogger('database')

    def setup_database(self):
        """Initialize database tables"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                # Token scans table
                c.execute('''CREATE TABLE IF NOT EXISTS token_scans
                            (token_address TEXT, 
                             first_scanner TEXT, 
                             scan_time TIMESTAMP,
                             first_mcap REAL, 
                             guild_id TEXT,
                             PRIMARY KEY (token_address, guild_id))''')
                conn.commit()
        except sqlite3.Error as e:
            self.logger.error(f"Database setup error: {e}")
            raise

    async def save_scan(self, token_address, scanner_id, mcap, guild_id):
        """Save token scan information"""
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
            self.logger.error(f"Save scan error: {e}")
            return False

    async def get_scan_info(self, token_address, guild_id):
        """Get first scan information for a token in a guild"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute('''SELECT first_scanner, scan_time, first_mcap 
                            FROM token_scans 
                            WHERE token_address = ? AND guild_id = ?''', 
                            (token_address, str(guild_id)))
                return c.fetchone()
        except sqlite3.Error as e:
            self.logger.error(f"Get scan info error: {e}")
            return None