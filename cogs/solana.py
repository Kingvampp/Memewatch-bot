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
            'me': 'MEFNBXixkEbait3xn9bkm8WsJzXtVsaJEn4c8Sam21u'  # Verified ME token address
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
        """Create aiohttp session when cog loads"""
        self.session = aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0'})
        
    async def cog_unload(self):
        """Close aiohttp session when cog unloads"""
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

    async def get_jupiter_token_list(self):
        """Fetch complete Jupiter token list"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json'
            }
            
            url = "https://token.jup.ag/strict"
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                self.logger.error(f"Jupiter API returned status {response.status}")
                return None
        except Exception as e:
            self.logger.error(f"Error fetching Jupiter token list: {str(e)}")
            return None

    async def get_jupiter_price_data(self, token_address):
        """Fetch comprehensive price data from Jupiter"""
        try:
            # Get real-time price with detailed metrics
            price_url = f"https://price.jup.ag/v4/price?ids={token_address}&vsToken=So11111111111111111111111111111111111111112"
            
            # Get detailed market info
            market_url = f"https://stats.jup.ag/coingecko/tokens/{token_address}"
            
            # Get OpenBook markets
            openbook_url = f"https://stats.jup.ag/openbook/{token_address}"
            
            async with self.session.get(price_url) as price_response, \
                      self.session.get(market_url) as market_response, \
                      self.session.get(openbook_url) as openbook_response:
                
                price_data = await price_response.json() if price_response.status == 200 else {}
                market_data = await market_response.json() if market_response.status == 200 else {}
                openbook_data = await openbook_response.json() if openbook_response.status == 200 else {}
                
                return {
                    'price_data': price_data,
                    'market_data': market_data,
                    'openbook_data': openbook_data
                }
        except Exception as e:
            self.logger.error(f"Error fetching Jupiter price data: {str(e)}")
        return None

    async def get_jupiter_pool_data(self, token_address):
        """Fetch comprehensive pool and DEX data"""
        try:
            # Get all pools
            pools_url = f"https://stats.jup.ag/coingecko/pairs?base={token_address}"
            
            # Get Raydium pools
            raydium_url = f"https://stats.jup.ag/raydium/{token_address}"
            
            # Get Orca pools
            orca_url = f"https://stats.jup.ag/orca/{token_address}"
            
            async with self.session.get(pools_url) as pools_response, \
                      self.session.get(raydium_url) as raydium_response, \
                      self.session.get(orca_url) as orca_response:
                
                pools_data = await pools_response.json() if pools_response.status == 200 else []
                raydium_data = await raydium_response.json() if raydium_response.status == 200 else {}
                orca_data = await orca_response.json() if orca_response.status == 200 else {}
                
                # Combine and sort pools by liquidity
                all_pools = []
                
                # Add Raydium pools
                if isinstance(raydium_data, dict):
                    for pool in raydium_data.values():
                        all_pools.append({
                            'name': 'Raydium',
                            'liquidity': float(pool.get('liquidity', 0)),
                            'volume_24h': float(pool.get('volume24h', 0)),
                            'fee_24h': float(pool.get('fee24h', 0))
                        })
                
                # Add Orca pools
                if isinstance(orca_data, dict):
                    for pool in orca_data.values():
                        all_pools.append({
                            'name': 'Orca',
                            'liquidity': float(pool.get('liquidity', 0)),
                            'volume_24h': float(pool.get('volume24h', 0)),
                            'fee_24h': float(pool.get('fee24h', 0))
                        })
                
                # Add other pools
                for pool in pools_data:
                    all_pools.append({
                        'name': pool.get('name', 'Unknown'),
                        'liquidity': float(pool.get('liquidity', 0)),
                        'volume_24h': float(pool.get('volume24h', 0)),
                        'fee_24h': float(pool.get('fee24h', 0))
                    })
                
                # Sort pools by liquidity
                all_pools.sort(key=lambda x: x['liquidity'], reverse=True)
                
                return all_pools
                
        except Exception as e:
            self.logger.error(f"Error fetching Jupiter pool data: {str(e)}")
        return None

    async def get_token_data(self, token_address):
        """Fetch comprehensive token data from Jupiter"""
        try:
            # Get all data concurrently
            token_list, price_data, pool_data = await asyncio.gather(
                self.get_jupiter_token_list(),
                self.get_jupiter_price_data(token_address),
                self.get_jupiter_pool_data(token_address)
            )
            
            if not price_data or not price_data.get('price_data', {}).get('data', {}).get(token_address):
                return None
                
            token_meta = token_list.get('tokens', {}).get(token_address, {}) if token_list else {}
            price_info = price_data['price_data']['data'][token_address]
            market_info = price_data['market_data']
            
            # Calculate total liquidity and volume
            total_liquidity = sum(pool['liquidity'] for pool in pool_data) if pool_data else 0
            total_volume = sum(pool['volume_24h'] for pool in pool_data) if pool_data else 0
            total_fees = sum(pool['fee_24h'] for pool in pool_data) if pool_data else 0
            
            # Get top pools with detailed info
            top_pools = pool_data[:3] if pool_data else []
            pool_info = [
                f"{pool['name']} (${self.format_number(pool['liquidity'])} - Vol: ${self.format_number(pool['volume_24h'])})"
                for pool in top_pools
            ]
            
            return {
                'name': token_meta.get('name', 'Unknown'),
                'symbol': token_meta.get('symbol', 'Unknown'),
                'price': float(price_info.get('price', 0)),
                'price_change_1h': float(market_info.get('price_change_percentage_1h', 0)),
                'price_change_4h': float(market_info.get('price_change_percentage_4h', 0)),
                'price_change_24h': float(market_info.get('price_change_percentage_24h', 0)),
                'mcap': float(market_info.get('market_cap', 0)),
                'fdv': float(market_info.get('fully_diluted_valuation', 0)),
                'liquidity': total_liquidity,
                'volume_24h': total_volume,
                'fees_24h': total_fees,
                'pair_address': token_address,
                'logo': token_meta.get('logoURI', ''),
                'created_at': market_info.get('created_at'),
                'holders': market_info.get('holders', 'Unknown'),
                'total_supply': market_info.get('total_supply', 'Unknown'),
                'circulating_supply': market_info.get('circulating_supply', 'Unknown'),
                'top_pools': pool_info,
                'dexes': [
                    f"[JUPITER](https://jup.ag/swap/SOL-{token_address})",
                    f"[BIRDEYE](https://birdeye.so/token/{token_address})",
                    f"[DEXSCREENER](https://dexscreener.com/solana/{token_address})",
                    f"[SOLSCAN](https://solscan.io/token/{token_address})"
                ]
            }

        except Exception as e:
            self.logger.error(f"Error in get_token_data: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None

    async def format_token_embed(self, token_data):
        """Create a beautifully formatted embed for token data"""
        try:
            # Create main embed
            embed = discord.Embed(
                title=f"{token_data['symbol']}/SOL • {token_data['name']}",
                color=discord.Color.green() if token_data['price_change_24h'] >= 0 else discord.Color.red()
            )

            # Price and Market Stats
            price_info = (
                f"💰 **Price:** ${token_data['price']:.10f}\n"
                f"📊 **Changes:**\n"
                f"• 1H: {token_data['price_change_1h']:+.2f}%\n"
                f"• 4H: {token_data['price_change_4h']:+.2f}%\n"
                f"• 24H: {token_data['price_change_24h']:+.2f}%\n"
            )
            embed.add_field(name="Price Information", value=price_info, inline=False)

            # Market Metrics
            market_info = (
                f"💫 **Market Cap:** ${self.format_number(token_data['mcap'])}\n"
                f"💎 **FDV:** ${self.format_number(token_data['fdv'])}\n"
                f"💦 **Liquidity:** ${self.format_number(token_data['liquidity'])}\n"
                f"📈 **24h Volume:** ${self.format_number(token_data['volume_24h'])}\n"
                f"💰 **24h Fees:** ${self.format_number(token_data['fees_24h'])}\n"
            )
            embed.add_field(name="Market Metrics", value=market_info, inline=False)

            # Supply Information
            supply_info = (
                f"🔄 **Circulating:** {self.format_number(token_data['circulating_supply'])}\n"
                f"📊 **Total:** {self.format_number(token_data['total_supply'])}\n"
                f"👥 **Holders:** {token_data['holders']}\n"
            )
            embed.add_field(name="Supply Info", value=supply_info, inline=False)

            # Top Pools
            if token_data['top_pools']:
                pools_info = "\n".join([
                    f"• {pool}" for pool in token_data['top_pools']
                ])
                embed.add_field(name="🌊 Top Liquidity Pools", value=pools_info, inline=False)

            # Quick Links
            links = "\n".join(token_data['dexes'])
            embed.add_field(name="🔗 Quick Links", value=links, inline=False)

            # Footer with address
            embed.set_footer(text=f"Token: {token_data['pair_address']}")

            # Set thumbnail if logo exists
            if token_data.get('logo'):
                embed.set_thumbnail(url=token_data['logo'])

            return embed

        except Exception as e:
            self.logger.error(f"Error formatting embed: {str(e)}")
            return None

    def format_number(self, num):
        """Format numbers with better readability"""
        try:
            num = float(num)
            if num >= 1_000_000_000_000:
                return f"{num/1_000_000_000_000:.2f}T"
            elif num >= 1_000_000_000:
                return f"{num/1_000_000_000:.2f}B"
            elif num >= 1_000_000:
                return f"{num/1_000_000:.2f}M"
            elif num >= 1_000:
                return f"{num/1_000:.2f}K"
            elif num >= 1:
                return f"{num:.2f}"
            else:
                return f"{num:.10f}".rstrip('0').rstrip('.')
        except (ValueError, TypeError):
            return "0.00"

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
            token_input = message.content[1:].strip().lower()
            
            try:
                # Check if input is a valid Solana address
                if len(token_input) == 44 or len(token_input) == 32:
                    token_address = token_input
                else:
                    # Try to get token info from Jupiter
                    headers = {
                        'User-Agent': 'Mozilla/5.0',
                        'Accept': 'application/json'
                    }
                    meta_url = "https://token.jup.ag/all"
                    async with self.session.get(meta_url, headers=headers) as response:
                        if response.status == 200:
                            tokens = await response.json()
                            # Search for token by symbol
                            token_address = None
                            for addr, info in tokens.get('tokens', {}).items():
                                if info.get('symbol', '').lower() == token_input:
                                    token_address = addr
                                    break
                            
                            if not token_address:
                                await message.channel.send(f"❌ Could not find token: ${token_input}")
                                return

                async with message.channel.typing():
                    token_data = await self.get_token_data(token_address)
                    if token_data:
                        embed = await self.format_token_embed(token_data)
                        if embed:
                            await message.channel.send(embed=embed)
                        else:
                            await message.channel.send(f"❌ Error formatting data for ${token_input}")
                    else:
                        await message.channel.send(f"❌ Could not fetch data for ${token_input}")
            except Exception as e:
                self.logger.error(f"Error processing ${token_input}: {str(e)}")
                self.logger.error(traceback.format_exc())
                await message.channel.send(f"❌ Error processing ${token_input}")

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
💎 MC: {format_number(float(data['mcap']))} ➡︎ ATH: {format_number(float(ath_mcap))} [{ath_time}]
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
