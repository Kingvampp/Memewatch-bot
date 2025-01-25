import logging
import discord
from discord.ext import commands
import traceback
import aiohttp
import base64
import io
import os
from anthropic import Anthropic
from PIL import Image

logger = logging.getLogger('bot')

class AnalyzerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('bot')
        # Initialize Anthropic client without proxies
        if os.getenv('CLAUDE_API_KEY'):
            self.claude = Anthropic(
                api_key=os.getenv('CLAUDE_API_KEY')
            )
        else:
            self.claude = None
            self.logger.warning("CLAUDE_API_KEY not set. Analyzer functionality will be limited.")
        
    @commands.command(name='quant')
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def analyze(self, ctx):
        """Analyze a chart image using Claude Vision API"""
        try:
            if not ctx.message.attachments:
                await ctx.send("❌ Please attach a chart image to analyze.")
                return
                
            attachment = ctx.message.attachments[0]
            if not attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                await ctx.send("❌ Please provide a PNG or JPG image.")
                return
                
            async with ctx.typing():
                # Download image
                async with aiohttp.ClientSession() as session:
                    async with session.get(attachment.url) as resp:
                        if resp.status != 200:
                            await ctx.send("❌ Failed to download image.")
                            return
                        image_data = await resp.read()
                
                # Process image
                image = Image.open(io.BytesIO(image_data))
                
                # Resize if too large
                max_size = (800, 800)
                if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Convert to bytes
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format=image.format)
                img_byte_arr = img_byte_arr.getvalue()
                
                # Get analysis from Claude
                if self.claude:
                    response = await self.claude.messages.create(
                        model="claude-3-opus-20240229",
                        max_tokens=1000,
                        messages=[{
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Analyze this price chart and provide technical analysis. Focus on key support/resistance levels, trend direction, and potential entry/exit points. Be concise."
                                },
                                {
                                    "type": "image",
                                    "image": img_byte_arr
                                }
                            ]
                        }]
                    )
                    
                    analysis = response.content[0].text
                    
                    # Create embed
                    embed = discord.Embed(
                        title="Chart Analysis",
                        description=analysis,
                        color=discord.Color.blue()
                    )
                    embed.set_thumbnail(url=attachment.url)
                    
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ Claude API key not configured. Analysis cannot be performed.")
                    
        except Exception as e:
            self.logger.error(f"Analysis error: {str(e)}")
            self.logger.error(traceback.format_exc())
            await ctx.send("❌ An error occurred during analysis. Please try again later.")

    @commands.command(name='ping')
    async def ping(self, ctx):
        """Check bot latency"""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Latency: {latency}ms")

async def setup(bot):
    await bot.add_cog(AnalyzerCog(bot))
