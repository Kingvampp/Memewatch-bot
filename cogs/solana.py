import discord
from discord.ext import commands
import aiohttp
import logging
import json
from datetime import datetime, timedelta

class SolanaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.logger = logging.getLogger('solana')
        
    async def get_token_holders(self, contract_address):
        """Get top token holders information"""
        try:
            url = f"https://public-api.birdeye.so/public/token_holders?address={contract_address}"
            async with self.session.get(url) as response:
                data = await response.json()
                return data.get('data', {}).get('items', [])[:5]  # Top 5 holders
        except Exception as e:
            self.logger.error(f"Error fetching holders: {e}")
            return None

    async def get_recent_trades(self, contract_address):
        """Get recent trade activity"""
        try:
            url = f"https://public-api.birdeye.so/public/trade_history?address={contract_address}"
            async with self.session.get(url) as response:
                data = await response.json()
                return data.get('data', [])[:5]  # Last 5 trades
        except Exception as e:
            self.logger.error(f"Error fetching trades: {e}")
            return None

    @commands.command(name='holders')
    async def show_holders(self, ctx, contract_address: str):
        """Show top token holders"""
        async with ctx.typing():
            holders = await self.get_token_holders(contract_address)
            if not holders:
                await ctx.send("❌ Could not fetch holder information")
                return

            embed = discord.Embed(
                title="👥 Top Token Holders",
                description=f"Contract: `{contract_address}`",
                color=discord.Color.blue()
            )

            for holder in holders:
                amount = float(holder.get('amount', 0))
                percent = float(holder.get('percentage', 0))
                address = holder.get('owner', 'Unknown')
                embed.add_field(
                    name=f"🏦 {address[:8]}...{address[-4:]}",
                    value=f"Holdings: {amount:,.0f} ({percent:.2f}%)",
                    inline=False
                )

            await ctx.send(embed=embed)

    @commands.command(name='trades')
    async def show_trades(self, ctx, contract_address: str):
        """Show recent trades"""
        async with ctx.typing():
            trades = await self.get_recent_trades(contract_address)
            if not trades:
                await ctx.send("❌ Could not fetch trade information")
                return

            embed = discord.Embed(
                title="📊 Recent Trades",
                description=f"Contract: `{contract_address}`",
                color=discord.Color.blue()
            )

            for trade in trades:
                side = "🟢 Buy" if trade.get('side') == 'buy' else "🔴 Sell"
                price = float(trade.get('price', 0))
                amount = float(trade.get('amount', 0))
                value = price * amount
                time = datetime.fromtimestamp(trade.get('time', 0)/1000)
                time_ago = (datetime.utcnow() - time).total_seconds() / 60  # minutes

                embed.add_field(
                    name=f"{side} • {time_ago:.1f}m ago",
                    value=f"Price: ${price:.8f}\nAmount: {amount:,.0f}\nValue: ${value:,.2f}",
                    inline=False
                )

            await ctx.send(embed=embed)

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        self.bot.loop.create_task(self.session.close())

async def setup(bot):
    await bot.add_cog(SolanaCog(bot))