# Arts One Two Three Trading Bot - Production Deployment

Production-ready version of the automated trading bot for Binance and Bybit exchanges.

## Prerequisites

- Python 3.8 or higher
- pip package manager
- Binance and/or Bybit API keys with appropriate permissions

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and settings
   ```

## Environment Variables

Required environment variables:
```
# Webhook security
WEBHOOK_PASSPHRASE=your_secure_passphrase

# Database configuration
DATABASE_URL=sqlite:///trading_bot.db
# Or for production: DATABASE_URL=mysql+pymysql://user:password@localhost:3306/trading_bot

# Exchange configuration (at least one required)
ACC_A_EXCHANGE=binance
ACC_A_API_KEY=your_binance_api_key
ACC_A_API_SECRET=your_binance_api_secret
ACC_A_ENABLED=true

# Optional second account
ACC_B_EXCHANGE=bybit
ACC_B_API_KEY=your_bybit_api_key
ACC_B_API_SECRET=your_bybit_api_secret
ACC_B_ENABLED=false

# Testnet/Live configuration
USE_TESTNET=true  # Set to false for live trading
```

## Starting the Bot

```bash
python run.py
```

The bot will start on `http://127.0.0.1:8003` by default.

## Webhook Endpoint

The bot listens for TradingView webhooks at:
`POST /webhook`

## Dashboard Access

Access the dashboard at:
`http://127.0.0.1:8003/dashboard`

## Supported Strategies

- Arts One Two Three Strategy
- Mode A (Take Profits provided at entry)
- Mode B (Separate TP/SL events)

## Supported Events

- LONG_ENTRY, SHORT_ENTRY
- TP1_HIT, TP2_HIT, TP3_HIT, TP4_HIT, TP5_HIT
- STOP (Stop Loss)
- CLOSE (Close entire position)
- TIME_GUARD, MAX_BARS, SWING_TP, DYN_TP

## Production Security Recommendations

1. Use strong, unique webhook passphrases
2. Use SSL/TLS for webhook endpoints
3. Implement rate limiting
4. Use strong API keys with minimal required permissions
5. Regularly backup database files
6. Monitor logs regularly

## API Endpoints

- `/webhook` - Receive TradingView signals
- `/status` - Get current position status
- `/dashboard` - Web-based dashboard
- `/api/positions` - Get positions data
- `/api/events` - Get recent events
- `/api/accounts` - Get account balances
- `/api/symbols` - Get available symbols
- `/api/sync_positions` - Sync positions with exchange

## Monitoring

Monitor the bot using the dashboard or by querying the `/status` endpoint regularly.

## Troubleshooting

- Check `trading_bot.log` for detailed logs
- Verify API keys have correct permissions
- Ensure webhook passphrase matches
- Check network connectivity to exchanges