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
            # Load all cogs
            for cog in ['analyzer', 'security', 'solana']:
                try:
                    await self.load_extension(f"cogs.{cog}")
                    logger.info(f"Loaded {cog} cog successfully")
                except Exception as e:
                    logger.error(f"Failed to load {cog} cog: {str(e)}")
            
            # Start background tasks
            self.bg_task = self.loop.create_task(self._heartbeat())
            self.presence_task = self.loop.create_task(self._refresh_presence())
            logger.info("Started background tasks")
            
        except Exception as e:
            logger.error(f"Error in setup_hook: {str(e)}")
            logger.error(traceback.format_exc())
            
    async def on_error(self, event, *args, **kwargs):
        """Global error handler for all events"""
        logger.error(f"Error in {event}: {traceback.format_exc()}")
        
    async def on_command_error(self, ctx, error):
        """Error handler for command errors"""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore command not found errors
            
        logger.error(f"Command error: {str(error)}")
        await ctx.send(f"❌ An error occurred: {str(error)}")

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
                        name="tokens | $symbol"
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
                    # Check WebSocket connection
                    if not self.ws or self.ws.closed:
                        logger.warning("WebSocket disconnected, attempting to reconnect...")
                        try:
                            await self.close()
                            await asyncio.sleep(5)  # Wait before reconnecting
                            await self.start(DISCORD_TOKEN)
                        except Exception as e:
                            logger.error(f"Failed to reconnect: {str(e)}")
                            await asyncio.sleep(30)  # Wait longer before next attempt
                            continue
                    
                    # Log connection status
                    logger.info(f"Bot is {'connected' if self.is_ready() else 'disconnected'}")
                    logger.info(f"Connected to {len(self.guilds)} guilds")
                    
                except Exception as e:
                    logger.error(f"Error in heartbeat: {str(e)}")
                    await asyncio.sleep(5)
                    
                await asyncio.sleep(30)  # Check every 30 seconds
                
        except asyncio.CancelledError:
            logger.info("Heartbeat task cancelled")
        except Exception as e:
            logger.error(f"Critical error in heartbeat task: {str(e)}")
            if not self.is_closed():
                self.create_background_task(self._heartbeat())
                
    async def close(self):
        """Clean up resources when bot is shutting down"""
        logger.info("Bot is shutting down...")
        try:
            # Cancel background tasks
            if hasattr(self, 'bg_task'):
                self.bg_task.cancel()
            if hasattr(self, 'presence_task'):
                self.presence_task.cancel()
            
            # Close aiohttp sessions in cogs
            for cog in self.cogs.values():
                if hasattr(cog, 'session'):
                    await cog.session.close()
            
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
                    # Send message with suppress_embeds=True to prevent auto-embedding
                    await message.channel.send(response, suppress_embeds=True)
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

        # Only search for Solana tokens
        dex_url = f"https://api.dexscreener.com/latest/dex/search?q={query}"
        dex_response = requests.get(dex_url, headers=headers, timeout=10)
        dex_data = dex_response.json()

        if not dex_data.get('pairs') or len(dex_data['pairs']) == 0:
            return f"Token '{query}' not found on Solana DEXs."

        # Filter only Solana pairs
        solana_pairs = [p for p in dex_data['pairs'] if p.get('chainId') == 'solana']
        if not solana_pairs:
            return f"Token '{query}' not found on Solana DEXs."

        # Get the first pair with good liquidity
        pair = None
        for p in solana_pairs:
            if float(p.get('liquidity', {}).get('usd', 0)) > 1000:  # Min $1000 liquidity
                pair = p
                break
        
        if not pair:
            pair = solana_pairs[0]  # Fallback to first pair if none with good liquidity

        # Extract basic token info
        token_symbol = pair.get('baseToken', {}).get('symbol', '???')
        dex_id = pair.get('dexId', 'Unknown').capitalize()
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

        # Calculate FDV and Market Cap
        fdv = 0
        market_cap = 0
        total_supply = pair.get('baseToken', {}).get('totalSupply')
        circulating_supply = pair.get('baseToken', {}).get('circulatingSupply', total_supply)
        
        if total_supply and price_usd:
            fdv = float(total_supply) * price_usd
        if circulating_supply and price_usd:
            market_cap = float(circulating_supply) * price_usd

        # Get ATH information
        ath = 0
        ath_change = 0
        if pair.get('priceUsd') and pair.get('priceMax'):
            ath = float(pair['priceMax'])
            ath_change = ((price_usd - ath) / ath) * 100 if ath > 0 else 0

        # Check for bundles with enhanced tracking
        bundles = []
        bundle_history = []
        try:
            # Get current bundles
            birdeye_url = f"https://public-api.birdeye.so/public/bundle_history?address={contract}"
            birdeye_response = requests.get(birdeye_url, headers=headers, timeout=10)
            if birdeye_response.status_code == 200:
                bundle_data = birdeye_response.json()
                if bundle_data.get('success') and bundle_data.get('data'):
                    # Track current bundles
                    current_bundles = []
                    for bundle in bundle_data['data']:
                        if bundle.get('symbol') and bundle.get('percentage'):
                            symbol = bundle['symbol']
                            percentage = float(bundle['percentage'])
                            current_bundles.append((symbol, percentage))
                    
                    # Sort by percentage and format
                    current_bundles.sort(key=lambda x: x[1], reverse=True)
                    bundles = [f"{symbol}•{percentage:.1f}%" for symbol, percentage in current_bundles]

                    # Get historical bundle data
                    history_url = f"https://public-api.birdeye.so/public/bundle_history_detail?address={contract}"
                    history_response = requests.get(history_url, headers=headers, timeout=10)
                    if history_response.status_code == 200:
                        history_data = history_response.json()
                        if history_data.get('success') and history_data.get('data'):
                            for entry in history_data['data'][:3]:  # Get last 3 changes
                                if entry.get('timestamp') and entry.get('percentage'):
                                    time_diff = int((datetime.utcnow() - datetime.fromtimestamp(entry['timestamp'])).total_seconds() / 3600)
                                    bundle_history.append(f"{entry['percentage']:.1f}% ({time_diff}h)")

        except Exception as e:
            logger.error(f"Error fetching bundle info: {str(e)}")

        # Get age of token
        hours_old = 0
        if pair.get('pairCreatedAt'):
            created_at = datetime.fromtimestamp(int(pair['pairCreatedAt'])/1000)
            hours_old = int((datetime.utcnow() - created_at).total_seconds() / 3600)

        # Get trading history
        buys = 0
        sells = 0
        total = 0
        buy_percentage = 0
        if pair.get('txns'):
            buys = pair['txns'].get('h24', {}).get('buys', 0)
            sells = pair['txns'].get('h24', {}).get('sells', 0)
            total = buys + sells
            buy_percentage = (buys/total * 100) if total > 0 else 0

        # Format message with ANSI colors and compact layout
        message = [
            f"\x1b[38;2;255;160;160m{token_symbol}\x1b[0m [{h24_change:+.1f}%] - \x1b[38;2;255;160;160mSOL\x1b[0m ↗",
            f"💰 \x1b[38;2;255;160;160mSOL\x1b[0m @ \x1b[38;2;255;160;160m{dex_id}\x1b[0m",
            f"💵 USD: \x1b[38;2;255;160;160m${price_str}\x1b[0m",
            f"💎 MC: \x1b[38;2;255;160;160m${market_cap/1e6:.1f}M\x1b[0m • FDV: \x1b[38;2;255;160;160m${fdv/1e6:.1f}M\x1b[0m",
            f"🏆 ATH: \x1b[38;2;255;160;160m${ath:.8f}\x1b[0m [{ath_change:.1f}%]",
            f"💧 Liq: \x1b[38;2;255;160;160m${liquidity:,.0f}\x1b[0m [x{liq_ratio:.1f}]",
            f"📊 Vol: \x1b[38;2;255;160;160m${volume_h24:,.0f}\x1b[0m ⏰ Age: \x1b[38;2;255;160;160m{hours_old}h\x1b[0m",
            f"📈 1H: {h1_change:+.1f}% • \x1b[38;2;255;160;160m${volume_h1:,.0f}\x1b[0m",
            f"🔄 TH: \x1b[38;2;255;160;160m{buys}\x1b[0m•\x1b[38;2;255;160;160m{sells}\x1b[0m•\x1b[38;2;255;160;160m{total}\x1b[0m [{buy_percentage:.0f}%]"
        ]

        # Add bundles if available
        if bundles:
            bundle_str = " • ".join(bundles)
            message.append(f"🎁 Bundles: \x1b[38;2;255;160;160m{bundle_str}\x1b[0m")

        # Add contract
        message.append(f"\n\x1b[38;2;255;160;160m{contract}\x1b[0m")

        # Add DEX links inside the code block
        message.extend([
            f"\x1b[38;2;255;160;160mDEX\x1b[0m•\x1b[38;2;255;160;160mBirdeye\x1b[0m•\x1b[38;2;255;160;160mJupiter\x1b[0m•\x1b[38;2;255;160;160mRaydium\x1b[0m",
            f"\x1b[38;2;255;160;160mPhoton\x1b[0m•\x1b[38;2;255;160;160mBullX\x1b[0m•\x1b[38;2;255;160;160mDexLab\x1b[0m"
        ])

        # Join with newlines and wrap in code block
        formatted_message = "```ansi\n" + "\n".join(message) + "\n```"

        # Add hidden clickable links after the code block
        formatted_message += (
            f"||DEX: <https://dexscreener.com/solana/{contract}>\n"
            f"Birdeye: <https://birdeye.so/token/{contract}>\n"
            f"Jupiter: <https://jup.ag/swap/{contract}>\n"
            f"Raydium: <https://raydium.io/swap/?inputCurrency=sol&outputCurrency={contract}>\n"
            f"Photon: <https://photon.rs/token/{contract}>\n"
            f"BullX: <https://bullx.io/trade/{contract}>\n"
            f"DexLab: <https://trade.dexlab.space/#/market/{contract}>||"
        )

        return formatted_message

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error: {str(e)}")
        return f"Network error while fetching token information. Please try again."
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return f"Error fetching token information. Please try again."

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