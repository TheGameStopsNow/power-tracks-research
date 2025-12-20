#!/usr/bin/env python3
"""
Steamroller Strategy Real-Time Tracker
=======================================
Monitors GME EDGX tick data via Polygon WebSocket for seed (0xDF) signals.
Logs daily activity and saves end-of-day reports.
"""

import asyncio
import json
import os
import websockets
from datetime import datetime, time
from pathlib import Path
import logging
from typing import Optional, List
from collections import deque

# Configuration
API_KEY = os.getenv('POLYGON_API_KEY')
if not API_KEY:
    raise ValueError("POLYGON_API_KEY environment variable required")

LOG_DIR = Path('logs')
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Trading hours (ET)
MARKET_OPEN = time(9, 30)  # 9:30 AM ET
MARKET_CLOSE = time(16, 0)  # 4:00 PM ET

# Strategy thresholds
SEED_THRESHOLD = 60
FILTER_MIN_RET = -0.05  # -5%

class SteamrollerTracker:
    def __init__(self):
        self.current_date = datetime.now().date()
        self.daily_seeds = 0
        self.daily_trades = []
        self.daily_prices = []
        self.session_start = None
        self.log_file = None
        # Buffer for 8 consecutive EDGX ticks to detect 0xDF
        self.edgx_buffer: deque = deque(maxlen=8)
        self.setup_logging()
        
    def setup_logging(self):
        """Setup daily log file"""
        date_str = self.current_date.strftime('%Y-%m-%d')
        log_path = LOG_DIR / f"steamroller_{date_str}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_path),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.log_file = log_path
        
    def is_market_hours(self) -> bool:
        """Check if current time is within market hours"""
        now = datetime.now().time()
        return MARKET_OPEN <= now <= MARKET_CLOSE
    
    def check_seed_pattern(self) -> bool:
        """Check if buffer contains 0xDF pattern (11011111)"""
        if len(self.edgx_buffer) < 8:
            return False
        
        byte = 0
        for lsb in self.edgx_buffer:
            byte = (byte << 1) | lsb
        
        return byte == 0xDF
    
    def process_trade(self, trade_data: dict):
        """Process incoming trade data"""
        try:
            # Polygon WebSocket trade format
            # Trades: {"ev":"T","sym":"GME","p":price,"s":size,"t":timestamp,"x":exchange}
            if trade_data.get('ev') != 'T' or trade_data.get('sym') != 'GME':
                return
                
            exchange = trade_data.get('x', 0)
            # EDGX exchange ID is 4
            if exchange != 4:
                return
                
            price = trade_data.get('p')
            if price is None:
                return
                
            timestamp = trade_data.get('t', 0)
            
            # Track price for daily return calculation
            self.daily_prices.append({
                'price': price,
                'timestamp': timestamp
            })
            
            # Extract LSB from price (cents & 1)
            cents = int(round(price * 100))
            lsb = cents & 1
            
            # Add to buffer
            self.edgx_buffer.append(lsb)
            
            # Check for 0xDF pattern
            if self.check_seed_pattern():
                self.daily_seeds += 1
                self.logger.info(f"🎯 SEED DETECTED: Price=${price:.2f}, Total Seeds Today: {self.daily_seeds}")
                
                # Check if threshold reached
                if self.daily_seeds == SEED_THRESHOLD:
                    self.logger.warning(f"⚠️  THRESHOLD REACHED: {SEED_THRESHOLD} seeds detected!")
                
        except Exception as e:
            self.logger.error(f"Error processing trade: {e}")
    
    def calculate_daily_return(self) -> float:
        """Calculate daily return from tracked prices"""
        if len(self.daily_prices) < 2:
            return 0.0
        open_price = self.daily_prices[0]['price']
        close_price = self.daily_prices[-1]['price']
        return (close_price - open_price) / open_price
    
    def check_signal(self):
        """Check if signal conditions are met"""
        if self.daily_seeds > SEED_THRESHOLD:
            daily_ret = self.calculate_daily_return()
            
            if daily_ret > FILTER_MIN_RET:
                signal = {
                    'date': self.current_date.isoformat(),
                    'seeds': self.daily_seeds,
                    'daily_return': daily_ret,
                    'status': 'TRADE_SIGNAL',
                    'action': 'BUY_OPEN_T+1'
                }
                self.logger.warning(f"🚨 TRADE SIGNAL: Seeds={self.daily_seeds}, Return={daily_ret:.2%}, Action=BUY OPEN T+1")
            else:
                signal = {
                    'date': self.current_date.isoformat(),
                    'seeds': self.daily_seeds,
                    'daily_return': daily_ret,
                    'status': 'FILTERED',
                    'reason': f'Daily return {daily_ret:.2%} < -5%'
                }
                self.logger.info(f"⚠️  SIGNAL FILTERED: Seeds={self.daily_seeds} but Return={daily_ret:.2%} (too negative)")
            
            return signal
        return None
    
    def save_daily_report(self):
        """Save end-of-day report"""
        date_str = self.current_date.strftime('%Y-%m-%d')
        report_path = LOG_DIR / f"report_{date_str}.json"
        
        daily_ret = self.calculate_daily_return()
        signal = self.check_signal()
        
        report = {
            'date': date_str,
            'seeds_count': self.daily_seeds,
            'daily_return': daily_ret,
            'trades_tracked': len(self.daily_prices),
            'signal': signal,
            'open_price': self.daily_prices[0]['price'] if self.daily_prices else None,
            'close_price': self.daily_prices[-1]['price'] if self.daily_prices else None,
            'session_start': self.session_start.isoformat() if self.session_start else None,
            'session_end': datetime.now().isoformat()
        }
        
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.logger.info(f"📊 Daily report saved: {report_path}")
        return report
    
    async def connect_and_track(self):
        """Connect to Polygon WebSocket and track trades"""
        # Polygon WebSocket endpoint
        uri = f"wss://socket.polygon.io/stocks"
        
        try:
            async with websockets.connect(uri) as websocket:
                self.logger.info("✓ Connected to Polygon WebSocket")
                
                # Authenticate
                auth_msg = {
                    "action": "auth",
                    "params": API_KEY
                }
                await websocket.send(json.dumps(auth_msg))
                auth_response = await websocket.recv()
                auth_data = json.loads(auth_response)
                if auth_data[0].get('ev') == 'status' and auth_data[0].get('status') == 'auth_success':
                    self.logger.info("✓ Authenticated successfully")
                else:
                    self.logger.error(f"Auth failed: {auth_response}")
                    return
                
                # Subscribe to GME trades
                subscribe_msg = {
                    "action": "subscribe",
                    "params": "T.GME"  # T = Trades, GME = symbol
                }
                await websocket.send(json.dumps(subscribe_msg))
                self.logger.info("✓ Subscribed to GME trades")
                
                self.session_start = datetime.now()
                self.logger.info(f"📈 Tracking started: {self.session_start}")
                self.logger.info(f"Target: {SEED_THRESHOLD}+ seeds, Filter: Daily return > {FILTER_MIN_RET:.1%}")
                
                # Listen for messages
                last_status_log = datetime.now()
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        
                        # Polygon sends arrays of events
                        if isinstance(data, list):
                            for event in data:
                                ev_type = event.get('ev')
                                if ev_type == 'status':
                                    msg = event.get('message', '')
                                    # Log status messages but not too frequently
                                    if 'subscribed' in msg.lower() or 'error' in msg.lower():
                                        self.logger.info(f"Status: {msg}")
                                elif ev_type == 'T':  # Trade
                                    self.process_trade(event)
                        
                        # Periodic status updates (every 1000 trades or every 5 minutes)
                        now = datetime.now()
                        if len(self.daily_prices) % 1000 == 0 or (now - last_status_log).seconds >= 300:
                            self.logger.info(f"📊 Status: {len(self.daily_prices)} trades, {self.daily_seeds} seeds (target: {SEED_THRESHOLD})")
                            last_status_log = now
                            
                            # Check for signal
                            signal = self.check_signal()
                            if signal and signal.get('status') == 'TRADE_SIGNAL':
                                self.logger.warning(f"🚨 TRADE SIGNAL ACTIVE: {signal}")
                                
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        self.logger.error(f"Error processing message: {e}")
                        
        except Exception as e:
            self.logger.error(f"WebSocket error: {e}")
            raise

