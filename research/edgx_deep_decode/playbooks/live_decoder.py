#!/usr/bin/env python3
"""
Live Decoder & Regime Detector
==============================

Simulates a real-time feed from historical EDGX data and performs
"Heads-Up" decoding of the volatility state machine.

Key Components:
1. EDGXStream: Simulates a websocket feed (tick-by-tick).
2. LiveParser: Maintains state, decodes LSBs, builds messages.
3. RegimeDetector: Calculates "Grammar Score" and identifies state (War vs Peace).
"""

import time
import sys
from pathlib import Path
from typing import Generator, List, Optional, Tuple, Deque
from dataclasses import dataclass
from collections import deque
import pandas as pd
import numpy as np

# Import local modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs
from packet_decoder import bits_to_bytes

# --- Constants & Opcodes ---
# LSB Extraction Mask
LSB_MASK = 0x01

# ASCII Control Codes
SOH = 0x01  # Start of Header
STX = 0x02  # Start of Text
ETX = 0x03  # End of Text

# EDGX Opcodes
OP_FLOOR   = 0xA0  # Hard Floor (War)
OP_CEILING = 0x98  # Hard Ceiling (War)
OP_PIVOT   = 0x80  # Pivot (Peace)
OP_STATION = 0x10  # Station Keeping (Peace)
OP_LIFT    = 0x01  # SOH / Lift (Momentum Injection)
OP_START   = 0x02  # STX / Start (Sequence Begin)

@dataclass
class TradeTick:
    timestamp: pd.Timestamp
    price: float
    volume: int
    venue: int
    # Computed fields
    lsb: int

@dataclass
class SignalEvent:
    timestamp: pd.Timestamp
    opcode: int
    name: str
    regime: str
    price: float


class EDGXStream:
    """
    Simulates a live data stream from historical CSV files.
    """
    def __init__(self, data_frame: pd.DataFrame, delay: float = 0.0):
        """
        Args:
            data_frame: Pre-loaded dataframe of EDGX trades.
            delay: Artificial delay in seconds between ticks (0 for max speed).
        """
        self.df = data_frame
        self.delay = delay
        self._iterator = self._create_iterator()
        
    def _create_iterator(self) -> Generator[TradeTick, None, None]:
        for _, row in self.df.iterrows():
            # Extract basic fields
            # Simple LSB for simulation purposes (logic will be refined in LiveParser)
            # We will pass the raw price; the Parser will handle byte construction.
            
            lsb = int(row['price'] * 100) & 1 # Default assumption: pennies
            
            yield TradeTick(
                timestamp=row['timestamp'],
                price=row['price'],
                volume=row['volume'],
                venue=row['venue'],
                lsb=lsb
            )
            
            if self.delay > 0:
                time.sleep(self.delay)

    def stream(self) -> Generator[TradeTick, None, None]:
        yield from self._iterator


