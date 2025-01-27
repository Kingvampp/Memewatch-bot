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
        """Comprehensive Jupiter API data fetching"""
        try:
            # Price and market data
            price_url = f"https://price.jup.ag/v4/price?ids={token_address}&vsToken=So11111111111111111111111111111111111111112"
            
            # Token metadata
            meta_url = "https://token.jup.ag/all"
            
            # Get top pools/routes
            routes_url = f"https://quote-api.jup.ag/v6/quote?inputMint=So11111111111111111111111111111111111111112&outputMint={token_address}&amount=1000000000&slippageBps=50"
            
            async with aiohttp.ClientSession() as session:
                # Fetch price data
                async with session.get(price_url) as price_response:
                    if price_response.status != 200:
                        return None
                    price_data = await price_response.json()
                    
                # Fetch metadata
                async with session.get(meta_url) as meta_response:
                    if meta_response.status != 200:
                        return None
                    meta_data = await meta_response.json()
                    
                # Fetch routing data
                async with session.get(routes_url) as routes_response:
                    if routes_response.status != 200:
                        return None
                    routes_data = await routes_response.json()
                    
                # Process the data
                token_price = price_data.get('data', {}).get(token_address, {})
                token_meta = meta_data.get('tokens', {}).get(token_address, {})
                routes = routes_data.get('data', [])
                
                # Get best pools from routes
                pools = []
                if routes:
                    for market in routes[0].get('marketInfos', [])[:3]:  # Top 3 pools
                        pools.append(f"{market.get('label', 'Unknown')} ({market.get('liquidity', '0')})")
                
                return {
                    'name': token_meta.get('name', 'Unknown'),
                    'symbol': token_meta.get('symbol', 'Unknown'),
                    'price': token_price.get('price', 0),
                    'price_change': token_price.get('priceChange24h', 0),
                    'liquidity': sum(float(market.get('liquidity', 0)) for market in routes[0].get('marketInfos', [])) if routes else 0,
                    'volume_24h': token_price.get('volume24h', 0),
                    'mcap': token_price.get('marketCap', 0),
                    'pair_address': token_address,
                    'created_at': 'Unknown',
                    'logo': token_meta.get('logoURI', ''),
                    'decimals': token_meta.get('decimals', 9),
                    'top_pools': pools,
                    'dexes': [
                        f"[JUPITER](https://jup.ag/swap/SOL-{token_address})",
                        f"[BIRDEYE](https://birdeye.so/token/{token_address})",
                        f"[DEXSCREENER](https://dexscreener.com/solana/{token_address})",
                        f"[SOLSCAN](https://solscan.io/token/{token_address})"
                    ]
                }
                
        except Exception as e:
            self.logger.error(f"Jupiter API error: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None

    async def get_token_data(self, token_address):
        """Fetch token data prioritizing Jupiter API"""
        # Try Jupiter first
        jupiter_data = await self.get_jupiter_data(token_address)
        if jupiter_data:
            return jupiter_data
            
        # If Jupiter fails, try DexScreener
        dex_url = f"{self.dexscreener_api}/pairs/solana/{token_address}"
        async with self.session.get(dex_url) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('pairs') and len(data['pairs']) > 0:
                    pair = data['pairs'][0]
                    return {
                        'name': pair['baseToken']['name'],
                        'symbol': pair['baseToken']['symbol'],
                        'price': float(pair['priceUsd']),
                        'price_change': float(pair['priceChange']['h24']),
                        'liquidity': float(pair['liquidity']['usd']),
                        'volume_24h': float(pair['volume']['h24']),
                        'mcap': float(pair.get('fdv', 0)),
                        'pair_address': pair['pairAddress'],
                        'created_at': pair.get('createTime', ''),
                        'logo': pair['baseToken'].get('logoURI', ''),
                        'dexes': [
                            f"[{pair['dexId'].upper()}](https://dexscreener.com/solana/{pair['pairAddress']})",
                            f"[JUPITER](https://jup.ag/swap/SOL-{token_address})",
                            f"[BIRDEYE](https://birdeye.so/token/{token_address})"
                        ]
                    }

        # Finally, try Birdeye
        bird_url = f"{self.birdeye_api}/token/info?address={token_address}"
        headers = {'X-API-KEY': self.birdeye_key}
        async with self.session.get(bird_url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('success') and data.get('data'):
                    token = data['data']
                    return {
                        'name': token.get('name', 'Unknown'),
                        'symbol': token.get('symbol', 'Unknown'),
                        'price': float(token.get('price', 0)),
                        'price_change': float(token.get('priceChange24h', 0)),
                        'liquidity': float(token.get('liquidity', 0)),
                        'volume_24h': float(token.get('volume24h', 0)),
                        'mcap': float(token.get('marketCap', 0)),
                        'pair_address': token_address,
                        'created_at': 'Unknown',
                        'logo': token.get('logoURI', ''),
                        'dexes': [
                            f"[BIRDEYE](https://birdeye.so/token/{token_address})",
                            f"[JUPITER](https://jup.ag/swap/SOL-{token_address})",
                            f"[DEXSCREENER](https://dexscreener.com/solana/{token_address})"
                        ]
                    }

        self.logger.warning(f"Could not fetch data for token {token_address}")
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

        # Check if message starts with $ and is a token symbol
        if message.content.startswith('$'):
            symbol = message.content[1:].lower()  # Remove $ and convert to lowercase
            
            # Debug logging
            self.logger.info(f"Received token symbol request: {symbol}")
            
            # Check if symbol exists in our token addresses
            if symbol in self.token_addresses:
                token_address = self.token_addresses[symbol]
                try:
                    async with message.channel.typing():
                        token_data = await self.get_token_data(token_address)
                        if token_data:
                            embed = self.create_token_embed(token_data, token_address)
                            await message.channel.send(embed=embed)
                            
                            # Format and send scan info
                            mcap = float(token_data.get('mcap', 0))
                            scan_info = await self.format_scan_info(message, token_data, mcap)
                            if scan_info:
                                await message.channel.send(scan_info)
                        else:
                            await message.channel.send(f"❌ Could not fetch data for ${symbol}")
                except Exception as e:
                    self.logger.error(f"Error processing token symbol {symbol}: {str(e)}")
                    await message.channel.send(f"❌ Error fetching data for ${symbol}")
            else:
                # Only respond if it looks like a token request
                if len(symbol) <= 10:  # Reasonable symbol length
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
