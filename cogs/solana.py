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

    async def get_token_data(self, token_address):
        """Fetch token data from multiple sources with retries"""
        if not self.session:
            self.session = aiohttp.ClientSession()  # Ensure session exists
            
        retry_count = 3
        for attempt in range(retry_count):
            try:
                # Add debug logging
                self.logger.info(f"Fetching token data attempt {attempt + 1}")
                
                # Birdeye API with proper headers
                headers = {'X-API-KEY': self.birdeye_key} if self.birdeye_key else {}
                birdeye_url = f"{self.birdeye_api}/token_info?address={token_address}"
                
                # Add debug logging
                self.logger.info(f"Making API request to: {birdeye_url}")
                
                async with self.session.get(birdeye_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.logger.info("API response received successfully")
                        
                        if 'data' in data:
                            token_data = self.process_token_data(data['data'])
                            
                            # Enrich with Solscan data
                            solscan_data = await self.get_solscan_data(token_address)
                            if solscan_data:
                                token_data.update(solscan_data)
                                
                            return token_data
                    elif response.status == 429:  # Rate limit
                        self.logger.warning("Rate limit hit, backing off...")
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    else:
                        self.logger.error(f"Birdeye API error: {response.status}")
                        response_text = await response.text()
                        self.logger.error(f"Response body: {response_text}")
                        
            except Exception as e:
                self.logger.error(f"Token data fetch error (attempt {attempt+1}): {str(e)}")
                self.logger.error(f"Full traceback: {traceback.format_exc()}")
                if attempt == retry_count - 1:
                    return None
                await asyncio.sleep(1)
        
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
            self.logger.info(f"Scan command received for token: {token_address}")
            
            # Check rate limit
            if not await self._check_rate_limit(ctx.author.id):
                await ctx.send("⏳ Please wait before scanning another token.")
                return
                
            async with ctx.typing():
                # Validate token address format
                if not self.validate_token_address(token_address):
                    await ctx.send("❌ Invalid token address format.")
                    return
                    
                # Add debug logging
                self.logger.info("Fetching token data...")
                token_data = await self.get_token_data(token_address)
                
                if not token_data:
                    await ctx.send("❌ Could not fetch token data. Please try again later.")
                    return

                # Add debug logging
                self.logger.info("Creating embed...")
                embed = self.create_token_embed(token_data, token_address)
                
                # Add debug logging
                self.logger.info("Sending response...")
                await ctx.send(embed=embed)
                
                # Save scan to database
                mcap = float(token_data['mcap'].replace('$', '').replace(',', ''))
                scan_info = await self.format_scan_info(ctx, token_data, mcap)
                if scan_info:
                    await ctx.send(scan_info)
                
        except Exception as e:
            self.logger.error(f"Scan command error: {str(e)}")
            self.logger.error(f"Full traceback: {traceback.format_exc()}")
            await ctx.send("❌ An error occurred while scanning the token.")

    def create_token_embed(self, data, address):
        """Create a rich embed for token data"""
        embed = discord.Embed(title=f"{data['symbol']}/SOL", description=data['name'])
        embed.add_field(name="", value=f"""
💰 USD: {self.format_price(data['price'])}
💎 FDV: {self.format_number(data['fdv'])}
💫 MC: {self.format_number(data['mcap'])} ➡︎ ATH: {self.format_number(data['mcap'])} [{self.format_time_ago(data['created_at'])}]
💦 Liq: {self.format_number(data['liquidity'])}
📊 Vol: {self.format_number(data['volume'])} 🕰️ Age: {self.format_time_ago(data['created_at'])}
🚀 1H: {self.format_percentage(data['price_change_24h'])} 🚀 4H: {self.format_percentage(data['price_change_24h'])}

{address}

{' • '.join(data['dexes'])}
""", inline=False)
        
        if data.get('verified'):
            embed.add_field(name="✅ Verified", value="Yes", inline=True)
            
        return embed

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

async def setup(bot):
    await bot.add_cog(Solana(bot))
