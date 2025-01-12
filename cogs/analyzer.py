import logging
import discord
from discord.ext import commands
import traceback
import aiohttp
import base64
import io
import os
import anthropic
from PIL import Image

logger = logging.getLogger('bot')

class AnalyzerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('bot')
        
    @commands.command(name='quant')
    async def analyze(self, ctx):
        """Analyze a chart image using Claude Vision API"""
        try:
            # Check if an image is attached
            if not ctx.message.attachments:
                await ctx.send("Please attach a chart image to analyze.")
                return
                
            attachment = ctx.message.attachments[0]
            
            # Validate file type
            if not attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                await ctx.send("Please provide a PNG or JPG image.")
                return
                
            # Check file size (8MB limit)
            if attachment.size > 8 * 1024 * 1024:
                await ctx.send("Image size must be under 8MB.")
                return
                
            async with ctx.typing():
                # Download the image
                image_data = await attachment.read()
                
                # Convert to base64
                image_b64 = base64.b64encode(image_data).decode('utf-8')
                
                # Send to Claude API
                headers = {
                    'x-api-key': CLAUDE_API_KEY,
                    'Content-Type': 'application/json'
                }
                
                data = {
                    'model': 'claude-3-opus-20240229',
                    'messages': [{
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': 'Please analyze this cryptocurrency chart and provide insights about the price action, key levels, patterns, and potential next moves. Focus on technical analysis.'
                            },
                            {
                                'type': 'image',
                                'source': {
                                    'type': 'base64',
                                    'media_type': 'image/jpeg',
                                    'data': image_b64
                                }
                            }
                        ]
                    }]
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post('https://api.anthropic.com/v1/messages', json=data, headers=headers) as response:
                        if response.status == 200:
                            result = await response.json()
                            analysis = result['content'][0]['text']
                            
                            # Create embed
                            embed = discord.Embed(
                                title="Chart Analysis",
                                description=analysis,
                                color=discord.Color.blue()
                            )
                            
                            # Add image thumbnail
                            embed.set_thumbnail(url=attachment.url)
                            
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send("Error analyzing chart. Please try again later.")
                            
        except Exception as e:
            self.logger.error(f"Error in analyze command: {str(e)}")
            self.logger.error(traceback.format_exc())
            await ctx.send("An error occurred while analyzing the chart. Please try again later.")

    @commands.command(name='ping')
    async def ping(self, ctx):
        """Check bot latency"""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Latency: {latency}ms")

async def setup(bot):
    await bot.add_cog(AnalyzerCog(bot))