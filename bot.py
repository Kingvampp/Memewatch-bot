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
bot = commands.Bot(command_prefix='$', intents=intents)

def create_price_chart(prices, created_at):
    try:
        # Calculate time intervals based on token age
        now = datetime.utcnow()
        token_age = now - created_at
        
        # Filter and sample data points based on age
        if token_age < timedelta(hours=1):
            # Under 1 hour: 1-minute intervals
            interval = 60  # 1 minute in seconds
            title_text = "1 Minute Chart"
        elif token_age < timedelta(hours=5):
            # 1-5 hours: 5-minute intervals
            interval = 300  # 5 minutes in seconds
            title_text = "5 Minute Chart"
        elif token_age < timedelta(hours=24):
            # 5-24 hours: 15-minute intervals
            interval = 900  # 15 minutes in seconds
            title_text = "15 Minute Chart"
        else:
            # Over 24 hours: 1-hour intervals
            interval = 3600  # 1 hour in seconds
            title_text = "1 Hour Chart"

        # Process price data
        times = []
        price_values = []
        last_timestamp = 0
        
        for price in reversed(prices):  # Newest first
            timestamp = price['timestamp'] // 1000  # Convert to seconds
            if timestamp - last_timestamp >= interval:
                times.append(datetime.fromtimestamp(timestamp).strftime('%H:%M'))
                price_values.append(float(price['price']))
                last_timestamp = timestamp

        # Determine if price is up or down
        line_color = 'rgb(0,255,0)' if price_values[-1] >= price_values[0] else 'rgb(255,0,0)'

        # Create QuickChart configuration
        chart_config = {
            "type": "line",
            "data": {
                "labels": times[::-1],
                "datasets": [{
                    "data": price_values[::-1],
                    "fill": False,
                    "borderColor": line_color,
                    "tension": 0.1,
                    "borderWidth": 2,
                    "pointRadius": 0
                }]
            },
            "options": {
                "title": {
                    "display": True,
                    "text": title_text,
                    "fontColor": "white",
                    "fontSize": 16
                },
                "legend": {
                    "display": False
                },
                "scales": {
                    "yAxes": [{
                        "ticks": {
                            "fontColor": "white",
                            "maxTicksLimit": 8,
                            "callback": "function(value) { return value.toFixed(8); }"
                        },
                        "gridLines": {
                            "color": "rgba(100,100,100,0.2)",
                            "zeroLineColor": "rgba(100,100,100,0.2)"
                        }
                    }],
                    "xAxes": [{
                        "ticks": {
                            "fontColor": "white",
                            "maxTicksLimit": 8
                        },
                        "gridLines": {
                            "color": "rgba(100,100,100,0.2)",
                            "zeroLineColor": "rgba(100,100,100,0.2)"
                        }
                    }]
                },
                "plugins": {
                    "backgroundImageUrl": "https://quickchart.io/images/dark-background.png"
                }
            }
        }

        # Convert to URL-safe JSON
        chart_json = json.dumps(chart_config)
        chart_json_b64 = base64.b64encode(chart_json.encode()).decode()
        
        # Return the QuickChart URL
        return f"https://quickchart.io/chart?c={chart_json_b64}&backgroundColor=rgb(47,49,54)&width=800&height=400"
        
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
                embed.set_image(url=chart_url)

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

    # Check if it's a contract address or starts with $
    if is_contract_address(content) or content.startswith('$'):
        query = content[1:] if content.startswith('$') else content
        if query:
            async with message.channel.typing():
                response, _ = get_token_info(query)
                if isinstance(response, str):
                    await message.channel.send(response)
                else:
                    await message.channel.send(embed=response)
        else:
            await message.channel.send("Please provide a token name or contract address. Example: `$pepe` or `0x...`")

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="memecoin prices | $symbol"))

# Run the bot
bot.run(DISCORD_TOKEN) 