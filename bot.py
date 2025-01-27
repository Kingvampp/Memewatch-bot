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
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    logger.critical("No Discord token found in environment variables!")
    sys.exit(1)

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class MemeWatchBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True
        
        super().__init__(command_prefix=['$', '!'], intents=intents)
        self.db = DatabaseManager()
        self.session = None
        
    async def setup_hook(self):
        """Load cogs and setup bot"""
        self.session = aiohttp.ClientSession()
        
        # Load cogs with better error handling
        cogs = ['solana']  # Remove analyzer cog temporarily
        for cog in cogs:
            try:
                await self.load_extension(f'cogs.{cog}')
                logger.info(f"Loaded {cog}")
            except Exception as e:
                logger.error(f"Failed to load {cog}: {str(e)}")
                logger.error(traceback.format_exc())
                
        logger.info("Bot setup complete")

    async def close(self):
        """Cleanup on bot shutdown"""
        if self.session:
            await self.session.close()
        await super().close()

    async def on_message(self, message):
        """Handle message events"""
        if message.author.bot:
            return
            
        # Add debug logging
        if message.content.startswith(('$', '!')):
            logger.info(f"Command received: {message.content} from {message.author.name}")
            
        try:
            await self.process_commands(message)
        except Exception as e:
            logger.error(f"Error processing command: {str(e)}")
            logger.error(traceback.format_exc())

bot = MemeWatchBot()

@bot.event
async def on_ready():
    """Called when bot is ready"""
    logger.info(f'Logged in as {bot.user.name}')
    logger.info(f'Bot ID: {bot.user.id}')
    logger.info(f'Discord.py Version: {discord.__version__}')
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="memecoins 👀"
    ))
    
    # Log which servers the bot is in
    for guild in bot.guilds:
        logger.info(f'Connected to server: {guild.name} (ID: {guild.id})')

@bot.event
async def on_command_error(ctx, error):
    """Global error handler for commands"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Please wait {error.retry_after:.1f}s before using this command again.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}")
    else:
        error_msg = f"Command error in {ctx.command}: {str(error)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        await ctx.send("❌ An error occurred while processing your command.")

def run_bot():
    """Run the bot with error handling"""
    try:
        logger.info("Starting bot...")
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        logger.critical("Failed to login. Check your token!")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}")
        logger.critical(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    run_bot()
