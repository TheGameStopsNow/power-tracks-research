# Steamroller Strategy Tracker

Real-time monitoring service for the Steamroller strategy using Polygon WebSocket API.

## Features

- **Real-time tracking**: Monitors GME EDGX trades via Polygon WebSocket
- **Seed detection**: Counts 0xDF seed signals (8-bit pattern from price LSBs)
- **Signal alerts**: Logs when threshold (>60 seeds) is reached
- **Daily reports**: Saves JSON reports at end of day
- **Auto-restart**: Resets each trading day automatically
- **Free hosting**: Deployable to Railway/Render/Fly.io

## Setup

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set API key:
```bash
export POLYGON_API_KEY=your_polygon_api_key_here
```

3. Run:
```bash
python steamroller_tracker.py
```

### Deploy to Railway (Free Tier)

1. Create account at [railway.app](https://railway.app)
2. Create new project → "Deploy from GitHub repo"
3. Connect your repo
4. Add environment variable: `POLYGON_API_KEY`
5. Set start command: `python steamroller_tracker.py`
6. Deploy!

### Deploy to Render (Free Tier)

1. Create account at [render.com](https://render.com)
2. New → Web Service
3. Connect GitHub repo
4. Settings:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python steamroller_tracker.py`
   - **Environment**: Add `POLYGON_API_KEY` variable
5. Deploy!

## Output

- **Live logs**: Console output with real-time tracking
- **Daily logs**: `logs/steamroller_YYYY-MM-DD.log`
- **Daily reports**: `logs/report_YYYY-MM-DD.json`

## Report Format

```json
{
  "date": "2025-01-15",
  "seeds_count": 65,
  "daily_return": 0.0234,
  "trades_tracked": 12345,
  "signal": {
    "status": "TRADE_SIGNAL",
    "action": "BUY_OPEN_T+1"
  },
  "open_price": 24.50,
  "close_price": 25.07
}
```

## Strategy Rules

- **Trigger**: EDGX seeds (0xDF) > 60
- **Filter**: Daily return > -5% (skip deep red days)
- **Action**: Buy open T+1, sell close T+1

## Notes

- Service runs continuously, auto-restarts each trading day
- Logs persist in `logs/` directory
- Free tier services may have resource limits; monitor usage

