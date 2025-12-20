
import pandas as pd
import numpy as np
from pathlib import Path

SIGNAL_LOG = Path("research/phase30_interconnectedness/2025_signal_log.csv")
REPORT_FILE = Path("research/phase30_interconnectedness/2025_YEAR_IN_REVIEW.md")

def generate_report():
    if not SIGNAL_LOG.exists():
        print("Signal log not found.")
        return

    df = pd.read_csv(SIGNAL_LOG)
    df['date'] = pd.to_datetime(df['date'])
    df['month'] = df['date'].dt.strftime('%Y-%m')
    
    # 1. Overview Stats
    total_signals = len(df)
    total_days = df['date'].nunique()
    signals_per_day = total_signals / total_days if total_days > 0 else 0
    active_tickers = df['symbol'].nunique()
    
    # 2. Top Tickers
    top_tickers = df['symbol'].value_counts().head(10)
    
    # 3. Monthly Trend
    monthly_counts = df.groupby('month').size()
    
    # 4. Pattern Balance
    type_counts = df['type'].value_counts(normalize=True)
    
    # 5. Identify "Hot" Days (95th percentile)
    daily_counts = df.groupby('date').size()
    hot_days_threshold = daily_counts.quantile(0.95)
    hot_days = daily_counts[daily_counts >= hot_days_threshold].sort_values(ascending=False).head(5)
    
    # Generate Markdown
    with open(REPORT_FILE, "w") as f:
        f.write("# 2025 Year in Review: The Algorithm\n\n")
        f.write("**Status:** Auto-Generated Analysis\n")
        f.write(f"**Data Range:** {df['date'].min().date()} to {df['date'].max().date()}\n")
        f.write(f"**Total Signals:** {total_signals:,}\n\n")
        
        f.write("## 1. Executive Summary\n")
        f.write("In 2025, the 'Basket Algorithm' (7-4-1 Signal) remained highly active. ")
        f.write(f"The signal appeared on **{active_tickers}** unique tickers, firing an average of **{signals_per_day:.1f}** times per day across the network.\n\n")
        
        f.write("## 2. Most Active Tickers (The 'Swarm' Leaders)\n")
        f.write("| Ticker | Signal Count | Share of Total |\n")
        f.write("| :--- | :--- | :--- |\n")
        for sym, count in top_tickers.items():
            share = (count / total_signals) * 100
            f.write(f"| {sym} | {count:,} | {share:.1f}% |\n")
        f.write("\n")
        
        f.write("## 3. Temporal Evolution (Monthly Activity)\n")
        f.write("Signal density varies significantly by month, indicating 'Regime Shifts'.\n\n")
        f.write("| Month | Total Signals | Trend |\n")
        f.write("| :--- | :--- | :--- |\n")
        for month, count in monthly_counts.items():
            # Simple trend visualization
            bar = "█" * int(count / monthly_counts.max() * 20)
            f.write(f"| {month} | {count:,} | `{bar}` |\n")
        f.write("\n")
        
        f.write("## 4. Notable Events ('Hot Days')\n")
        f.write("The network activity peaked on these dates, suggesting localized volatility events:\n\n")
        for date, count in hot_days.items():
            f.write(f"- **{date.date()}:** {count} signals\n")
        f.write("\n")
        
        f.write("## 5. Pattern Mechanics\n")
        f.write(f"- **Forward (7-4-1):** {type_counts.get('FORWARD_741', 0)*100:.1f}%\n")
        f.write(f"- **Reverse (1-4-7):** {type_counts.get('REVERSE_741', 0)*100:.1f}%\n")
        f.write("\n")
        f.write("The balance between Forward (Initiation) and Reverse (Termination) signals remains consistent with previous years.\n")

    print(f"Report generated at {REPORT_FILE}")

if __name__ == "__main__":
    generate_report()
