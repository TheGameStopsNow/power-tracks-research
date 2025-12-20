# Deployment Guide

## Quick Deploy to Railway (Recommended - Free Tier)

1. **Sign up**: [railway.app](https://railway.app) (free tier available)

2. **Create Project**:
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Connect your GitHub account
   - Select `power-tracks-research` repo
   - Set root directory: `services/steamroller_tracker`

3. **Configure**:
   - Go to Variables tab
   - Add: `POLYGON_API_KEY` = your Polygon API key
   - Service will auto-detect Python and install dependencies

4. **Deploy**:
   - Railway auto-deploys on git push
   - Or click "Deploy Now"

5. **Monitor**:
   - View logs in Railway dashboard
   - Logs saved to `logs/` directory (persistent storage)

## Quick Deploy to Render

1. **Sign up**: [render.com](https://render.com) (free tier available)

2. **Create Worker Service**:
   - New → Background Worker
   - Connect GitHub repo
   - Settings:
     - **Name**: `steamroller-tracker`
     - **Root Directory**: `services/steamroller_tracker`
     - **Environment**: Python 3
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `python steamroller_tracker.py`
     - **Environment Variables**: Add `POLYGON_API_KEY`

3. **Deploy**:
   - Click "Create Worker"
   - Service starts automatically

## Local Testing

```bash
cd services/steamroller_tracker
export POLYGON_API_KEY=your_key_here
python steamroller_tracker.py
```

## Monitoring

- **Live logs**: Check service console output
- **Daily logs**: `logs/steamroller_YYYY-MM-DD.log`
- **Daily reports**: `logs/report_YYYY-MM-DD.json`

## Troubleshooting

- **Connection issues**: Check API key is valid
- **No trades**: Verify market is open (9:30 AM - 4:00 PM ET)
- **Missing logs**: Check service has write permissions to `logs/` directory


