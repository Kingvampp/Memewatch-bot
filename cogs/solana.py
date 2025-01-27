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
    """Solana token tracking commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.dexscreener_api = "https://api.dexscreener.com/latest/dex"
        self.birdeye_api = "https://public-api.birdeye.so/public"
        self.solscan_api = "https://public-api.solscan.io"
        self.logger = logging.getLogger('solana')
        self.session = None
        self.last_scan = {}
        self.db = bot.db
        
        # API keys
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

    @commands.command(name='test')
    async def test(self, ctx):
        """Simple test command"""
        await ctx.send("Bot is working!")

    @commands.command(name='scan')
    async def scan(self, ctx, address: str):
        """Scan a Solana token"""
        try:
            self.logger.info(f"Scan command received for {address}")
            await ctx.send(f"Scanning token: {address}...")
            # Rest of scan logic
        except Exception as e:
            self.logger.error(f"Error in scan command: {str(e)}")
            await ctx.send("❌ An error occurred while scanning.")

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

    async def get_jupiter_data(self, token_address):
        """Fetch token data from Jupiter"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            # Basic price data
            price_url = f"https://price.jup.ag/v4/price?ids={token_address}"
            async with self.session.get(price_url) as response:
                if response.status != 200:
                    self.logger.error(f"Jupiter price API error: {await response.text()}")
                    return None
                    
                price_data = await response.json()
                if not price_data.get('data', {}).get(token_address):
                    self.logger.error(f"No price data for {token_address}")
                    return None

                token_price = price_data['data'][token_address]
                
                # Get token metadata
                meta_url = "https://token.jup.ag/all"
                async with self.session.get(meta_url) as meta_response:
                    if meta_response.status != 200:
                        self.logger.error(f"Jupiter metadata API error: {await meta_response.text()}")
                        return None
                        
                    meta_data = await meta_response.json()
                    token_meta = meta_data.get('tokens', {}).get(token_address, {})

                return {
                    'name': token_meta.get('name', 'Unknown'),
                    'symbol': token_meta.get('symbol', 'Unknown'),
                    'price': float(token_price.get('price', 0)),
                    'price_change': float(token_price.get('priceChange24h', 0)),
                    'mcap': float(token_price.get('marketCap', 0)),
                    'logo': token_meta.get('logoURI', ''),
                    'dexes': [
                        f"[JUPITER](https://jup.ag/swap/SOL-{token_address})",
                        f"[BIRDEYE](https://birdeye.so/token/{token_address})",
                        f"[DEXSCREENER](https://dexscreener.com/solana/{token_address})"
                    ]
                }

        except Exception as e:
            self.logger.error(f"Jupiter API error for {token_address}: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None

    async def get_token_data(self, token_address):
        """Fetch token data from DexScreener"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            # Try DexScreener first
            dex_url = f"{self.dexscreener_api}/pairs/solana/{token_address}"
            self.logger.info(f"Fetching from DexScreener: {dex_url}")
            
            async with self.session.get(dex_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('pairs') and len(data['pairs']) > 0:
                        pair = data['pairs'][0]
                        return {
                            'name': pair['baseToken']['name'],
                            'symbol': pair['baseToken']['symbol'],
                            'price': float(pair['priceUsd']),
                            'price_change_1h': float(pair['priceChange']['h1'] or 0),
                            'price_change_4h': float(pair['priceChange']['h4'] or 0),
                            'price_change_24h': float(pair['priceChange']['h24'] or 0),
                            'liquidity': float(pair['liquidity']['usd']),
                            'volume_24h': float(pair['volume']['h24']),
                            'fdv': float(pair.get('fdv', 0)),
                            'mcap': float(pair.get('mcap', 0)),
                            'pair_address': pair['pairAddress'],
                            'created_at': pair.get('createTime'),
                            'logo': pair['baseToken'].get('logoURI', '')
                        }

            self.logger.error(f"No data found for token {token_address}")
            return None

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
                color=discord.Color.green() if data['price_change'] >= 0 else discord.Color.red()
            )
            
            # Add fields
            embed.add_field(
                name="💰 Price",
                value=f"${data['price']:.10f}" if data['price'] < 0.000001 else f"${data['price']:.6f}",
                inline=True
            )
            embed.add_field(
                name="📈 24h Change",
                value=f"{data['price_change']:+.2f}%",
                inline=True
            )
            embed.add_field(
                name="💎 Market Cap",
                value=f"${data['mcap']:,.0f}",
                inline=True
            )
            embed.add_field(
                name="💫 FDV",
                value=f"${data['mcap']:,.0f}",
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
                    f"{data['dexes'][0]} • {data['dexes'][1]} • {data['dexes'][2]}"
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
        """Handle $symbol messages"""
        if message.author.bot:
            return

        if message.content.startswith('$'):
            symbol = message.content[1:].lower()
            
            if symbol in self.token_addresses:
                token_address = self.token_addresses[symbol]
                try:
                    async with message.channel.typing():
                        token_data = await self.get_token_data(token_address)
                        
                        if token_data:
                            # Format the message
                            description = (
                                f"{token_data['name']} ({token_data['symbol']}/SOL)\n\n"
                                f"💰 USD: ${token_data['price']:.10f}\n"
                                f"💎 FDV: ${self.format_number(token_data['fdv'])}\n"
                                f"💫 MC: ${self.format_number(token_data['mcap'])}\n"
                                f"💧 Liq: ${self.format_number(token_data['liquidity'])}\n"
                                f"📊 Vol: ${self.format_number(token_data['volume_24h'])} "
                                f"🕒 Age: {format_time_ago(token_data['created_at'])}\n"
                                f"📈 1H: {token_data['price_change_1h']}% • "
                                f"4H: {token_data['price_change_4h']}% • "
                                f"24H: {token_data['price_change_24h']}%\n\n"
                                f"`{token_address}`\n\n"
                                f"[DEX](https://dexscreener.com/solana/{token_data['pair_address']}) • "
                                f"[BIRD](https://birdeye.so/token/{token_address}) • "
                                f"[BLX](https://solscan.io/token/{token_address}) • "
                                f"[SOL](https://solana.fm/address/{token_address}) • "
                                f"[BNK](https://solanabeach.io/token/{token_address}) • "
                                f"[JUP](https://jup.ag/swap/SOL-{token_address})"
                            )

                            # Create embed
                            embed = discord.Embed(
                                title=f"{token_data['symbol']}/SOL",
                                description=description,
                                color=discord.Color.green() if token_data['price_change_24h'] >= 0 else discord.Color.red()
                            )

                            if token_data.get('logo'):
                                embed.set_thumbnail(url=token_data['logo'])

                            await message.channel.send(embed=embed)

                            # Format and send scan info
                            scan_info = await self.format_scan_info(message, token_data, token_data['mcap'])
                            if scan_info:
                                await message.channel.send(scan_info)
                        else:
                            await message.channel.send(f"❌ Could not fetch data for ${symbol}")
                            
                except Exception as e:
                    self.logger.error(f"Error processing {symbol}: {str(e)}")
                    self.logger.error(traceback.format_exc())
                    await message.channel.send(f"❌ Error processing ${symbol}")
            else:
                if len(symbol) <= 10:
                    await message.channel.send(f"❌ Unknown token symbol: ${symbol}")

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
💎 FDV: {format_number(float(data['mcap']))}
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
