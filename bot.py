import discord
from discord.ext import commands
import logging
import os
from dotenv import load_dotenv
from utils.database import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('bot')

# Load environment variables
load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='$', intents=intents)

# Initialize database
db = DatabaseManager()

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name}')
    
    # Load all cogs
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                logger.info(f'Loaded {filename}')
            except Exception as e:
                logger.error(f'Failed to load {filename}: {str(e)}')

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Please wait {error.retry_after:.1f}s before using this command again.")
    else:
        logger.error(f"Unhandled error: {str(error)}")
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