class LiveParser:
    """
    Ingests ticks, assembles bits into bytes, and decodes opcodes.
    """
    def __init__(self):
        self.bit_buffer: List[int] = [] # Accumulates 8 bits
        self.byte_stream: List[int] = [] # History of bytes (for sliding window)
        self.msg_buffer: List[int] = []  # Current message being assembled
        self.events: List[SignalEvent] = []
        
        # Regime State
        self.window_size = 100
        self.opcode_history: Deque[int] = deque(maxlen=1000)
        self.current_regime = "NEUTRAL"
        self.storm_score = 0.0 # 0.0 to 1.0
        
    def process_tick(self, tick: TradeTick) -> Optional[SignalEvent]:
        # 1. Extract LSB
        bit = int(tick.price * 100) & 1  
        
        # 2. Add to bit buffer
        self.bit_buffer.append(bit)
        
        # 3. If 8 bits, form a byte
        if len(self.bit_buffer) == 8:
            byte_val = 0
            for b in self.bit_buffer:
                byte_val = (byte_val << 1) | b
            
            # Clear bit buffer
            self.bit_buffer = []
            
            # Add to stream
            self.byte_stream.append(byte_val)
            self._update_regime_metrics(byte_val)
            
            # 4. Decode
            return self._decode_byte(byte_val, tick)
            
        return None

    def _update_regime_metrics(self, new_byte: int):
        self.opcode_history.append(new_byte)
        
        # Calculate scores over last N bytes
        if len(self.opcode_history) < 50:
            return

        # Count recent opcodes (last 50)
        recent = list(self.opcode_history)[-50:]
        
        storm_ops = recent.count(OP_FLOOR) + recent.count(OP_CEILING)
        calm_ops = recent.count(OP_PIVOT) + recent.count(OP_STATION)
        
        total_ops = storm_ops + calm_ops
        if total_ops > 0:
            self.storm_score = storm_ops / total_ops
        else:
            self.storm_score = 0.0
            
        if self.storm_score > 0.6:
            self.current_regime = "STORM"
        elif self.storm_score < 0.3 and total_ops > 5:
            self.current_regime = "CALM"
        else:
            self.current_regime = "TRANSITION"

    def _decode_byte(self, byte_val: int, tick: TradeTick) -> Optional[SignalEvent]:
        event = None
        
        # Check for Opcodes
        name = ""
        regime = self.current_regime # Use calculated regime
        
        if byte_val == OP_FLOOR:
            name = "HARD FLOOR"
        elif byte_val == OP_CEILING:
            name = "HARD CEILING"
        elif byte_val == OP_PIVOT:
            name = "PIVOT"
        elif byte_val == OP_STATION:
            name = "STATION KEEPING"
        elif byte_val == OP_LIFT:
            name = "LIFT (SOH)"
        elif byte_val == OP_START:
            name = "START (STX)"
            
        if name:
            event = SignalEvent(
                timestamp=tick.timestamp,
                opcode=byte_val,
                name=name,
                regime=regime,
                price=tick.price
            )
            self.events.append(event)
            # Print alert
            # Optional: Don't print EVERY lift/start if there are too many, but for now let's see.
            # Lifts might be frequent.
            if byte_val not in [OP_LIFT, OP_START]:
                 print(f"[{tick.timestamp}] ALERT: {name} (0x{byte_val:02X}) @ ${tick.price:.2f} | Regime: {regime} ({self.storm_score:.2f})")
            
        return event

def run_live_simulation():
    print("=" * 60)
    print("GLASS OPs START: Phase II Real-Time Simulation")
    print("=" * 60)
    
    # 1. Load Data
    sample_dirs = get_sample_dirs()
    if not sample_dirs:
        print("No data found.")
        return

    # Use a known storm day if possible, or just the latest
    target_dir = sample_dirs[-1]
    print(f"Loading tape from: {target_dir.name}")
    
    df = load_edgx_data(target_dir, symbol='GME')
    print(f"Loaded {len(df)} ticks.")
    
    # 2. Init System
    stream = EDGXStream(df) # No delay for fast simulation
    parser = LiveParser()
    
    print("\n[LIVE FEED STARTED]")
    start_time = time.time()
    tick_count = 0
    
    try:
        for tick in stream.stream():
            event = parser.process_tick(tick)
            tick_count += 1
            
            if tick_count % 10000 == 0:
                sys.stdout.write(f"\rProcessed {tick_count} ticks...")
                sys.stdout.flush()
                
    except KeyboardInterrupt:
        print("\n\nSimulation Stopped.")
        
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"\n\n[SIMULATION COMPLETE]")
    print(f"Processed {tick_count} ticks in {duration:.2f}s ({tick_count/duration:.0f} ticks/s)")
    print(f"Total Events Detected: {len(parser.events)}")
    
    # Summary of events
    if parser.events:
        print("\nEvent Summary:")
        ev_df = pd.DataFrame([vars(e) for e in parser.events])
        print(ev_df['name'].value_counts())

if __name__ == "__main__":
    run_live_simulation()
