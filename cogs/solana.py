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
        self.dexscreener_api = "https://api.dexscreener.com/latest/dex"
        self.birdeye_api = "https://public-api.birdeye.so/public"
        self.solscan_api = "https://public-api.solscan.io"
        self.logger = logging.getLogger('solana')
        self.session = None
        self.last_scan = {}  # Rate limiting
        self.db = bot.db  # Get database reference from bot
        
        # Add API keys from environment
        self.birdeye_key = os.getenv('BIRDEYE_API_KEY')
        self.solscan_key = os.getenv('SOLSCAN_API_KEY')
        
        # Common token addresses
        self.token_addresses = {
            'sol': 'So11111111111111111111111111111111111111112',
            'solana': 'So11111111111111111111111111111111111111112',
            'wif': 'EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm',
            'bonk': 'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263',
            'jup': 'JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN',
            'ufd': 'UFDGgD31XVrEUpDQZXxGbqbW7EhxgMWHpxBhVoqGsqB',
            'me': 'MEFNBXixkEbait3xn9bkm8WsJzXtVsaJEn4c8Sam21u'
        }
        
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
        """Fetch token data from multiple sources"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            # Get data from DexScreener
            url = f"{self.dexscreener_api}/pairs/solana/{token_address}"
            async with self.session.get(url) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                pairs = data.get('pairs', [])
                if not pairs:
                    return None
                    
                # Get the most liquid pair
                pair = max(pairs, key=lambda x: float(x.get('liquidity', {}).get('usd', 0)))
                
                # Format the data
                return {
                    'symbol': pair['baseToken']['symbol'],
                    'name': pair['baseToken']['name'],
                    'price': float(pair['priceUsd']),
                    'price_change_24h': float(pair['priceChange']['h24']),
                    'mcap': float(pair['marketCap']),
                    'fdv': float(pair.get('fdv', 0)),
                    'volume_24h': float(pair['volume']['h24']),
                    'liquidity': float(pair['liquidity']['usd']),
                    'created_at': pair['pairCreatedAt'],
                    'dexes': [pair['dexId']],
                    'pair_address': pair['pairAddress']
                }
                
        except Exception as e:
            self.logger.error(f"Error fetching token data: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None

    def format_message(self, data):
        """Format token data for Discord message"""
        try:
            embed = discord.Embed(
                title=f"{data['symbol']}/SOL",
                description=f"{data['name']} Price and Analytics",
                color=discord.Color.green() if data['price_change_24h'] >= 0 else discord.Color.red()
            )
            
            # Add fields
            embed.add_field(
                name="💰 Price",
                value=f"${data['price']:.10f}" if data['price'] < 0.000001 else f"${data['price']:.6f}",
                inline=True
            )
            embed.add_field(
                name="📈 24h Change",
                value=f"{data['price_change_24h']:+.2f}%",
                inline=True
            )
            embed.add_field(
                name="💎 Market Cap",
                value=f"${data['mcap']:,.0f}",
                inline=True
            )
            embed.add_field(
                name="💫 FDV",
                value=f"${data['fdv']:,.0f}",
                inline=True
            )
            embed.add_field(
                name="💧 Liquidity",
                value=f"${data['liquidity']:,.0f}",
                inline=True
            )
            embed.add_field(
                name="📊 24h Volume",
                value=f"${data['volume_24h']:,.0f}",
                inline=True
            )
            
            # Add links
            embed.add_field(
                name="🔗 Links",
                value=(
                    f"[DexScreener](https://dexscreener.com/solana/{data['pair_address']}) • "
                    f"[Birdeye](https://birdeye.so/token/{data['pair_address']}) • "
                    f"[Solscan](https://solscan.io/token/{data['pair_address']})"
                ),
                inline=False
            )
            
            return embed
            
        except Exception as e:
            self.logger.error(f"Error formatting message: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle $ commands"""
        if message.author.bot:
            return
            
        if not message.content.startswith('$'):
            return
            
        # Get token symbol/address
        token_id = message.content[1:].strip().lower()
        if not token_id:
            return
            
        # Check rate limit
        if not await self._check_rate_limit(message.author.id):
            await message.channel.send("⏳ Please wait before scanning another token")
            return
            
        try:
            # Get token address
            token_address = self.token_addresses.get(token_id, token_id)
            
            async with message.channel.typing():
                # Get token data
                token_data = await self.get_token_data(token_address)
                if not token_data:
                    await message.channel.send(f"❌ Could not find token information for {token_id}")
                    return
                    
                # Format and send message
                embed = self.format_message(token_data)
                if embed:
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send("❌ Error formatting token information")
                    
        except Exception as e:
            self.logger.error(f"Error processing token command: {str(e)}")
            self.logger.error(traceback.format_exc())
            await message.channel.send("❌ An error occurred while processing your request")

    @commands.command(name='scan')
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def scan_token(self, ctx, token_address: str):
        """Scan a token and display its information"""
        try:
            self.logger.info(f"[SCAN] Command received from {ctx.author.name} for token: {token_address}")
            
            if not self.validate_token_address(token_address):
                await ctx.send("❌ Invalid token address format.")
                return
                
            async with ctx.typing():
                token_data = await self.get_token_data(token_address)
                if not token_data:
                    await ctx.send("❌ Could not fetch token data. Please try again later.")
                    return
                
                # Create and send embed
                embed = self.create_token_embed(token_data, token_address)
                await ctx.send(embed=embed)
                
                # Format and send scan info
                mcap = float(token_data.get('mcap', 0))
                scan_info = await self.format_scan_info(ctx, token_data, mcap)
                if scan_info:
                    await ctx.send(scan_info)
                    
        except Exception as e:
            self.logger.error(f"[SCAN] Command error: {str(e)}")
            self.logger.error(traceback.format_exc())
            await ctx.send("❌ An error occurred while scanning the token.")

    @commands.command(name='ping')
    async def ping(self, ctx):
        """Simple ping command to check if bot is responsive"""
        try:
            self.logger.info(f"[PING] Command received from {ctx.author.name}")
            await ctx.send("🏓 Pong!")
        except Exception as e:
            self.logger.error(f"[PING] Error: {str(e)}")
            await ctx.send("❌ An error occurred.")

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
📊 Vol: {format_number(float(data['volume_24h']))} 🕰️ Age: {data['created_at']}
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
            scan_info = await self.db.get_scan_info(token_data['pair_address'], str(ctx.guild.id))
            
            if not scan_info:
                # First scan
                await self.db.save_scan(token_data['pair_address'], ctx.author.id, mcap, str(ctx.guild.id))
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
