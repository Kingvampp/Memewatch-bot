import discord
from discord.ext import commands
import aiohttp
import logging
import time
import asyncio
import os
from datetime import datetime, timezone
from utils.formatting import (
    format_number, 
    format_price, 
    format_time_ago, 
    format_percentage
)
import traceback

class Solana(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.birdeye_api = "https://public-api.birdeye.so/public"
        self.solscan_api = "https://public-api.solscan.io"
        self.last_scan = {}  # Rate limiting
        self.logger = logging.getLogger('solana')
        self.session = None
        self.db = bot.db  # Get database reference from bot
        
        # Add API keys from environment
        self.birdeye_key = os.getenv('BIRDEYE_API_KEY')
        self.solscan_key = os.getenv('SOLSCAN_API_KEY')
        
    async def cog_load(self):
        """Initialize aiohttp session with headers"""
        headers = {
            'User-Agent': 'MemeWatchBot/1.0',
            'X-API-KEY': self.birdeye_key
        }
        self.session = aiohttp.ClientSession(headers=headers)
        
    async def cog_unload(self):
        """Cleanup session"""
        if self.session:
            await self.session.close()
            
    async def _check_rate_limit(self, user_id, cooldown=30):
        """Rate limit checker"""
        now = time.time()
        if user_id in self.last_scan:
            if now - self.last_scan[user_id] < cooldown:
                return False
        self.last_scan[user_id] = now
        return True

    async def get_dexscreener_data(self, token_address):
        """Fetch data from DexScreener API"""
        try:
            url = f"{os.getenv('DEXSCREENER_URL')}/tokens/{token_address}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    pairs = data.get('pairs', [])
                    if pairs:
                        # Get the most liquid pair
                        pair = max(pairs, key=lambda x: float(x.get('liquidity', {}).get('usd', 0)))
                        return {
                            'price': float(pair.get('priceUsd', 0)),
                            'price_change_1h': float(pair.get('priceChange', {}).get('h1', 0)),
                            'price_change_4h': float(pair.get('priceChange', {}).get('h4', 0)),
                            'liquidity_usd': float(pair.get('liquidity', {}).get('usd', 0)),
                            'volume_24h': float(pair.get('volume', {}).get('h24', 0)),
                            'ath_price': float(pair.get('priceUsd', {}).get('h24', 0)),
                            'ath_timestamp': pair.get('athTimestamp'),
                        }
        except Exception as e:
            self.logger.error(f"DexScreener API error: {str(e)}")
        return None

    async def get_token_data(self, token_address):
        """Fetch token data from multiple sources with retries"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            # Get data from multiple sources
            birdeye_data = await self.get_birdeye_data(token_address)
            solscan_data = await self.get_solscan_data(token_address)
            dexscreener_data = await self.get_dexscreener_data(token_address)
            
            # Combine data with priority (DexScreener > Birdeye > Solscan)
            token_data = {}
            if birdeye_data:
                token_data.update(birdeye_data)
            if solscan_data:
                token_data.update(solscan_data)
            if dexscreener_data:
                # Update specific fields from DexScreener
                token_data.update({
                    'price_change_1h': dexscreener_data['price_change_1h'],
                    'price_change_4h': dexscreener_data['price_change_4h'],
                    'ath_price': dexscreener_data['ath_price'],
                    'ath_timestamp': dexscreener_data['ath_timestamp']
                })
            
            return token_data
        except Exception as e:
            self.logger.error(f"Error fetching token data: {str(e)}")
            return None

    async def get_solscan_data(self, token_address):
        """Fetch additional data from Solscan"""
        try:
            url = f"{self.solscan_api}/token/{token_address}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'holder_count': data.get('holder', 0),
                        'creation_date': data.get('creation_date'),
                        'verified': data.get('verified', False)
                    }
        except Exception as e:
            self.logger.error(f"Solscan API error: {str(e)}")
            return None

    def process_token_data(self, data):
        """Process and format token data with error handling"""
        try:
            if not data:
                return None
                
            return {
                'symbol': data.get('symbol', 'Unknown'),
                'name': data.get('name', 'Unknown Token'),
                'price': format_price(data.get('price', 0)),
                'price_change_24h': format_percentage(data.get('priceChange24h', 0)),
                'mcap': format_number(data.get('marketCap', 0)),
                'fdv': format_number(data.get('fdv', 0)),
                'volume': format_number(data.get('volume24h', 0)),
                'liquidity': format_number(data.get('liquidity', 0)),
                'holders': format_number(data.get('holderCount', 0)),
                'created_at': format_time_ago(data.get('createdAt', 0)),
                'age': format_time_ago(data.get('createdAt', 0)),
                'dexes': data.get('dexes', [])
            }
        except Exception as e:
            self.logger.error(f"Data processing error: {str(e)}")
            return None

    @commands.command(name='scan')
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def scan_token(self, ctx, token_address: str):
        """Scan a token and display its information"""
        try:
            # Add debug logging
            self.logger.info(f"[SCAN] Command received from {ctx.author.name} for token: {token_address}")
            
            # Check rate limit
            if not await self._check_rate_limit(ctx.author.id):
                self.logger.info("[SCAN] Rate limit hit")
                await ctx.send("⏳ Please wait before scanning another token.")
                return
                
            async with ctx.typing():
                # Validate token address format
                if not self.validate_token_address(token_address):
                    self.logger.error("[SCAN] Invalid token address format")
                    await ctx.send("❌ Invalid token address format.")
                    return
                    
                # Add debug logging for API calls
                self.logger.info("[SCAN] Starting API calls...")
                
                # Test each API individually
                try:
                    birdeye_data = await self.get_birdeye_data(token_address)
                    self.logger.info(f"[SCAN] Birdeye data: {bool(birdeye_data)}")
                except Exception as e:
                    self.logger.error(f"[SCAN] Birdeye API error: {str(e)}")
                    
                try:
                    solscan_data = await self.get_solscan_data(token_address)
                    self.logger.info(f"[SCAN] Solscan data: {bool(solscan_data)}")
                except Exception as e:
                    self.logger.error(f"[SCAN] Solscan API error: {str(e)}")
                    
                try:
                    dexscreener_data = await self.get_dexscreener_data(token_address)
                    self.logger.info(f"[SCAN] DexScreener data: {bool(dexscreener_data)}")
                except Exception as e:
                    self.logger.error(f"[SCAN] DexScreener API error: {str(e)}")
                
                # Get combined token data
                token_data = await self.get_token_data(token_address)
                
                if not token_data:
                    self.logger.error("[SCAN] Could not fetch token data")
                    await ctx.send("❌ Could not fetch token data. Please try again later.")
                    return

                # Add debug logging for embed creation
                self.logger.info("[SCAN] Creating embed...")
                try:
                    embed = self.create_token_embed(token_data, token_address)
                except Exception as e:
                    self.logger.error(f"[SCAN] Error creating embed: {str(e)}")
                    raise
                
                # Add debug logging for response
                self.logger.info("[SCAN] Sending response...")
                await ctx.send(embed=embed)
                
                # Save scan to database
                try:
                    mcap = float(token_data.get('mcap', '0').replace('$', '').replace(',', ''))
                    scan_info = await self.format_scan_info(ctx, token_data, mcap)
                    if scan_info:
                        await ctx.send(scan_info)
                except Exception as e:
                    self.logger.error(f"[SCAN] Error saving scan: {str(e)}")
                
        except Exception as e:
            self.logger.error(f"[SCAN] Command error: {str(e)}")
            self.logger.error(f"[SCAN] Full traceback: {traceback.format_exc()}")
            await ctx.send("❌ An error occurred while scanning the token.")

    def create_token_embed(self, data, address):
        """Create a rich embed for token data"""
        try:
            # Get price changes
            price_changes = {
                '1h': data.get('price_change_1h', 0),
                '4h': data.get('price_change_4h', 0)
            }
            
            # Get ATH data
            ath_mcap = data.get('ath_mcap', data.get('mcap', 0))
            ath_time = data.get('ath_timestamp', 'Unknown')
            if ath_time != 'Unknown':
                ath_time = format_time_ago(int(ath_time))
            
            embed = discord.Embed(title=f"{data['symbol']}/SOL", description=data['name'])
            embed.add_field(name="", value=f"""
💰 USD: {format_price(float(data['price']))}
💎 FDV: {format_number(float(data['fdv']))}
💫 MC: {format_number(float(data['mcap']))} ➡︎ ATH: {format_number(float(ath_mcap))} [{ath_time}]
💦 Liq: {format_number(float(data['liquidity']))}
📊 Vol: {format_number(float(data['volume']))} 🕰️ Age: {data['age']}
🚀 1H: {format_percentage(price_changes['1h'])} 🚀 4H: {format_percentage(price_changes['4h'])}

{address}

{' • '.join(data['dexes'])}
""", inline=False)
            
            if data.get('verified'):
                embed.add_field(name="✅ Verified", value="Yes", inline=True)
            
            return embed
        except Exception as e:
            self.logger.error(f"Error creating embed: {str(e)}")
            raise

    def validate_token_address(self, address):
        """Validate Solana token address format"""
        return len(address) == 44 and address.isalnum()

    async def format_scan_info(self, ctx, token_data, mcap):
        """Format scan information for display"""
        try:
            scan_info = await self.db.get_scan_info(token_data['address'], str(ctx.guild.id))
            
            if not scan_info:
                # First scan
                await self.db.save_scan(token_data['address'], ctx.author.id, mcap, str(ctx.guild.id))
                return f"{ctx.author.name} you are first in this server @ {self.format_number(mcap)}"
            else:
                first_scanner_id, scan_time, first_mcap = scan_info
                first_scanner = await self.bot.fetch_user(int(first_scanner_id))
                time_ago = self.format_time_ago(scan_time)
                
                # Determine if price went up or down
                if mcap > first_mcap:
                    trend = "📈 Token pumped!"
                else:
                    trend = "📉 Token dipped!"
                    
                return f"{ctx.author.name} {self.format_number(mcap)} {trend} ⋅ {first_scanner.name} @ {self.format_number(first_mcap)} ⋅ {time_ago}"
                
        except Exception as e:
            self.logger.error(f"Error formatting scan info: {str(e)}")
            return ""

    @commands.command(name='ping')
    async def ping(self, ctx):
        """Simple command to test if the bot is responsive"""
        try:
            self.logger.info("[PING] Command received")
            await ctx.send("🏓 Pong!")
        except Exception as e:
            self.logger.error(f"[PING] Error: {str(e)}")

    async def get_birdeye_data(self, token_address):
        """Fetch data from Birdeye API"""
        try:
            url = f"{self.birdeye_api}/token/info?address={token_address}"
            headers = {'X-API-KEY': self.birdeye_key}
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('success'):
                        return self.process_token_data(data.get('data', {}))
        except Exception as e:
            self.logger.error(f"Birdeye API error: {str(e)}")
        return None

async def setup(bot):
    await bot.add_cog(Solana(bot))
