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
        self.claude_client = anthropic.AsyncAnthropic(api_key=os.getenv('CLAUDE_API_KEY'))
        self.max_image_size = 20 * 1024 * 1024  # 20MB limit
        
    async def analyze_chart_with_claude(self, image_data):
        """Analyze chart using Claude"""
        try:
            # Convert image to JPEG format
            image = Image.open(io.BytesIO(image_data))
            
            # Check image dimensions
            if image.size[0] > 4096 or image.size[1] > 4096:
                raise ValueError("Image dimensions too large (max 4096x4096)")
                
            if image.mode != 'RGB':
                image = image.convert('RGB')
                
            # Save as JPEG in memory with compression
            jpeg_buffer = io.BytesIO()
            image.save(jpeg_buffer, format='JPEG', quality=85, optimize=True)
            jpeg_buffer.seek(0)
            
            # Check if compressed image is within size limit
            compressed_size = jpeg_buffer.getbuffer().nbytes
            if compressed_size > self.max_image_size:
                raise ValueError(f"Image too large ({compressed_size / 1024 / 1024:.1f}MB). Maximum size is 20MB")
            
            # Convert JPEG data to base64
            image_base64 = base64.b64encode(jpeg_buffer.getvalue()).decode('utf-8')
            
            # Prepare the message for Claude
            system_prompt = "You are a cryptocurrency trading expert analyzing charts. Provide detailed technical analysis."
            user_message = """Please analyze this cryptocurrency chart and provide detailed insights including:
1. Current price action and trend
2. Key support and resistance levels
3. Notable chart patterns
4. Technical indicators analysis (if any indicators are present in the chart, analyze what they're signaling)
5. Market sentiment
6. Potential trading opportunities
Please be specific with price levels and technical analysis. If you see any technical indicators (like RSI, MACD, Moving Averages, Bollinger Bands, etc.), explain what they're indicating about potential price movement."""

            try:
                # Call Claude API
                response = await self.claude_client.messages.create(
                    model="claude-3-opus-20240229",
                    max_tokens=1000,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_message
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_base64
                                }
                            }
                        ]
                    }]
                )
                
                return response.content[0].text
                
            except anthropic.APIError as api_error:
                logger.error(f"Claude API error: {str(api_error)}")
                if hasattr(api_error, 'status_code'):
                    logger.error(f"Status code: {api_error.status_code}")
                raise
                
        except ValueError as ve:
            logger.error(f"Validation error: {str(ve)}")
            raise
        except Exception as e:
            logger.error(f"Error in Claude analysis: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        finally:
            # Clean up resources
            if 'image' in locals():
                image.close()
            if 'jpeg_buffer' in locals():
                jpeg_buffer.close()
        
    @commands.command(name='analyze')
    async def analyze(self, ctx):
        """Analyze a chart image"""
        try:
            # Check if message has an attachment
            if not ctx.message.attachments:
                await ctx.send("❌ Please attach a chart image to analyze!")
                return
                
            attachment = ctx.message.attachments[0]
            
            # Check file size
            if attachment.size > self.max_image_size:
                await ctx.send(f"❌ Image too large ({attachment.size / 1024 / 1024:.1f}MB). Maximum size is 20MB!")
                return
                
            # Validate file type
            if not attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                await ctx.send("❌ Please provide a valid image file (PNG, JPG, GIF, or WEBP)!")
                return
                
            # Send acknowledgment
            processing_msg = await ctx.send("📊 Analyzing your chart... Please wait.")
            
            try:
                # Download the image
                image_data = await attachment.read()
                
                # Get analysis from Claude
                analysis = await self.analyze_chart_with_claude(image_data)
                
                # Create embed with analysis
                embed = discord.Embed(
                    title="Chart Analysis",
                    description=analysis,
                    color=discord.Color.blue()
                )
                
                # Add footer
                embed.set_footer(text="Analysis powered by Claude | Not financial advice")
                
                # Delete processing message and send analysis
                await processing_msg.delete()
                await ctx.send(embed=embed)
                
            except ValueError as ve:
                await processing_msg.edit(content=f"❌ {str(ve)}")
            except Exception as e:
                logger.error(f"Error analyzing chart: {str(e)}")
                logger.error(traceback.format_exc())
                await processing_msg.edit(content="❌ An error occurred while analyzing the chart. Please try again later.")
            
        except Exception as e:
            logger.error(f"Error in analyze command: {str(e)}")
            logger.error(traceback.format_exc())
            await ctx.send("❌ An error occurred while processing your request")
            
    @commands.command(name='ping')
    async def ping(self, ctx):
        """Check if the bot is responsive"""
        try:
            latency = round(self.bot.latency * 1000)
            await ctx.send(f'🏓 Pong! Latency: {latency}ms')
        except Exception as e:
            logger.error(f"Error in ping command: {str(e)}")
            await ctx.send("❌ An error occurred while checking latency")
            
    @commands.command(name='status')
    async def status(self, ctx):
        """Check the bot's status"""
        try:
            embed = discord.Embed(
                title="Bot Status",
                color=discord.Color.green() if self.bot.is_ready() else discord.Color.red()
            )
            
            # Add connection info
            ws_state = "Connected" if self.bot.ws and not self.bot.ws.closed else "Disconnected"
            embed.add_field(
                name="Connection",
                value=f"WebSocket: {ws_state}\nLatency: {round(self.bot.latency * 1000)}ms",
                inline=False
            )
            
            # Add guild info
            guild_info = []
            for guild in self.bot.guilds:
                permissions = guild.me.guild_permissions
                guild_info.append(f"• {guild.name}")
                guild_info.append(f"  - Status: {guild.me.status}")
                guild_info.append(f"  - Send Messages: {'✅' if permissions.send_messages else '❌'}")
                guild_info.append(f"  - Embed Links: {'✅' if permissions.embed_links else '❌'}")
                guild_info.append(f"  - Attach Files: {'✅' if permissions.attach_files else '❌'}")
            
            embed.add_field(
                name="Guilds",
                value="\n".join(guild_info) if guild_info else "Not in any guilds",
                inline=False
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in status command: {str(e)}")
            logger.error(traceback.format_exc())
            await ctx.send("❌ An error occurred while checking status")