import os
import discord
from discord.ext import commands
import requests
from dotenv import load_dotenv
import json
from datetime import datetime
import time

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Initialize bot with command prefix '$'
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='$', intents=intents)

def get_token_info(query):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'accept': 'application/json'
        }

        # First try DEXScreener API
        dex_url = f"https://api.dexscreener.com/latest/dex/search?q={query}"
        dex_response = requests.get(dex_url, headers=headers)
        dex_data = dex_response.json()

        if not dex_data.get('pairs') or len(dex_data['pairs']) == 0:
            return f"Token '{query}' not found on DEXScreener."

        # Get the first pair with good liquidity
        pair = None
        for p in dex_data['pairs']:
            if float(p.get('liquidity', {}).get('usd', 0)) > 1000:  # Min $1000 liquidity
                pair = p
                break
        
        if not pair:
            pair = dex_data['pairs'][0]  # Fallback to first pair if none with good liquidity

        # Create embed
        token_name = pair.get('baseToken', {}).get('name', 'Unknown Token')
        token_symbol = pair.get('baseToken', {}).get('symbol', '???')
        chain = pair.get('chainId', 'unknown')
        contract = pair.get('baseToken', {}).get('address', '')

        embed = discord.Embed(
            title=f"{token_name} ({token_symbol})",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        # Add price info
        price_usd = float(pair.get('priceUsd', 0))
        price_str = f"${price_usd:.12f}" if price_usd < 0.000001 else f"${price_usd:.8f}"
        embed.add_field(name="💰 Price USD", value=price_str, inline=True)

        # Add 24h change
        price_change = pair.get('priceChange', {}).get('h24', 0)
        if price_change:
            change_emoji = "📈" if float(price_change) > 0 else "📉"
            embed.add_field(
                name="24h Change",
                value=f"{change_emoji} {price_change}%",
                inline=True
            )

        # Add liquidity
        liquidity = float(pair.get('liquidity', {}).get('usd', 0))
        embed.add_field(name="💧 Liquidity", value=f"${liquidity:,.2f}", inline=False)

        # Add volume
        volume = float(pair.get('volume', {}).get('h24', 0))
        embed.add_field(name="📊 24h Volume", value=f"${volume:,.2f}", inline=True)

        # Add age if available
        if pair.get('pairCreatedAt'):
            created_at = datetime.fromtimestamp(int(pair['pairCreatedAt'])/1000)
            days_old = (datetime.utcnow() - created_at).days
            embed.add_field(name="📅 Age", value=f"{days_old} days", inline=True)

        # Add contract address
        if contract:
            embed.add_field(name=f"📝 Contract ({chain.upper()})", value=f"`{contract}`", inline=False)

        # Add trading links based on chain
        links = []
        if chain in ['eth', 'ethereum']:
            links.extend([
                f"[🔍 DEXScreener](https://dexscreener.com/ethereum/{contract})",
                f"[📊 Pump.fun](https://pump.fun/token/{contract})",
                f"[🐂 BullX](https://bullx.io/token/{contract})",
                f"[🤖 BonkBot](https://t.me/BonkBot)",
                f"[📱 Photon](https://photon.rs/token/{contract})",
                f"[🔄 Jupiter](https://jup.ag/swap/SOL-{contract})"
            ])
        elif chain == 'solana':
            links.extend([
                f"[🔍 DEXScreener](https://dexscreener.com/solana/{contract})",
                f"[👁️ Birdeye](https://birdeye.so/token/{contract})",
                f"[🐂 BullX](https://bullx.io/token/{contract})",
                f"[🤖 BonkBot](https://t.me/BonkBot)",
                f"[📱 Photon](https://photon.rs/token/{contract})",
                f"[🔄 Jupiter](https://jup.ag/swap/SOL-{contract})"
            ])
        elif chain == 'bsc':
            links.extend([
                f"[🔍 DEXScreener](https://dexscreener.com/bsc/{contract})",
                f"[💩 PooCoin](https://poocoin.app/tokens/{contract})",
                f"[🐂 BullX](https://bullx.io/token/{contract})",
                f"[🤖 BonkBot](https://t.me/BonkBot)",
                f"[📱 Photon](https://photon.rs/token/{contract})",
                f"[🔄 Jupiter](https://jup.ag/swap/SOL-{contract})"
            ])

        if links:
            embed.add_field(name="🔗 Links", value=" | ".join(links), inline=False)

        # Add footer
        embed.set_footer(text=f"Data: DEXScreener | Chain: {chain.upper()}")
        
        return embed
        
    except requests.exceptions.RequestException as e:
        return f"Network error while fetching token information. Please try again."
    except Exception as e:
        return f"Error fetching token information: {str(e)}"

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Check if message starts with $ and has content after it
    if message.content.startswith('$'):
        query = message.content[1:].strip()  # Remove $ and any whitespace
        if query:
            async with message.channel.typing():
                response = get_token_info(query)
                if isinstance(response, str):
                    await message.channel.send(response)
                else:
                    await message.channel.send(embed=response)
        else:
            await message.channel.send("Please provide a token name or contract address. Example: `$pepe` or `$0x...`")

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="memecoin prices | $symbol"))

# Run the bot
bot.run(DISCORD_TOKEN) 