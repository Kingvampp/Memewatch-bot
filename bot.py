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

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
            
        if not message.content.startswith('$'):
            return
            
        token_id = message.content[1:].strip().lower()
        if not token_id:
            return
            
        try:
            # Use search endpoint directly
            search_url = f"{self.dexscreener_api}/search?q={token_id}"
            headers = {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers=headers) as response:
                    if response.status != 200:
                        await message.channel.send(f"❌ Could not find token information for {token_id}. Please check the symbol/address and try again.")
                        return
                        
                    data = await response.json()
                    pairs = data.get('pairs', [])
                    
                    # Filter for Solana pairs
                    solana_pairs = [p for p in pairs if p.get('chainId') == 'solana']
                    if not solana_pairs:
                        await message.channel.send(f"❌ Could not find Solana token information for {token_id}. Please check the symbol/address and try again.")
                        return
                    
                    # Filter for USD pairs and sort by volume
                    usd_pairs = [p for p in solana_pairs if p.get('quoteToken', {}).get('symbol', '').upper() in ['USDC', 'USDT', 'USD']]
                    if not usd_pairs:
                        await message.channel.send(f"❌ Could not find USD pair for Solana token {token_id}. Please check the symbol/address and try again.")
                        return
                    
                    # Sort by 24h volume to get the most active pair
                    sorted_pairs = sorted(usd_pairs, key=lambda x: float(x.get('volume', {}).get('h24', 0)), reverse=True)
                    pair = sorted_pairs[0]
                    
                    # Get token info
                    token_name = pair['baseToken']['name']
                    token_symbol = pair['baseToken']['symbol']
                    price = float(pair['priceUsd'])
                    mcap = float(pair['marketCap'])
                    volume = float(pair['volume']['h24'])
                    liquidity = float(pair['liquidity']['usd'])
                    price_change = float(pair['priceChange']['h24'])
                    fdv = float(pair.get('fdv', mcap))  # Use marketcap if FDV not available
                    pool_name = self.get_pool_name(pair)
                    
                    # Get time-based changes
                    h1_change = pair['priceChange'].get('h1', '0')
                    h4_change = pair['priceChange'].get('h4', '0')
                    h12_change = pair['priceChange'].get('h12', '0')
                    
                    # Calculate age
                    age = self.calculate_age(pair.get('pairCreatedAt'))

                    # Get ATH data (using current values as placeholder - you'll need to implement ATH tracking)
                    ath_price = price * 1.5  # Placeholder
                    ath_mcap = mcap * 1.5   # Placeholder
                    ath_time = "5m"         # Placeholder
                    
                    # Check if this is the first scan
                    token_address = pair['baseToken']['address']
                    scan_info = await self.get_scan_info(token_address, message.guild.id)
                    
                    if scan_info:
                        first_scanner_id, scan_time, first_mcap = scan_info
                        first_scanner = await self.bot.fetch_user(int(first_scanner_id))
                        time_ago = self.format_time_ago(scan_time * 1000)
                        scanner_info = f"{message.author.display_avatar.url} {message.author.name} 🏆 {first_scanner.name} @ ${self.format_number(first_mcap)} ⋅ {time_ago}"
                    else:
                        await self.save_scan(token_address, message.author.id, mcap, message.guild.id)
                        scanner_info = f"{message.author.name} You are first in this server @ ${self.format_number(mcap)}"
                    
                    # Format description
                    description = (
                        f"{token_name} [{self.format_number(mcap)}/{'+'if price_change >= 0 else ''}{price_change}%] - {token_symbol}/SOL\n"
                        f"{token_name} @ {pool_name} 🔥\n"
                        f"💰 USD: {self.format_price(price)} ➜ ATH: {self.format_price(ath_price)} [{ath_time}]\n"
                        f"💎 FDV: ${self.format_number(fdv)}\n"
                        f"💫 MC: ${self.format_number(mcap)} ➜ ATH: ${self.format_number(ath_mcap)} [{ath_time}]\n"
                        f"💧 Liq: ${self.format_number(liquidity)}\n"
                        f"📊 Vol: ${self.format_number(volume)} 🕒 Age: {age}\n"
                        f"📈 1H: {h1_change}% • 4H: {h4_change}% • 12H: {h12_change}%\n\n"
                        f"`{token_address}`\n\n"
                        f"[DEX](https://dexscreener.com/solana/{pair['pairAddress']}) • "
                        f"[BIRD](https://birdeye.so/token/{token_address}) • "
                        f"[BLX](https://solscan.io/token/{token_address}) • "
                        f"[SOL](https://solana.fm/address/{token_address}) • "
                        f"[BNK](https://solanabeach.io/token/{token_address}) • "
                        f"[JUP](https://jup.ag/swap/SOL-{token_address})\n\n"
                        f"{scanner_info}"
                    )
                    
                    # Create embed with token image
                    embed = discord.Embed(
                        title=f"{token_symbol}/SOL",
                        description=description,
                        color=0x00ff00 if price_change >= 0 else 0xff0000
                    )
                    
                    # Try to add token image
                    if pair.get('baseToken', {}).get('logoURI'):
                        embed.set_thumbnail(url=pair['baseToken']['logoURI'])
                    
                    await message.channel.send(embed=embed)
                    
        except Exception as e:
            logging.error(f"Error getting token info: {str(e)}")
            await message.channel.send(f"❌ Could not find token information for {token_id}. Please check the symbol/address and try again.")

async def setup(bot):
    await bot.add_cog(Solana(bot))
