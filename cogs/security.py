import discord
from discord.ext import commands
import aiohttp
import json
import logging
import re

class SecurityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.logger = logging.getLogger('security')
        
    async def check_honeypot(self, contract_address, chain="ethereum"):
        """Check if a contract is a potential honeypot"""
        try:
            # Using GoPlus API for honeypot detection
            async with self.session.get(
                f"https://api.gopluslabs.io/api/v1/token_security/{chain}/{contract_address}"
            ) as response:
                data = await response.json()
                return data.get('result', {})
        except Exception as e:
            self.logger.error(f"Honeypot check failed: {e}")
            return None

    async def verify_liquidity_lock(self, contract_address, chain="ethereum"):
        """Verify if the token's liquidity is locked"""
        try:
            # Check liquidity locks on common platforms
            async with self.session.get(
                f"https://api.gopluslabs.io/api/v1/token_security/{chain}/{contract_address}"
            ) as response:
                data = await response.json()
                security_info = data.get('result', {})
                
                # Check for locked liquidity info
                locked_info = {
                    'is_locked': security_info.get('lp_holders', [{}])[0].get('is_locked', 0) == 1,
                    'lock_time': security_info.get('lp_holders', [{}])[0].get('lock_time', 0),
                    'locked_percent': security_info.get('lp_holders', [{}])[0].get('percent', 0)
                }
                return locked_info
        except Exception as e:
            self.logger.error(f"Liquidity lock check failed: {e}")
            return None

    async def assess_rug_pull_risk(self, contract_address, chain="ethereum"):
        """Assess the risk of a rug pull based on various factors"""
        try:
            risk_factors = {
                'high_risk': [],
                'medium_risk': [],
                'low_risk': []
            }
            
            # Get security info from GoPlus
            async with self.session.get(
                f"https://api.gopluslabs.io/api/v1/token_security/{chain}/{contract_address}"
            ) as response:
                data = await response.json()
                security_info = data.get('result', {})
                
                # Check ownership
                if security_info.get('owner_address') == contract_address:
                    risk_factors['low_risk'].append("Contract ownership renounced")
                else:
                    risk_factors['medium_risk'].append("Contract has an owner")
                
                # Check mint function
                if security_info.get('mint_function', 0) == 1:
                    risk_factors['high_risk'].append("Contract can mint new tokens")
                
                # Check proxy status
                if security_info.get('is_proxy', 0) == 1:
                    risk_factors['high_risk'].append("Contract is a proxy (can be modified)")
                
                # Check trading cooldown
                if security_info.get('trading_cooldown', 0) == 1:
                    risk_factors['medium_risk'].append("Trading cooldown enabled")
                
                return risk_factors
        except Exception as e:
            self.logger.error(f"Rug pull risk assessment failed: {e}")
            return None

    @commands.command(name='audit')
    async def audit_contract(self, ctx, contract_address: str):
        """Perform a comprehensive security audit of a token contract"""
        if not re.match(r'^0x[a-fA-F0-9]{40}$', contract_address):
            await ctx.send("❌ Invalid contract address format")
            return

        async with ctx.typing():
            embed = discord.Embed(
                title="🔒 Security Audit Report",
                description=f"Contract: `{contract_address}`",
                color=discord.Color.blue()
            )

            # Check for honeypot
            honeypot_info = await self.check_honeypot(contract_address)
            if honeypot_info:
                is_honeypot = honeypot_info.get('is_honeypot', 0) == 1
                embed.add_field(
                    name="🍯 Honeypot Check",
                    value="⚠️ High Risk: Potential Honeypot" if is_honeypot else "✅ No honeypot detected",
                    inline=False
                )

            # Verify liquidity lock
            lock_info = await self.verify_liquidity_lock(contract_address)
            if lock_info:
                lock_status = "✅ Locked" if lock_info['is_locked'] else "⚠️ Not locked"
                lock_details = f"{lock_status}\nLocked: {lock_info['locked_percent']}%"
                if lock_info['lock_time'] > 0:
                    lock_details += f"\nLock Duration: {lock_info['lock_time']} days"
                embed.add_field(
                    name="🔒 Liquidity Lock",
                    value=lock_details,
                    inline=False
                )

            # Assess rug pull risk
            risk_assessment = await self.assess_rug_pull_risk(contract_address)
            if risk_assessment:
                risk_details = ""
                if risk_assessment['high_risk']:
                    risk_details += "⚠️ **High Risk Factors**:\n• " + "\n• ".join(risk_assessment['high_risk']) + "\n"
                if risk_assessment['medium_risk']:
                    risk_details += "⚡ **Medium Risk Factors**:\n• " + "\n• ".join(risk_assessment['medium_risk']) + "\n"
                if risk_assessment['low_risk']:
                    risk_details += "✅ **Low Risk Factors**:\n• " + "\n• ".join(risk_assessment['low_risk'])
                
                embed.add_field(
                    name="⚠️ Rug Pull Risk Assessment",
                    value=risk_details or "No significant risks detected",
                    inline=False
                )

            embed.set_footer(text="Security data provided by GoPlus Security API")
            await ctx.send(embed=embed)

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        self.bot.loop.create_task(self.session.close())

async def setup(bot):
    await bot.add_cog(SecurityCog(bot))