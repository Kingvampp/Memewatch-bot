import discord
from discord.ext import commands
import logging
import aiohttp
import json

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
            # Try pairs endpoint first for exact matches
            pairs_url = f"{self.dexscreener_api}/pairs/solana"
            headers = {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0"
            }
            params = {"q": token_id}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(pairs_url, params=params, headers=headers) as response:
                    data = await response.json()
                    pairs = data.get('pairs', [])
                    
                    if not pairs:
                        # If no pairs found, try search endpoint
                        search_url = f"{self.dexscreener_api}/search?q={token_id}"
                        async with session.get(search_url, headers=headers) as search_response:
                            search_data = await search_response.json()
                            pairs = search_data.get('pairs', [])
                    
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
                    
                    # Get quote token symbol for display
                    quote_symbol = pair['quoteToken']['symbol'].upper()
                    
                    # Create embed
                    embed = discord.Embed(
                        title=f"{pair['baseToken']['symbol']}/{quote_symbol}",
                        description=f"Token Name: {pair['baseToken']['name']}\n" + \
                                  f"Price: {self.format_price(float(pair['priceUsd']))}\n" + \
                                  f"Price Change 24h: {pair['priceChange']['h24']}%\n" + \
                                  f"Market Cap: ${self.format_number(float(pair['marketCap']))}\n" + \
                                  f"Liquidity: ${self.format_number(float(pair['liquidity']['usd']))}\n" + \
                                  f"Volume 24h: ${self.format_number(float(pair['volume']['h24']))}\n\n" + \
                                  f"Contract Address: `{pair['baseToken']['address']}`\n\n" + \
                                  f"[DexScreener](https://dexscreener.com/solana/{pair['pairAddress']}) | " + \
                                  f"[Raydium](https://raydium.io/swap/?inputCurrency={pair['baseToken']['address']}) | " + \
                                  f"[Birdeye](https://birdeye.so/token/{pair['baseToken']['address']}) | " + \
                                  f"[Dextools](https://www.dextools.io/app/solana/pair-explorer/{pair['pairAddress']})",
                        color=0x00ff00
                    )
                    
                    await message.channel.send(embed=embed)
                    
        except Exception as e:
            logging.error(f"Error getting token info: {str(e)}")
            await message.channel.send(f"❌ Could not find token information for {token_id}. Please check the symbol/address and try again.")

async def setup(bot):
    await bot.add_cog(Solana(bot))