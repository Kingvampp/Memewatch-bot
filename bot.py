#!/usr/bin/env python3

import os
import logging
import discord
import asyncio
import traceback
from discord.ext import commands
from dotenv import load_dotenv
from cogs.analyzer import AnalyzerCog
import requests
from datetime import datetime
import re  # Add this import for regex

# Configure logging
logger = logging.getLogger('bot')
logger.setLevel(logging.INFO)

# Create handlers
stream_handler = logging.StreamHandler()
file_handler = logging.FileHandler('bot.log', mode='a', encoding='utf-8')
error_handler = logging.FileHandler('error.log', mode='a', encoding='utf-8')

# Set format
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
stream_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)
error_handler.setFormatter(formatter)

# Set levels
error_handler.setLevel(logging.ERROR)

# Add handlers
logger.addHandler(stream_handler)
logger.addHandler(file_handler)
logger.addHandler(error_handler)

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
if not DISCORD_TOKEN:
    logger.error("No Discord token found in environment variables")
    exit(1)

CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')

class CryptoBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix='$', intents=intents)
        self._background_tasks = set()
        
    def create_background_task(self, coro):
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task
        
    async def setup_hook(self):
        logger.info("Setting up bot hooks...")
        try:
            await self.add_cog(AnalyzerCog(self))
            logger.info("Added AnalyzerCog successfully")
            
            # Start heartbeat task
            self.create_background_task(self._heartbeat())
            logger.info("Started heartbeat task")
            
            # Start presence refresh task
            self.create_background_task(self._refresh_presence())
            logger.info("Started presence refresh task")
            
        except Exception as e:
            logger.error(f"Error in setup_hook: {str(e)}")
            logger.error(traceback.format_exc())
            
    async def on_ready(self):
        """Called when the bot is ready and connected to Discord"""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        
        try:
            # Set initial presence
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name="memecoin prices | $symbol"
            )
            await self.change_presence(
                status=discord.Status.online,
                activity=activity
            )
            logger.info("Set initial presence")
            
        except Exception as e:
            logger.error(f"Error setting presence: {str(e)}")
            logger.error(traceback.format_exc())
            
    async def _refresh_presence(self):
        """Task to periodically refresh bot's presence"""
        await self.wait_until_ready()
        try:
            while not self.is_closed():
                try:
                    activity = discord.Activity(
                        type=discord.ActivityType.watching,
                        name="crypto charts | !analyze"
                    )
                    await self.change_presence(
                        status=discord.Status.online,
                        activity=activity
                    )
                    logger.info("Refreshed bot presence")
                except Exception as e:
                    logger.error(f"Error refreshing presence: {str(e)}")
                
                await asyncio.sleep(300)  # Refresh every 5 minutes
                
        except asyncio.CancelledError:
            logger.info("Presence refresh task cancelled")
        except Exception as e:
            logger.error(f"Error in presence refresh task: {str(e)}")
            if not self.is_closed():
                self.create_background_task(self._refresh_presence())
                
    async def _heartbeat(self):
        """Task to monitor bot's connection status"""
        await self.wait_until_ready()
        try:
            while not self.is_closed():
                try:
                    # Log connection status
                    is_connected = self.is_ws_ratelimited() is False and self.is_connected()
                    ws_state = "Connected" if is_connected else "Disconnected"
                    logger.info(f"WebSocket state: {ws_state}")
                    
                    # Log status in each guild
                    for guild in self.guilds:
                        me = guild.me
                        logger.info(f"Status in {guild.name}: {me.status}, "
                                  f"Permissions: {me.guild_permissions.value}")
                    
                    # Check if bot needs to reconnect
                    if not is_connected and not self.is_closed():
                        logger.warning("Bot appears to be disconnected, attempting to recover...")
                        try:
                            await self.connect(reconnect=True)
                        except Exception as e:
                            logger.error(f"Failed to recover connection: {str(e)}")
                            
                except Exception as e:
                    logger.error(f"Error in heartbeat: {str(e)}")
                    
                await asyncio.sleep(60)  # Check every minute
                
        except asyncio.CancelledError:
            logger.info("Heartbeat task cancelled")
        except Exception as e:
            logger.error(f"Error in heartbeat task: {str(e)}")
            if not self.is_closed():
                self.create_background_task(self._heartbeat())
                
    async def close(self):
        """Clean up resources when bot is shutting down"""
        logger.info("Bot is shutting down...")
        try:
            # Cancel background tasks
            for task in self._background_tasks:
                task.cancel()
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            
            # Close Discord connection
            await super().close()
            
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}")
            logger.error(traceback.format_exc())

    async def on_message(self, message):
        # Ignore messages from the bot itself
        if message.author == self.user:
            return

        # Get the message content
        content = message.content.strip()

        # Handle token lookups
        if content.startswith('$') or is_contract_address(content):
            query = content[1:].strip() if content.startswith('$') else content
            if query:
                async with message.channel.typing():
                    response = get_token_info(query)
                    await message.channel.send(response)
            else:
                await message.channel.send("Please provide a token name or contract address. Example: `$pepe` or `$0x...`")
        
        # Make sure to process commands from AnalyzerCog
        await self.process_commands(message)

