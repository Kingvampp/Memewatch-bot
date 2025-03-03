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
        
        # Get db if available, otherwise None
        self.db = getattr(bot, 'db', None)
        
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

        # Log initialization
        self.logger.info("Solana cog initialized")

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
        self.logger.info("Solana cog session created")
        
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
        """Fetch data from DexScreener"""
        try:
            url = f"{self.dexscreener_api}/tokens/{token_address}"
            async with self.session.get(url, ssl=True) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('pairs') and len(data['pairs']) > 0:
                        pair = data['pairs'][0]
                        return {
                            'name': pair['baseToken']['name'],
                            'symbol': pair['baseToken']['symbol'],
                            'price': float(pair['priceUsd']),
                            'price_change_24h': float(pair['priceChange']['h24'] or 0),
                            'liquidity': float(pair['liquidity']['usd']),
                            'volume_24h': float(pair['volume']['h24']),
                            'pair_address': pair['pairAddress'],
                            'dex': pair['dexId']
                        }
                return None
        except Exception as e:
            self.logger.error(f"DexScreener API error: {str(e)}")
            return None

    async def get_solscan_data(self, token_address):
        """Fetch data from Solscan"""
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            meta_url = f"https://public-api.solscan.io/token/meta/{token_address}"
            market_url = f"https://public-api.solscan.io/market/token/{token_address}"
            
            async with self.session.get(meta_url, headers=headers) as meta_response, \
                      self.session.get(market_url, headers=headers) as market_response:
                
                if meta_response.status == 200 and market_response.status == 200:
                    meta_data = await meta_response.json()
                    market_data = await market_response.json()
                    
                    return {
                        'name': meta_data.get('name'),
                        'symbol': meta_data.get('symbol'),
                        'price': float(market_data.get('priceUsdt', 0)),
                        'volume_24h': float(market_data.get('volume24h', 0)),
                        'mcap': float(market_data.get('marketCap', 0)),
                        'holder_count': meta_data.get('holder'),
                        'supply': meta_data.get('supply')
                    }
                return None
        except Exception as e:
            self.logger.error(f"Solscan API error: {str(e)}")
            return None

    async def get_raydium_data(self, token_address):
        """Fetch data from Raydium"""
        try:
            price_url = "https://api.raydium.io/v2/main/price"
            tokens_url = "https://api.raydium.io/v2/sdk/token/raydium.mainnet.json"
            
            async with self.session.get(price_url) as price_response, \
                      self.session.get(tokens_url) as tokens_response:
                
                if price_response.status == 200 and tokens_response.status == 200:
                    price_data = await price_response.json()
                    tokens_data = await tokens_response.json()
                    
                    token_info = tokens_data.get(token_address)
                    price_info = price_data.get(token_address)
                    
                    if token_info and price_info:
                        return {
                            'name': token_info.get('name'),
                            'symbol': token_info.get('symbol'),
                            'price': float(price_info.get('price', 0)),
                            'decimals': token_info.get('decimals')
                        }
                return None
        except Exception as e:
            self.logger.error(f"Raydium API error: {str(e)}")
            return None

    async def get_token_data(self, token_address):
        """Fetch token data from multiple sources"""
        try:
            # Try all APIs concurrently
            jupiter_data, dex_data, solscan_data, raydium_data = await asyncio.gather(
                self.get_jupiter_price_data(token_address),
                self.get_dexscreener_data(token_address),
                self.get_solscan_data(token_address),
                self.get_raydium_data(token_address),
                return_exceptions=True
            )

            # Combine data from all sources
            combined_data = {}
            
            # Prioritize Jupiter data
            if isinstance(jupiter_data, dict):
                combined_data.update(jupiter_data)
            
            # Add DexScreener data if available
            if isinstance(dex_data, dict):
                for key, value in dex_data.items():
                    if not combined_data.get(key):
                        combined_data[key] = value
            
            # Add Solscan data if available
            if isinstance(solscan_data, dict):
                for key, value in solscan_data.items():
                    if not combined_data.get(key):
                        combined_data[key] = value
            
            # Add Raydium data if available
            if isinstance(raydium_data, dict):
                for key, value in raydium_data.items():
                    if not combined_data.get(key):
                        combined_data[key] = value

            return combined_data if combined_data else None

        except Exception as e:
            self.logger.error(f"Error fetching token data: {str(e)}")
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

    async def format_token_embed(self, token_data):
        """Create a beautifully formatted embed for token data"""
        try:
            # Create main embed with token name and symbol
            embed = discord.Embed(
                title=f"{token_data['symbol']}/SOL • {token_data['name']}",
                color=discord.Color.green() if token_data['price_change'] >= 0 else discord.Color.red()
            )

            # Price Information
            price_info = (
                f"💰 **Price:** ${self.format_price(token_data['price'])}\n"
                f"📊 **24h Change:** {token_data['price_change']:+.2f}%\n"
            )
            embed.add_field(name="Price Information", value=price_info, inline=False)

            # Market Metrics
            if token_data.get('mcap'):
                market_info = f"💫 **Market Cap:** ${self.format_number(token_data['mcap'])}\n"
                embed.add_field(name="Market Metrics", value=market_info, inline=False)

            # Quick Links
            if token_data.get('dexes'):
                links = "\n".join(token_data['dexes'])
                embed.add_field(name="🔗 Quick Links", value=links, inline=False)

            # Set thumbnail if logo exists
            if token_data.get('logo'):
                embed.set_thumbnail(url=token_data['logo'])

            # Footer with address
            embed.set_footer(text=f"Token: {token_data['pair_address']}")

            return embed

        except Exception as e:
            self.logger.error(f"Error formatting embed: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None

    def format_number(self, num):
        """Format large numbers with K, M, B, T suffixes"""
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
            return f"{num:.2f}"
        except (ValueError, TypeError):
            return "0.00"

    def format_price(self, price):
        """Format price with appropriate decimal places"""
        try:
            price = float(price)
            if price < 0.00000001:
                return f"{price:.10f}"
            elif price < 0.000001:
                return f"{price:.8f}"
            elif price < 0.0001:
                return f"{price:.6f}"
            elif price < 0.01:
                return f"{price:.4f}"
            return f"{price:.2f}"
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

    @commands.command(name='token')
    async def token_command(self, ctx, token_id: str = None):
        """Get token information"""
        if not token_id:
            await ctx.send("❌ Please provide a token symbol or address")
            return
            
        try:
            # Get token address from known tokens or use input as address
            token_id = token_id.lower()
            token_address = self.token_addresses.get(token_id, token_id)
            
            async with ctx.typing():
                # Initialize session if not exists
                if not self.session:
                    self.session = aiohttp.ClientSession()
                
                # Get token data from Jupiter
                token_data = await self.get_token_data(token_address)
                
                if not token_data:
                    await ctx.send(f"❌ Could not find token information for {token_id}")
                    return
                    
                # Create and send embed
                embed = await self.format_token_embed(token_data)
                if embed:
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ Error formatting token information")

        except Exception as e:
            self.logger.error(f"Error processing token command: {str(e)}")
            self.logger.error(traceback.format_exc())
            await ctx.send("❌ An error occurred while processing your request")

    async def get_token_address(self, symbol):
        """Get token address from symbol"""
        try:
            # Known token addresses
            known_tokens = {
                'bonk': 'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263',
                'me': 'MEFNBXixkEbait3xn9bkm8WsJzXtVsaJEn4c8Sam21u',
                'jup': 'JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN',
            }
            
            # Check known tokens first
            if symbol in known_tokens:
                return known_tokens[symbol]

            # Try Jupiter API
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json'
            }
            
            # Try both APIs for redundancy
            apis = [
                "https://token.jup.ag/all",
                "https://cache.jup.ag/tokens"
            ]
            
            for api in apis:
                try:
                    async with self.session.get(api, headers=headers, timeout=10) as response:
                        if response.status == 200:
                            tokens = await response.json()
                            for addr, info in tokens.get('tokens', {}).items():
                                if info.get('symbol', '').lower() == symbol:
                                    return addr
                except Exception as e:
                    self.logger.error(f"Error with {api}: {str(e)}")
                    continue

            return None
            
        except Exception as e:
            self.logger.error(f"Error in get_token_address: {str(e)}")
            return None

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle $symbol messages"""
        if message.author.bot:
            return

        if message.content.startswith('$'):
            token_input = message.content[1:].strip().lower()
            self.logger.info(f"Processing token request: {token_input}")
            
            try:
                async with message.channel.typing():
                    # Get token info first
                    token_info = await self.get_token_info(token_input)
                    
                    if token_info:
                        self.logger.info(f"Found token info: {token_info['address']}")
                        token_data = await self.get_token_data(token_info['address'])
                        
                        if token_data:
                            embed = await self.format_token_embed(token_data)
                            if embed:
                                await message.channel.send(embed=embed)
                            else:
                                await message.channel.send(f"❌ Error formatting data for ${token_input}")
                        else:
                            await message.channel.send(f"❌ Could not fetch price data for ${token_input}")
                    else:
                        await message.channel.send(f"❌ Could not find token information for {token_input}")
                        
            except Exception as e:
                self.logger.error(f"Error processing token request: {str(e)}")
                self.logger.error(traceback.format_exc())
                await message.channel.send(f"❌ Error processing request for ${token_input}")

    @commands.command(name='ping')
    async def ping(self, ctx):
        """Simple ping command to check if bot is responsive"""
        try:
            self.logger.info(f"[PING] Command received from {ctx.author.name}")
            await ctx.send("🏓 Pong!")
        except Exception as e:
            self.logger.error(f"[PING] Error: {str(e)}")
            await ctx.send("❌ An error occurred.")

    def create_token_embed(self, dex_data, birdeye_data=None):
        """Create Discord embed with token information"""
        try:
            price = float(dex_data['priceUsd'])
            price_change = float(dex_data['priceChange']['h24'])
            mcap = float(dex_data['marketCap'])
            liquidity = float(dex_data['liquidity']['usd'])
            volume = float(dex_data['volume']['h24'])
            
            embed = discord.Embed(
                title=f"{dex_data['baseToken']['symbol']}/SOL",
                description=f"{dex_data['baseToken']['name']} Price and Analytics",
                color=discord.Color.green() if price_change >= 0 else discord.Color.red()
            )
            
            # Add price and metrics
            embed.add_field(
                name="💰 Price",
                value=f"${self.format_price(price)}",
                inline=True
            )
            embed.add_field(
                name="📈 24h Change",
                value=f"{price_change:+.2f}%",
                inline=True
            )
            embed.add_field(
                name="💎 Market Cap",
                value=f"${self.format_number(mcap)}",
                inline=True
            )
            
            # Add volume and liquidity
            embed.add_field(
                name="💧 Liquidity",
                value=f"${self.format_number(liquidity)}",
                inline=True
            )
            embed.add_field(
                name="📊 24h Volume",
                value=f"${self.format_number(volume)}",
                inline=True
            )
            
            # Add links
            token_address = dex_data['baseToken']['address']
            embed.add_field(
                name="🔗 Links",
                value=(
                    f"[DexScreener](https://dexscreener.com/solana/{dex_data['pairAddress']}) • "
                    f"[Birdeye](https://birdeye.so/token/{token_address}) • "
                    f"[Solscan](https://solscan.io/token/{token_address})"
                ),
                inline=False
            )
            
            return embed
            
        except Exception as e:
            self.logger.error(f"Error creating embed: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None

    def validate_token_address(self, address):
        """Validate Solana token address format"""
        return len(address) == 44 and address.isalnum()

    async def format_scan_info(self, ctx, token_data, mcap):
        """Format scan information for display"""
        try:
            # Skip if no database available
            if not self.db:
                return ""
                
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

    async def get_token_info(self, symbol_or_address):
        """Get token information from Jupiter"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json'
            }
            
            # Try Jupiter token list API
            url = "https://token.jup.ag/all"
            self.logger.info(f"Fetching token list from {url}")
            
            async with self.session.get(url, headers=headers, ssl=True) as response:
                if response.status == 200:
                    tokens = await response.json()
                    token_info = None
                    
                    # Search by address or symbol
                    for addr, info in tokens.get('tokens', {}).items():
                        if addr.lower() == symbol_or_address.lower() or info.get('symbol', '').lower() == symbol_or_address.lower():
                            token_info = {'address': addr, **info}
                            break
                    
                    return token_info
                else:
                    self.logger.error(f"Jupiter API returned status {response.status}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error fetching token info: {str(e)}")
            return None

async def setup(bot):
    """Set up the Solana cog"""
    try:
        cog = Solana(bot)
        await bot.add_cog(cog)
        cog.logger.info("Solana cog loaded successfully")
    except Exception as e:
        logging.error(f"Error loading Solana cog: {str(e)}")
        logging.error(traceback.format_exc())
