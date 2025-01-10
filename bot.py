import os
import discord
from discord.ext import commands
import requests
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import time
import re
import base64

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Initialize bot with command prefix '$'
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(
    command_prefix='$',
    intents=intents
)

def create_price_chart(prices, created_at):
    try:
        # Calculate time intervals based on token age
        now = datetime.utcnow()
        token_age = now - created_at
        
        # Filter and sample data points based on age
        if token_age < timedelta(hours=1):
            interval = 60  # 1 minute
            title = "1m"
        elif token_age < timedelta(hours=5):
            interval = 300  # 5 minutes
            title = "5m"
        elif token_age < timedelta(hours=24):
            interval = 900  # 15 minutes
            title = "15m"
        else:
            interval = 3600  # 1 hour
            title = "1h"

        # Process price data (limit to 20 points max)
        times = []
        prices_list = []
        last_timestamp = 0
        count = 0
        
        for price in reversed(prices):  # Newest first
            if count >= 20:  # Limit to 20 data points
                break
            timestamp = price['timestamp'] // 1000
            if timestamp - last_timestamp >= interval:
                times.append(datetime.fromtimestamp(timestamp).strftime('%H:%M'))
                prices_list.append(float(price['price']))
                last_timestamp = timestamp
                count += 1

        # Determine color based on price direction
        color = '00ff00' if prices_list[-1] >= prices_list[0] else 'ff0000'

        # Format data for chart
        data_points = ','.join(str(p) for p in prices_list[::-1][-20:])
        labels = ','.join(f'"{t}"' for t in times[::-1][-20:])
        
        # Create direct ChartJS URL
        return f"https://image-charts.com/chart?cht=lc&chs=400x300&chd=t:{data_points}&chl={labels}&chco={color}&chf=bg,s,32353b&chdl=Price&chtt={title}"
        
    except Exception as e:
        print(f"Error creating chart: {str(e)}")
        return None

def is_contract_address(text):
    # ETH address pattern
    eth_pattern = r'^0x[a-fA-F0-9]{40}$'
    # SOL address pattern (base58 encoded, 32-44 chars)
    sol_pattern = r'^[1-9A-HJ-NP-Za-km-z]{32,44}$'
    
    return bool(re.match(eth_pattern, text)) or bool(re.match(sol_pattern, text))

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
            return f"Token '{query}' not found on DEXScreener.", None

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

        # Get creation time and add age
        created_at = None
        if pair.get('pairCreatedAt'):
            created_at = datetime.fromtimestamp(int(pair['pairCreatedAt'])/1000)
            days_old = (datetime.utcnow() - created_at).days
            hours_old = int((datetime.utcnow() - created_at).total_seconds() / 3600)
            
            if days_old > 0:
                age_str = f"{days_old} days"
            else:
                age_str = f"{hours_old} hours"
            embed.add_field(name="📅 Age", value=age_str, inline=True)

        # Add contract address
        if contract:
            embed.add_field(name=f"📝 Contract ({chain.upper()})", value=f"`{contract}`", inline=False)

        # Add trading links based on chain
        links = []
        if chain in ['eth', 'ethereum']:
            links.extend([
                f"[🔍 DEXScreener](https://dexscreener.com/ethereum/{contract})",
                f"[🐂 BullX](https://bullx.io/token/{contract})",
                f"[📱 Photon](https://photon.rs/token/{contract})"
            ])
        elif chain == 'solana':
            links.extend([
                f"[🔍 DEXScreener](https://dexscreener.com/solana/{contract})",
                f"[👁️ Birdeye](https://birdeye.so/token/{contract})",
                f"[📊 Pump.fun](https://pump.fun/token/{contract})",
                f"[🐂 BullX](https://bullx.io/token/{contract})",
                f"[📱 Photon](https://photon.rs/token/{contract})",
                f"[🤖 BonkBot](https://t.me/BonkBot)",
                f"[🔄 Jupiter](https://jup.ag/swap/SOL-{contract})"
            ])

        if links:
            embed.add_field(name="🔗 Links", value=" | ".join(links), inline=False)

        # Add price chart if creation time is available
        if created_at and pair.get('priceHistory'):
            chart_url = create_price_chart(pair['priceHistory'], created_at)
            if chart_url:
                print(f"Chart URL: {chart_url}")  # Debug print
                embed.set_image(url=chart_url)
            else:
                print("Failed to create chart URL")  # Debug print

        # Add footer
        embed.set_footer(text=f"Data: DEXScreener | Chain: {chain.upper()}")
        
        return embed, None
        
    except requests.exceptions.RequestException as e:
        return f"Network error while fetching token information. Please try again.", None
    except Exception as e:
        return f"Error fetching token information: {str(e)}", None

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Get the message content
    content = message.content.strip()

    # Test command for image sending
    if content.lower() == "$testimage":
        try:
            test_embed = discord.Embed(title="Image Test", color=discord.Color.blue())
            # Using a known working Discord image URL
            test_embed.set_image(url="https://discord.com/assets/7c8f476123d28d103efe381543274c25.png")
            await message.channel.send("Testing image capability...")
            await message.channel.send(embed=test_embed)
            return
        except Exception as e:
            await message.channel.send(f"Error sending test image: {str(e)}")
            return

    # Only proceed with token lookup if it's not the test command
    if content.startswith('$') and content.lower() != "$testimage":
        query = content[1:].strip()
        if query:
            async with message.channel.typing():
                response, _ = get_token_info(query)
                if isinstance(response, str):
                    await message.channel.send(response)
                else:
                    await message.channel.send(embed=response)
        else:
            await message.channel.send("Please provide a token name or contract address. Example: `$pepe` or `0x...`")
    elif is_contract_address(content):
        async with message.channel.typing():
            response, _ = get_token_info(content)
            if isinstance(response, str):
                await message.channel.send(response)
            else:
                await message.channel.send(embed=response)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="memecoin prices | $symbol"))

# Run the bot
bot.run(DISCORD_TOKEN) 