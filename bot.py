#!/usr/bin/env python3

import os
import logging
import discord
import asyncio
import traceback
from discord.ext import commands
from dotenv import load_dotenv
import aiohttp
from datetime import datetime
import re

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

class MemecoinBot(commands.Bot):
    def __init__(self):
        """Initialize the bot with intents and command prefix"""
        intents = discord.Intents.default()
        intents.message_content = True
        
        # Set command prefix and activity
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="tokens | $symbol"
        )
            
        super().__init__(
            command_prefix='$',
            intents=intents,
            activity=activity
        )
        
        # Store activity for presence refresh
        self.activity = activity
        
        # Initialize logger
        self.logger = logging.getLogger('bot')
        
        # Initialize background tasks
        self.bg_task = None
        self.presence_task = None
        
    def create_background_task(self, coro):
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task
        
    async def setup_hook(self):
        """Called before the bot starts running"""
        logger.info("Setting up Memecoin bot hooks...")
        try:
            # Load cogs
            await self.load_extension("cogs.security")
            await self.load_extension("cogs.solana")
            logger.info("Loaded cogs for Memecoin bot")
            
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
        try:
            # Update username if needed
            if self.user.name != "Memecoin bot":
                try:
                    await self.user.edit(username="Memecoin bot")
                    logger.info("Updated bot username to Memecoin bot")
                except discord.HTTPException as e:
                    logger.error(f"Failed to update username: {str(e)}")
            
            # Set presence
            await self.change_presence(
                status=discord.Status.online,
                activity=self.activity
            )
            
            logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
            logger.info("Set initial presence")
            
        except Exception as e:
            logger.error(f"Error in on_ready: {str(e)}")
            logger.error(traceback.format_exc())
            
    async def _refresh_presence(self):
        """Refresh bot presence periodically"""
        await self.wait_until_ready()
        try:
            while not self.is_closed():
                try:
                    # Only update if connected
                    ws = self._connection._get_websocket(None)
                    if ws is not None and not ws._closed:
                        await self.change_presence(
                            status=discord.Status.online,
                            activity=self.activity
                        )
                        logger.info("Refreshed Memecoin bot presence")
                except Exception as e:
                    logger.error(f"Error refreshing presence: {str(e)}")
                
                await asyncio.sleep(300)
                
        except asyncio.CancelledError:
            logger.info("Presence refresh task cancelled")
        except Exception as e:
            logger.error(f"Error in presence refresh task: {str(e)}")
            if not self.is_closed():
                self.create_background_task(self._refresh_presence())
                
    async def _heartbeat(self):
        """Monitor bot connection status"""
        await self.wait_until_ready()
        try:
            while not self.is_closed():
                try:
                    # Check if websocket exists and is connected
                    ws = self._connection._get_websocket(None)
                    if ws is not None and not ws._closed:
                        logger.info("Memecoin bot heartbeat ok")
                    else:
                        logger.warning("Memecoin bot connection issues detected")
                        # Try to reconnect
                        try:
                            await self.close()
                            await self.start(DISCORD_TOKEN)
                            logger.info("Memecoin bot reconnected successfully")
                        except Exception as e:
                            logger.error(f"Failed to reconnect: {str(e)}")
                            
                except Exception as e:
                    logger.error(f"Error in heartbeat: {str(e)}")
                    
                await asyncio.sleep(30)
                
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
        """Handle incoming messages"""
        # Ignore messages from the bot itself
        if message.author == self.user:
            return

        # Get the message content
        content = message.content.strip()

        try:
            # Skip if message starts with @
            if content.startswith('@'):
                return
                
            # Process $ commands and contract addresses
            if content.startswith('$') or is_contract_address(content):
                # Check if we've already processed this message
                if hasattr(message, 'processed_by_memecoin'):
                    return
                
                # Mark message as processed
                setattr(message, 'processed_by_memecoin', True)
                
                logger.info(f"Memecoin bot processing token query: {content}")
                query = content[1:].strip() if content.startswith('$') else content
                if query:
                    async with message.channel.typing():
                        embed = await get_token_info(query)
                        await message.channel.send(embed=embed)
                else:
                    await message.channel.send("Please provide a token name or contract address. Example: `$pepe` or `$0x...`")

        except Exception as e:
            logger.error(f"Error in message handler: {str(e)}")
            logger.error(traceback.format_exc())

def is_contract_address(text):
    # ETH address pattern
    eth_pattern = r'^0x[a-fA-F0-9]{40}$'
    # SOL address pattern (base58 encoded, 32-44 chars)
    sol_pattern = r'^[1-9A-HJ-NP-Za-km-z]{32,44}$'
    
    return bool(re.match(eth_pattern, text)) or bool(re.match(sol_pattern, text))

