import os
import discord
from discord.ext import commands
import requests
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import time
import matplotlib.pyplot as plt
import io
import matplotlib.dates as mdates

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Initialize bot with command prefix '$'
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='$', intents=intents)

def create_price_chart(pair_address, chain, created_at):
    try:
        # Get price history from DEXScreener
        url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair_address}"
        response = requests.get(url)
        data = response.json()
        
        if not data.get('pair'):
            return None
            
        # Calculate time intervals based on token age
        now = datetime.utcnow()
        token_age = now - created_at
        
        if token_age < timedelta(hours=1):
            # Under 1 hour: 1-minute intervals
            interval = timedelta(minutes=1)
            format_str = '%H:%M'
        elif token_age < timedelta(hours=24):
            # Under 24 hours: 30-minute intervals
            interval = timedelta(minutes=30)
            format_str = '%H:%M'
        else:
            # Over 24 hours: 1-hour intervals
            interval = timedelta(hours=1)
            format_str = '%m/%d %H:%M'

        # Create price chart
        plt.figure(figsize=(8, 4))
        plt.style.use('dark_background')
        
        # Get price data
        prices = data['pair'].get('priceHistory', [])
        if not prices:
            return None
            
        # Convert timestamps to datetime
        times = [datetime.fromtimestamp(p['timestamp']/1000) for p in prices]
        price_values = [float(p['price']) for p in prices]
        
        # Plot the line
        plt.plot(times, price_values, color='#00ff00', linewidth=2)
        
        # Format the plot
        plt.gca().spines['top'].set_visible(False)
        plt.gca().spines['right'].set_visible(False)
        plt.gca().spines['bottom'].set_color('#666666')
        plt.gca().spines['left'].set_color('#666666')
        
        # Format x-axis
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter(format_str))
        plt.xticks(rotation=45)
        
        # Format y-axis to use scientific notation for small numbers
        plt.gca().yaxis.set_major_formatter(plt.ScalarFormatter(useMathText=True))
        plt.ticklabel_format(style='sci', axis='y', scilimits=(0,0))
        
        # Adjust layout and grid
        plt.grid(True, alpha=0.2)
        plt.tight_layout()
        
        # Save to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf
    except Exception as e:
        print(f"Error creating chart: {str(e)}")
        return None

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
        pair_address = pair.get('pairAddress', '')

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
        if created_at and pair_address:
            chart_buf = create_price_chart(pair_address, chain, created_at)
            if chart_buf:
                chart_file = discord.File(chart_buf, filename="chart.png")
                embed.set_image(url="attachment://chart.png")
                return embed, chart_file

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

    # Check if message starts with $ and has content after it
    if message.content.startswith('$'):
        query = message.content[1:].strip()  # Remove $ and any whitespace
        if query:
            async with message.channel.typing():
                response, chart = get_token_info(query)
                if isinstance(response, str):
                    await message.channel.send(response)
                else:
                    if chart:
                        await message.channel.send(embed=response, file=chart)
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