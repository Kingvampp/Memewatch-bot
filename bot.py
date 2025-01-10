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

        # Search for token info
        search_url = f"https://api.coingecko.com/api/v3/search?query={query}"
        search_response = requests.get(search_url, headers=headers)
        
        if search_response.status_code == 429:
            return "Rate limit reached. Please try again in a minute."
        
        search_data = search_response.json()
        
        if not search_data.get('coins'):
            return f"Token '{query}' not found on CoinGecko."
            
        coin = search_data['coins'][0]
        coin_id = coin['id']
        
        # Get detailed token info
        token_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&market_data=true&community_data=true&developer_data=false&sparkline=false"
        response = requests.get(token_url, headers=headers)
        
        if response.status_code == 429:
            return "Rate limit reached. Please try again in a minute."
            
        data = response.json()
        
        # Create embed with token color if available
        color = discord.Color.blue()
        if data.get('image', {}).get('small'):
            embed = discord.Embed(
                title=f"{data['name']} ({data['symbol'].upper()})",
                color=color,
                timestamp=datetime.utcnow(),
                url=data.get('links', {}).get('homepage', [''])[0]  # Add homepage link to title
            )
            embed.set_thumbnail(url=data['image']['small'])
        
        # Price and market info section
        market_data = data.get('market_data', {})
        current_price = market_data.get('current_price', {}).get('usd')
        market_cap = market_data.get('market_cap', {}).get('usd')
        volume = market_data.get('total_volume', {}).get('usd')
        ath = market_data.get('ath', {}).get('usd')
        ath_date = market_data.get('ath_date', {}).get('usd')
        price_change_24h = market_data.get('price_change_percentage_24h')
        
        # Price formatting
        if current_price:
            if current_price < 0.000001:
                price_str = f"${current_price:.12f}"
            elif current_price < 0.01:
                price_str = f"${current_price:.10f}"
            else:
                price_str = f"${current_price:.4f}"
            embed.add_field(name="💰 Price USD", value=price_str, inline=True)
            
            if price_change_24h:
                change_emoji = "📈" if price_change_24h > 0 else "📉"
                embed.add_field(
                    name="24h Change", 
                    value=f"{change_emoji} {price_change_24h:.2f}%", 
                    inline=True
                )
        
        if market_cap:
            embed.add_field(name="📊 Market Cap", value=f"${market_cap:,.2f}", inline=False)
        
        if volume:
            embed.add_field(name="📈 24h Volume", value=f"${volume:,.2f}", inline=True)
        
        # ATH with date
        if ath:
            if ath < 0.01:
                ath_str = f"${ath:.10f}"
            else:
                ath_str = f"${ath:.4f}"
            
            if ath_date:
                ath_datetime = datetime.strptime(ath_date, "%Y-%m-%dT%H:%M:%S.%fZ")
                days_since_ath = (datetime.utcnow() - ath_datetime).days
                ath_str += f"\n({days_since_ath} days ago)"
            
            embed.add_field(name="🏆 All Time High", value=ath_str, inline=True)
        
        # Add blockchain info
        platforms = data.get('platforms', {})
        if platforms:
            native_chain = None
            if 'solana' in platforms and coin['symbol'].lower() in ['bonk', 'rlb', 'hnt']:
                native_chain = 'solana'
            elif 'ethereum' in platforms and coin['symbol'].lower() in ['pepe', 'wojak']:
                native_chain = 'ethereum'
            elif 'binance-smart-chain' in platforms and coin['symbol'].lower() in ['cake', 'bsc']:
                native_chain = 'binance-smart-chain'
            
            if native_chain and platforms.get(native_chain):
                platform_text = f"`{platforms[native_chain]}`"
                embed.add_field(name=f"📝 {native_chain.title()} Contract", value=platform_text, inline=False)
            else:
                platform_text = "\n".join([f"{k.title()}: `{v}`" for k, v in platforms.items() if v])
                if platform_text:
                    if len(platform_text) > 1024:
                        platform_text = platform_text[:1021] + "..."
                    embed.add_field(name="📝 Contract Addresses", value=platform_text, inline=False)
        
        # Add social links
        social_links = []
        if data.get('links', {}).get('twitter_screen_name'):
            twitter_handle = data['links']['twitter_screen_name']
            social_links.append(f"[𝕏 Twitter](https://twitter.com/{twitter_handle})")
        
        if data.get('links', {}).get('telegram_channel_identifier'):
            telegram = data['links']['telegram_channel_identifier']
            social_links.append(f"[📱 Telegram](https://t.me/{telegram})")
        
        if social_links:
            embed.add_field(name="🌐 Social", value=" | ".join(social_links), inline=False)
        
        # Add trading links
        links = []
        if 'ethereum' in platforms:
            contract = platforms['ethereum']
            links.extend([
                f"[🔍 DEXScreener](https://dexscreener.com/ethereum/{contract})",
                f"[📊 Pump.fun](https://pump.fun/token/{contract})",
                f"[🐂 BullX](https://bullx.io/token/{contract})"
            ])
        elif 'solana' in platforms:
            contract = platforms['solana']
            links.extend([
                f"[🔍 DEXScreener](https://dexscreener.com/solana/{contract})",
                f"[👁️ Birdeye](https://birdeye.so/token/{contract})",
                f"[🐂 BullX](https://bullx.io/token/{contract})"
            ])
        elif 'binance-smart-chain' in platforms:
            contract = platforms['binance-smart-chain']
            links.extend([
                f"[🔍 DEXScreener](https://dexscreener.com/bsc/{contract})",
                f"[💩 PooCoin](https://poocoin.app/tokens/{contract})",
                f"[🐂 BullX](https://bullx.io/token/{contract})"
            ])
        
        if links:
            embed.add_field(name="📈 Trading Links", value=" | ".join(links), inline=False)
        
        # Add footer
        embed.set_footer(text="Data: CoinGecko | Prices update every minute", icon_url="https://static.coingecko.com/s/thumbnail-007177f3eca19695592f0b8b0eabbdae282b54154e1be912285c9034ea6cbaf2.png")
        
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
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="crypto prices | $symbol"))

# Run the bot
bot.run(DISCORD_TOKEN) 