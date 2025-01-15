#!/usr/bin/env python3

import os
import discord
import logging
from discord.ext import commands

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Disable other loggers
logging.getLogger('discord').setLevel(logging.ERROR)
logging.getLogger('discord.http').setLevel(logging.ERROR)
logging.getLogger('discord.gateway').setLevel(logging.ERROR)

class CustomBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='$', intents=intents)
        
    async def setup_hook(self):
        """Load cogs when bot starts"""
        try:
            await self.load_extension('cogs.solana')
            logging.info('Successfully loaded cogs.solana')
        except Exception as e:
            logging.error(f'Failed to load cogs.solana: {str(e)}')
            
    async def on_ready(self):
        """Called when bot is ready"""
        logging.info('Bot connected as %s (ID: %s)', self.user, self.user.id)
        logging.info('Connected to guilds:')
        for guild in self.guilds:
            logging.info('- %s (ID: %s)', guild.name, guild.id)
        await self.change_presence(activity=discord.Game(name='$<token>'))
        logging.info('Bot is ready!')

def main():
    """Main entry point"""
    # Get token from environment variable
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logging.error('No token found in environment variables')
        return
        
    # Create and start bot
    logging.info('Starting bot...')
    bot = CustomBot()
    bot.run(token, log_handler=None)

if __name__ == "__main__":
    main()