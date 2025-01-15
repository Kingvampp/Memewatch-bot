import discord
from discord.ext import commands
import logging
import aiohttp
import json
from datetime import datetime, timezone

class Solana(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.dexscreener_api = "https://api.dexscreener.com/latest/dex"
        
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
                    
                    # Get time-based changes
                    h1_change = pair['priceChange'].get('h1', '0')
                    h4_change = pair['priceChange'].get('h4', '0')
                    h12_change = pair['priceChange'].get('h12', '0')
                    
                    # Calculate age
                    age = self.calculate_age(pair.get('pairCreatedAt'))
                    
                    # Format description
                    description = (
                        f"{token_name} [{self.format_number(mcap)}/{'+'if price_change >= 0 else ''}{price_change}%] - {token_symbol}/SOL\n"
                        f"{token_name} @ Raydium 🔥\n"
                        f"💰 USD: {self.format_price(price)}\n"
                        f"💎 FDV: ${self.format_number(fdv)}\n"
                        f"💫 MC: ${self.format_number(mcap)}\n"
                        f"💧 Liq: ${self.format_number(liquidity)}\n"
                        f"📊 Vol: ${self.format_number(volume)} 🕒 Age: {age}\n"
                        f"📈 1H: {h1_change}% • 4H: {h4_change}% • 12H: {h12_change}%\n\n"
                        f"`{pair['baseToken']['address']}`\n\n"
                        f"[DEX](https://dexscreener.com/solana/{pair['pairAddress']}) • "
                        f"[BIRD](https://birdeye.so/token/{pair['baseToken']['address']}) • "
                        f"[BLX](https://solscan.io/token/{pair['baseToken']['address']}) • "
                        f"[SOL](https://solana.fm/address/{pair['baseToken']['address']}) • "
                        f"[BNK](https://solanabeach.io/token/{pair['baseToken']['address']}) • "
                        f"[JUP](https://jup.ag/swap/SOL-{pair['baseToken']['address']})"
                    )
                    
                    # Create embed
                    embed = discord.Embed(
                        title=f"{token_symbol} Price",
                        description=description,
                        color=0x00ff00 if price_change >= 0 else 0xff0000
                    )
                    
                    await message.channel.send(embed=embed)
                    
        except Exception as e:
            logging.error(f"Error getting token info: {str(e)}")
            await message.channel.send(f"❌ Could not find token information for {token_id}. Please check the symbol/address and try again.")

async def setup(bot):
    await bot.add_cog(Solana(bot))