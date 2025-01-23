import os
import sys
import discord
from discord.ext import commands
import logging
import traceback
from dotenv import load_dotenv
import aiohttp
from utils.database import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('bot')

# Load environment variables
load_dotenv()

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class MemeWatchBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(command_prefix='$', intents=intents)
        self.db = DatabaseManager()
        self.session = None
        
    async def setup_hook(self):
        """Load cogs and setup bot"""
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('__'):  # Skip __init__.py
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    logger.info(f"Loaded {filename}")
                except Exception as e:
                    logger.error(f"Failed to load {filename}: {str(e)}")
                    logger.error(traceback.format_exc())

    async def close(self):
        """Cleanup on bot shutdown"""
        if self.session:
            await self.session.close()
        await super().close()

bot = MemeWatchBot()

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name}')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="memecoins 👀"
    ))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Please wait {error.retry_after:.1f}s before using this command again.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}")
    else:
        logger.error(f"Command error in {ctx.command}: {str(error)}")
        logger.error(traceback.format_exc())
        await ctx.send("❌ An error occurred while processing your command.")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
        
    # Process commands
    await bot.process_commands(message)

if __name__ == "__main__":
    try:
        bot.run(os.getenv('DISCORD_TOKEN'))
    except Exception as e:
        logger.critical(f"Failed to start bot: {str(e)}")
        logger.critical(traceback.format_exc())
