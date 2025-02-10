import os
import sys
import discord
from discord.ext import commands
import logging
import traceback
from dotenv import load_dotenv
import aiohttp

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

class MemeWatchBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True
        
        super().__init__(command_prefix=['$', '!'], intents=intents)
        self.session = None
        
        # Placeholder for database initialization
        self.db = None  # Replace with actual database initialization
        
    async def setup_hook(self):
        """Load cogs and setup bot"""
        try:
            self.session = aiohttp.ClientSession()
            logger.info("Created aiohttp session")
            
            # Load cogs with better error handling
            cogs = ['solana']
            for cog in cogs:
                try:
                    logger.info(f"Attempting to load {cog}")
                    await self.load_extension(f'cogs.{cog}')
                    logger.info(f"Successfully loaded {cog}")
                except Exception as e:
                    logger.error(f"Failed to load {cog}: {str(e)}")
                    logger.error(traceback.format_exc())
            
            logger.info("Bot setup complete")
        except Exception as e:
            logger.error(f"Error in setup_hook: {str(e)}")
            logger.error(traceback.format_exc())

    async def close(self):
        """Cleanup on bot shutdown"""
        if self.session:
            await self.session.close()
        await super().close()

    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f'Logged in as {self.user.name}')
        logger.info(f'Bot ID: {self.user.id}')
        logger.info(f'Discord.py Version: {discord.__version__}')
        
        # Log loaded cogs
        loaded_cogs = [cog for cog in self.cogs]
        logger.info(f'Loaded cogs: {loaded_cogs}')
        
        # Log connected servers
        for guild in self.guilds:
            logger.info(f'Connected to server: {guild.name} (ID: {guild.id})')
        
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="memecoins 👀"
        ))

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

    async def on_command_error(self, ctx, error):
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
        bot = MemeWatchBot()
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