async def get_token_info(query):
    """Get token information from DEXScreener API"""
    try:
        # First try DEXScreener API for Solana tokens
        dex_url = f"https://api.dexscreener.com/latest/dex/search?q={query}"
        async with aiohttp.ClientSession() as session:
            async with session.get(dex_url, timeout=10) as response:
                dex_data = await response.json()
        
        # Filter for Solana pairs only
        solana_pairs = [p for p in dex_data.get('pairs', []) if p.get('chainId') == 'solana']
        if not solana_pairs:
            return discord.Embed(title="Error", description=f"Token not found on Solana DEXs: {query}", color=discord.Color.red())
            
        # Get the first pair with data
        pair = solana_pairs[0]
        if not pair:
            return discord.Embed(title="Error", description="No data available for this token", color=discord.Color.red())
            
        # Extract basic info
        symbol = pair.get('baseToken', {}).get('symbol', 'Unknown')
        contract = pair.get('baseToken', {}).get('address', '')
        price_usd = float(pair.get('priceUsd', 0))
        price_change = float(pair.get('priceChange', {}).get('h24', 0))
        
        # Calculate market metrics
        total_supply = pair.get('baseToken', {}).get('totalSupply')
        circulating_supply = pair.get('baseToken', {}).get('circulatingSupply')
        
        market_cap = 0
        fdv = 0
        
        if circulating_supply and price_usd:
            try:
                market_cap = float(circulating_supply) * price_usd
            except:
                market_cap = 0
                
        if total_supply and price_usd:
            try:
                fdv = float(total_supply) * price_usd
            except:
                fdv = 0
            
        # Get liquidity and volume
        liquidity_usd = float(pair.get('liquidity', {}).get('usd', 0))
        volume_usd = float(pair.get('volume', {}).get('h24', 0))
        
        # Calculate age
        created_at = pair.get('pairCreatedAt')
        if created_at:
            created_date = datetime.fromtimestamp(int(created_at)/1000)
            age_hours = (datetime.now() - created_date).total_seconds() / 3600
        else:
            age_hours = 0
            
        # Get trading history
        txns = pair.get('txns', {}).get('h24', {})
        buys = int(txns.get('buys', 0))
        sells = int(txns.get('sells', 0))
        total_txns = buys + sells
        buy_ratio = (buys / total_txns * 100) if total_txns > 0 else 0
        
        # Format numbers
        def format_number(num):
            if num == 0:
                return "?"
            if num >= 1_000_000_000:
                return f"{num/1_000_000_000:.1f}B"
            elif num >= 1_000_000:
                return f"{num/1_000_000:.1f}M"
            elif num >= 1_000:
                return f"{num/1_000:.1f}K"
            else:
                return f"{num:.1f}"
                
        # Create embed
        color = discord.Color.green() if price_change > 0 else discord.Color.red()
        embed = discord.Embed(
            title=f"{symbol} {'↗' if price_change > 0 else '↘'}",
            description=f"24h Change: {price_change:+.1f}%",
            color=color
        )
        
        # Format price based on size
        if price_usd < 0.00001:
            price_str = f"${price_usd:.12f}"
        elif price_usd < 0.0001:
            price_str = f"${price_usd:.10f}"
        elif price_usd < 0.001:
            price_str = f"${price_usd:.8f}"
        else:
            price_str = f"${price_usd:.6f}"
            
        embed.add_field(name="💵 Price", value=price_str, inline=True)
        
        # Market metrics
        mc_str = format_number(market_cap)
        fdv_str = format_number(fdv)
        embed.add_field(name="💎 Market Cap", value=f"${mc_str}", inline=True)
        embed.add_field(name="💫 FDV", value=f"${fdv_str}", inline=True)
            
        # Liquidity and volume
        liq_str = format_number(liquidity_usd)
        vol_str = format_number(volume_usd)
        embed.add_field(name="💧 Liquidity", value=f"${liq_str}", inline=True)
        embed.add_field(name="📊 Volume (24h)", value=f"${vol_str}", inline=True)
        
        if age_hours > 0:
            embed.add_field(name="⏰ Age", value=f"{int(age_hours)}h", inline=True)
            
        if total_txns > 0:
            embed.add_field(
                name="🔄 Transactions (24h)", 
                value=f"Buys: {buys}\nSells: {sells}\nTotal: {total_txns}\nBuy Ratio: {buy_ratio:.0f}%",
                inline=False
            )
            
        # Add links
        links = [
            f"[Birdeye](https://birdeye.so/token/{contract})",
            f"[Jupiter](https://jup.ag/swap/{contract})",
            f"[Raydium](https://raydium.io/swap/?inputCurrency=sol&outputCurrency={contract})",
            f"[DexLab](https://trade.dexlab.space/#/market/{contract})"
        ]
        embed.add_field(name="🔗 Links", value=" • ".join(links), inline=False)
        
        return embed
        
    except Exception as e:
        logger.error(f"Error getting token info: {str(e)}")
        logger.error(traceback.format_exc())
        return discord.Embed(
            title="Error",
            description=f"Error fetching token information: {str(e)}",
            color=discord.Color.red()
        )

async def main():
    async with MemecoinBot() as bot:
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