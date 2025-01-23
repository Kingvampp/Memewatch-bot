import discord
from discord.ext import commands
import logging
import aiohttp
import json
from datetime import datetime, timezone
import sqlite3
import os

class Solana(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.dexscreener_api = "https://api.dexscreener.com/latest/dex"
        self.birdeye_api = "https://public-api.birdeye.so/public"
        self.raydium_api = "https://api.raydium.io/v2"
        self.solscan_api = "https://public-api.solscan.io"
        self.setup_database()
        
    def setup_database(self):
        db_path = 'token_scans.db'
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS token_scans
                    (token_address TEXT, first_scanner TEXT, scan_time TIMESTAMP, 
                     first_mcap REAL, guild_id TEXT,
                     PRIMARY KEY (token_address, guild_id))''')
        conn.commit()
        conn.close()

    def format_number(self, num):
        if num >= 1_000_000_000_000:  # Trillion
            return f"{num/1_000_000_000_000:.2f}T"
        elif num >= 1_000_000_000:  # Billion
            return f"{num/1_000_000_000:.2f}B"
        elif num >= 1_000_000:  # Million
            return f"{num/1_000_000:.2f}M"
        elif num >= 1_000:  # Thousand
            return f"{num/1_000:.2f}K"
        return f"{num:.2f}"

    def format_price(self, price):
        if price < 0.0001:
            return f"${price:.10f}"
        elif price < 0.01:
            return f"${price:.6f}"
        else:
            return f"${price:.4f}"

    def calculate_age(self, pair_created_at):
        if not pair_created_at:
            return "Unknown"
        created_time = datetime.fromtimestamp(pair_created_at / 1000, timezone.utc)
        now = datetime.now(timezone.utc)
        days = (now - created_time).days
        return f"{days}d ago"

    def get_pool_name(self, pair):
        dex = pair.get('dexId', '').lower()
        if 'raydium' in dex:
            return 'Raydium'
        elif 'orca' in dex:
            return 'Orca'
        elif 'meteora' in dex:
            return 'Meteora'
        return dex.capitalize()

    def format_time_ago(self, timestamp):
        if not timestamp:
            return "Unknown"
        then = datetime.fromtimestamp(timestamp / 1000, timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - then
        
        if delta.days > 0:
            return f"{delta.days}d"
        elif delta.seconds >= 3600:
            return f"{delta.seconds // 3600}h"
        elif delta.seconds >= 60:
            return f"{delta.seconds // 60}m"
        return f"{delta.seconds}s"

    async def get_scan_info(self, token_address, guild_id):
        conn = sqlite3.connect('token_scans.db')
        c = conn.cursor()
        c.execute('''SELECT first_scanner, scan_time, first_mcap 
                    FROM token_scans 
                    WHERE token_address = ? AND guild_id = ?''', 
                    (token_address, str(guild_id)))
        result = c.fetchone()
        conn.close()
        return result

    async def save_scan(self, token_address, scanner_id, mcap, guild_id):
        conn = sqlite3.connect('token_scans.db')
        c = conn.cursor()
        try:
            c.execute('''INSERT INTO token_scans 
                        (token_address, first_scanner, scan_time, first_mcap, guild_id)
                        VALUES (?, ?, ?, ?, ?)''',
                        (token_address, str(scanner_id), datetime.now(timezone.utc).timestamp(),
                         mcap, str(guild_id)))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    async def get_birdeye_data(self, token_address):
        """Fetch token data from Birdeye API"""
        endpoints = {
            'token_info': f"{self.birdeye_api}/token_info?address={token_address}",
            'holders': f"{self.birdeye_api}/token_holders?address={token_address}&limit=5",
            'price': f"{self.birdeye_api}/price?address={token_address}"
        }
        
        async with aiohttp.ClientSession() as session:
            data = {}
            for key, url in endpoints.items():
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            result = await response.json()
                            data[key] = result.get('data', {})
                except Exception as e:
                    logging.error(f"Birdeye {key} API error: {str(e)}")
            return data

    async def get_raydium_data(self, token_address):
        """Fetch liquidity and trading data from Raydium"""
        url = f"{self.raydium_api}/main/pool/{token_address}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
            except Exception as e:
                logging.error(f"Raydium API error: {str(e)}")
            return {}

    async def get_solscan_data(self, token_address):
        """Fetch token metadata from Solscan"""
        url = f"{self.solscan_api}/token/{token_address}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
            except Exception as e:
                logging.error(f"Solscan API error: {str(e)}")
            return {}

    async def get_token_data(self, token_id):
        """Aggregate data from multiple sources"""
        try:
            # First get token address if symbol provided
            search_url = f"{self.dexscreener_api}/search?q={token_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url) as response:
                    if response.status != 200:
                        raise Exception("Token not found")
                    
                    data = await response.json()
                    pairs = data.get('pairs', [])
                    solana_pairs = [p for p in pairs if p.get('chainId') == 'solana']
                    if not solana_pairs:
                        raise Exception("No Solana pairs found")
                    
                    pair = solana_pairs[0]
                    token_address = pair['baseToken']['address']
                    
                    # Fetch data from all sources
                    birdeye_data = await self.get_birdeye_data(token_address)
                    raydium_data = await self.get_raydium_data(token_address)
                    solscan_data = await self.get_solscan_data(token_address)
                    
                    # Compile token data
                    price = float(pair['priceUsd'])
                    mcap = float(pair['marketCap'])
                    
                    # Get holder distribution
                    holders = birdeye_data.get('holders', [])
                    top_holders = [float(h.get('percentage', 0)) for h in holders[:5]]
                    
                    return {
                        "name": pair['baseToken']['name'],
                        "symbol": pair['baseToken']['symbol'],
                        "price": price,
                        "fdv": float(pair.get('fdv', mcap)),
                        "mcap": mcap,
                        "ath_price": float(birdeye_data.get('price', {}).get('ath', price)),
                        "ath_time": self.format_time_ago(birdeye_data.get('price', {}).get('athTime')),
                        "liquidity": float(pair['liquidity']['usd']),
                        "volume": float(pair['volume']['h24']),
                        "age": self.calculate_age(pair.get('pairCreatedAt')),
                        "h1_change": float(pair['priceChange'].get('h1', 0)),
                        "h4_change": float(pair['priceChange'].get('h4', 0)),
                        "top_holders": top_holders,
                        "image_url": pair['baseToken'].get('logoURI'),
                        "pair_address": pair['pairAddress'],
                        "token_address": token_address
                    }
                    
        except Exception as e:
            logging.error(f"Error getting token data: {str(e)}")
            raise

    def format_response(self, token_data, user, first_scan_info):
        """Format token data for Discord embed"""
        top_holders_sum = sum(token_data["top_holders"])
        top_holders_str = "⋅".join(f"{h:.1f}" for h in token_data["top_holders"])
        
        description = (
            f"{token_data['name']} ({token_data['symbol']}/SOL)\n\n"
            f"💰 USD: ${token_data['price']:.10f}\n"
            f"💎 FDV: ${self.format_number(token_data['fdv'])}\n"
            f"💫 MC: ${self.format_number(token_data['mcap'])} ➡︎ ATH: ${self.format_number(token_data['mcap'] * (token_data['ath_price']/token_data['price']))} [{token_data['ath_time']}]\n"
            f"💦 Liq: ${self.format_number(token_data['liquidity'])}\n"
            f"📊 Vol: ${self.format_number(token_data['volume'])} 🕰️ Age: {token_data['age']}\n"
            f"🚀 1H: {token_data['h1_change']}% 🚀 4H: {token_data['h4_change']}%\n"
            f"👥 TH: {top_holders_str} [{top_holders_sum:.1f}%]\n\n"
            f"`{token_data['token_address']}`\n\n"
            f"[DEX](https://dexscreener.com/solana/{token_data['pair_address']}) • "
            f"[BIRD](https://birdeye.so/token/{token_data['token_address']}) • "
            f"[BLX](https://solscan.io/token/{token_data['token_address']}) • "
            f"[SOL](https://solana.fm/address/{token_data['token_address']}) • "
            f"[BNK](https://solanabeach.io/token/{token_data['token_address']}) • "
            f"[JUP](https://jup.ag/swap/SOL-{token_data['token_address']})\n\n"
        )
        
        if first_scan_info:
            first_scanner, first_mcap, first_scan_time = first_scan_info
            mcap_change = "📉 Token dipped!" if token_data['mcap'] < first_mcap else "📈 Token pumped!"
            description += (
                f"{user.display_name} ${self.format_number(token_data['mcap'])} {mcap_change} ⋅ "
                f"{first_scanner} @ ${self.format_number(first_mcap)} ⋅ {first_scan_time}"
            )
        else:
            description += f"{user.display_name} you are first in this server @ ${self.format_number(token_data['mcap'])}"
        
        return description

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.content.startswith('$'):
            return
        
        token_id = message.content[1:].strip().lower()
        if not token_id:
            return
        
        try:
            token_data = await self.get_token_data(token_id)
            first_scan_info = await self.get_scan_info(token_data['token_address'], message.guild.id)
            
            if not first_scan_info:
                await self.save_scan(token_data['token_address'], message.author.id, token_data['mcap'], message.guild.id)
            
            response = self.format_response(token_data, message.author, first_scan_info)
            
            embed = discord.Embed(
                title=f"{token_data['symbol']}/SOL",
                description=response,
                color=0x00ff00 if token_data['h1_change'] >= 0 else 0xff0000
            )
            
            if token_data.get('image_url'):
                embed.set_thumbnail(url=token_data['image_url'])
            
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Error processing token {token_id}: {str(e)}")
            await message.channel.send(f"❌ Could not find token information for {token_id}. Please check the symbol/address and try again.")

    async def get_ath_data(self, pair):
        """Get ATH data using multiple DEX APIs for comprehensive price history"""
        try:
            # Get current price and mcap from DexScreener
            current_price = float(pair.get('priceUsd', 0))
            current_mcap = float(pair.get('marketCap', 0))
            token_address = pair['baseToken']['address']
            
            # Initialize ATH tracking
            ath_price = float(pair.get('priceMax', current_price))
            ath_date = pair.get('priceMaxDate', None)
            
            # Check multiple sources for ATH
            apis = {
                'birdeye': f"https://public-api.birdeye.so/public/history_price?address={token_address}&type=max",
                'raydium': f"https://api.raydium.io/v2/main/price?address={token_address}&range=max",
                'dexscreener': f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair['pairAddress']}"
            }
            
            async with aiohttp.ClientSession() as session:
                for source, url in apis.items():
                    try:
                        async with session.get(url) as response:
                            if response.status == 200:
                                data = await response.json()
                                
                                # Extract ATH based on source
                                if source == 'birdeye':
                                    birdeye_ath = float(data.get('data', {}).get('value', 0))
                                    if birdeye_ath > ath_price:
                                        ath_price = birdeye_ath
                                        
                                elif source == 'raydium':
                                    raydium_ath = float(data.get('data', {}).get('maxPrice', 0))
                                    if raydium_ath > ath_price:
                                        ath_price = raydium_ath
                                        
                                elif source == 'dexscreener':
                                    dex_ath = float(data.get('pair', {}).get('priceMax', 0))
                                    if dex_ath > ath_price:
                                        ath_price = dex_ath
                                        ath_date = data.get('pair', {}).get('priceMaxDate')
                                        
                    except Exception as e:
                        logging.error(f"Error fetching from {source}: {str(e)}")
                        continue
            
            # Calculate ATH mcap using the ratio
            ath_mcap = current_mcap * (ath_price / current_price) if current_price > 0 else current_mcap
            
            # Format time
            ath_time = self.format_time_ago(ath_date) if ath_date else "Now"
            
            return ath_price, ath_mcap, ath_time
            
        except Exception as e:
            logging.error(f"Error calculating ATH data: {str(e)}")
            return current_price, current_mcap, "Now"

async def setup(bot):
    await bot.add_cog(Solana(bot))
