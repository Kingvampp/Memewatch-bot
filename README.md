# MemeWatch Bot 🚀

A Discord bot that tracks memecoin prices and provides detailed token information with AI-powered chart analysis.

## Features

- 💰 Real-time token prices and market data
- 📊 Market cap and volume information
- 📈 Price change tracking with 24h changes
- 🤖 AI-powered chart analysis using Claude Vision
- 🏆 All-Time High tracking with dates
- 🔍 First scanner tracking for new tokens
- 🌐 Social media links (Twitter/X, Telegram)
- 📱 Trading platform links (DEXScreener, Birdeye)

## Commands

- `$scan <token_address>` - Scan a new token
- `$quant` - Analyze a chart image using AI
- `$ping` - Check bot latency
- `$help` - Show all available commands

## Setup

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables in `.env`:
```env
DISCORD_TOKEN=your_token_here
CLAUDE_API_KEY=your_claude_key_here
BIRDEYE_API_KEY=your_birdeye_key_here
SOLSCAN_API_KEY=your_solscan_key_here
```

4. Run the bot:
```bash
python bot.py
```

## Data Sources

- Birdeye API (Solana)
- Solscan API
- Claude Vision API

## Contributing

Feel free to open issues or submit pull requests!

## License

MIT License