async def main():
    """Main event loop"""
    if not API_KEY:
        print("ERROR: POLYGON_API_KEY not set")
        return
    
    tracker = SteamrollerTracker()
    
    while True:
        try:
            # Check if market is open
            if tracker.is_market_hours():
                await tracker.connect_and_track()
            else:
                # Market closed - save report and wait
                if tracker.daily_prices:
                    tracker.save_daily_report()
                
                # Reset for next day
                tracker = SteamrollerTracker()
                
                # Wait until market opens
                now = datetime.now()
                if now.time() < MARKET_OPEN:
                    # Wait until market open
                    next_open = datetime.combine(now.date(), MARKET_OPEN)
                    wait_seconds = (next_open - now).total_seconds()
                    tracker.logger.info(f"⏸️  Market closed. Waiting {wait_seconds/3600:.1f}h until market open...")
                    await asyncio.sleep(min(wait_seconds, 3600))
                else:
                    # Wait until next trading day
                    tracker.logger.info("⏸️  Market closed. Waiting until next trading day...")
                    await asyncio.sleep(3600)
                    
        except KeyboardInterrupt:
            tracker.logger.info("🛑 Shutting down...")
            if tracker.daily_prices:
                tracker.save_daily_report()
            break
        except Exception as e:
            tracker.logger.error(f"Fatal error: {e}")
            await asyncio.sleep(60)  # Wait before retry

if __name__ == "__main__":
    asyncio.run(main())

