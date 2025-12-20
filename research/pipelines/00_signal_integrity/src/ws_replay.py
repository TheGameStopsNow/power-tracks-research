#!/usr/bin/env python3
"""
Replay tick CSV over a local WebSocket so the pipeline can be tested as if it were live.

Usage:
  python scripts/ws_replay.py --ticks sample_2024-05-13/raw_ticks/GME_2024-05-13_trades.csv --port 8765 --rate 500

Options:
  --ticks       Path to tick CSV (requires columns: timestamp, price, volume)
  --host        Host to bind (default: 127.0.0.1)
  --port        Port to bind (default: 8765)
  --rate        Messages per second (approx; default: 1000). If set to 0, uses real tick deltas.
  --loop        If set, loop through the file continuously.
  --symbol      Override symbol in payload (optional)

Payload:
  JSON object per tick: {"ts": "...", "price": float, "volume": float, "venue": str, "symbol": str}
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import List

import pandas as pd
import websockets


def load_ticks(path: Path, symbol_override: str = None) -> List[dict]:
    df = pd.read_csv(path)
    required = {"timestamp", "price"}
    if not required.issubset(df.columns):
        raise ValueError(f"{path} must include {required}")
    ticks = []
    for _, row in df.iterrows():
        ticks.append(
            {
                "ts": str(row["timestamp"]),
                "price": float(row["price"]),
                "volume": float(row["volume"]) if "volume" in df.columns else None,
                "venue": row["venue"] if "venue" in df.columns else None,
                "symbol": symbol_override or row.get("symbol") or "UNKNOWN",
            }
        )
    return ticks


async def replay(websocket, path, ticks: List[dict], rate: int, loop: bool):
    while True:
        prev_ts = None
        for tick in ticks:
            await websocket.send(json.dumps(tick))
            if rate and rate > 0:
                await asyncio.sleep(1.0 / rate)
            else:
                # approximate real-time using timestamp delta if possible
                if prev_ts is not None:
                    try:
                        delta = pd.to_datetime(tick["ts"], utc=True) - prev_ts
                        sleep_s = max(delta.total_seconds(), 0)
                        await asyncio.sleep(sleep_s)
                    except Exception:
                        pass
                prev_ts = pd.to_datetime(tick["ts"], utc=True)
        if not loop:
            break


async def main():
    parser = argparse.ArgumentParser(description="Replay tick CSV over WebSocket")
    parser.add_argument("--ticks", required=True, type=Path, help="Tick CSV path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--rate", type=int, default=1000, help="Messages per second (0 = real-time delta)")
    parser.add_argument("--loop", action="store_true", help="Loop replay")
    parser.add_argument("--symbol", help="Override symbol in payload")
    args = parser.parse_args()

    ticks = load_ticks(args.ticks, args.symbol)
    if not ticks:
        raise SystemExit("No ticks loaded")

    async def handler(ws, path):
        await replay(ws, path, ticks, args.rate, args.loop)

    print(f"Starting WebSocket replay on ws://{args.host}:{args.port} ({len(ticks)} ticks, rate={args.rate}/s)")
    async with websockets.serve(handler, args.host, args.port):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