def is_contract_address(text):
    # ETH address pattern
    eth_pattern = r'^0x[a-fA-F0-9]{40}$'
    # SOL address pattern (base58 encoded, 32-44 chars)
    sol_pattern = r'^[1-9A-HJ-NP-Za-km-z]{32,44}$'
    
    return bool(re.match(eth_pattern, text)) or bool(re.match(sol_pattern, text))

def get_token_info(query):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'accept': 'application/json'
        }

        # First try DEXScreener API
        dex_url = f"https://api.dexscreener.com/latest/dex/search?q={query}"
        dex_response = requests.get(dex_url, headers=headers)
        dex_data = dex_response.json()

        if not dex_data.get('pairs') or len(dex_data['pairs']) == 0:
            return f"Token '{query}' not found on DEXScreener."

        # Get the first pair with good liquidity
        pair = None
        for p in dex_data['pairs']:
            if float(p.get('liquidity', {}).get('usd', 0)) > 1000:  # Min $1000 liquidity
                pair = p
                break
        
        if not pair:
            pair = dex_data['pairs'][0]  # Fallback to first pair if none with good liquidity

        # Extract basic token info
        token_symbol = pair.get('baseToken', {}).get('symbol', '???')
        chain = pair.get('chainId', 'unknown').upper()
        dex_id = pair.get('dexId', 'Unknown')
        contract = pair.get('baseToken', {}).get('address', '')

        # Calculate price and changes
        price_usd = float(pair.get('priceUsd', 0))
        price_str = f"${price_usd:.12f}" if price_usd < 0.000001 else f"${price_usd:.8f}"
        h24_change = float(pair.get('priceChange', {}).get('h24', 0))
        h1_change = float(pair.get('priceChange', {}).get('h1', 0))

        # Get liquidity and volume
        liquidity = float(pair.get('liquidity', {}).get('usd', 0))
        liq_ratio = float(pair.get('liquidity', {}).get('ratio', 0))
        volume_h24 = float(pair.get('volume', {}).get('h24', 0))
        volume_h1 = float(pair.get('volume', {}).get('h1', 0))

        # Format message
        message = [
            f"```ml",
            f"{token_symbol} [{h24_change:+.1f}%] - {chain} ↗\n",
            f"💰 {chain} @ {dex_id}",
            f"💵 USD: {price_str}",
        ]

        # Add liquidity
        message.append(f"💧 Liq: ${liquidity:,.0f} [x{liq_ratio:.1f}]")

        # Add volume and age
        vol_age = f"📊 Vol: ${volume_h24:,.0f}"
        if pair.get('pairCreatedAt'):
            created_at = datetime.fromtimestamp(int(pair['pairCreatedAt'])/1000)
            hours_old = int((datetime.utcnow() - created_at).total_seconds() / 3600)
            vol_age += f" ⏰ Age: {hours_old}h"
        message.append(vol_age)

        # Add 1H stats
        message.append(f"📈 1H: {h1_change:+.1f}% • ${volume_h1:,.0f}")

        # Add trading history
        if pair.get('txns'):
            buys = pair['txns'].get('h24', {}).get('buys', 0)
            sells = pair['txns'].get('h24', {}).get('sells', 0)
            total = buys + sells
            buy_percentage = (buys/total * 100) if total > 0 else 0
            message.append(f"🔄 TH: {buys}•{sells}•{total} [{buy_percentage:.0f}%]")

        # Add contract
        message.append(f"\n{contract}")

        # Add DEX links
        if chain == "SOLANA":
            message.extend([
                "DEX•Birdeye•Jupiter•Raydium•Orca",
                "Photon•BullX•DexLab•GooseFX"
            ])
        elif chain == "ETHEREUM":
            message.extend([
                "MAE•BAN•BNK•SHU•PEP•MVX•DEX",
                "TRO•STB•PHO•BLX•GMG•EXP•TW"
            ])

        message.append("```")
        return "\n".join(message)

    except requests.exceptions.RequestException as e:
        return f"Network error while fetching token information. Please try again."
    except Exception as e:
        return f"Error fetching token information: {str(e)}"

async def main():
    async with CryptoBot() as bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        # Ensure event loop is closed
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.close()