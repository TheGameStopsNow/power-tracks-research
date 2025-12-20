import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os

# --- parameters ---
START_DATE = "2002-02-13" # first trading day of GME IPO
np.random.seed(1) # for reproducibility
YEARS = 30 # 30 trading years
N = 250 * YEARS # 250 trading days per year
k1, k4, k7 = 0.50, -0.25, 0.15  # lag coefficients
sigma = 0.15 # noise standard deviation

# --- simulate ---
close = np.zeros(N)
close[0:2] = 30, 30.5
noise = np.random.normal(0, sigma, size=N)

for t in range(2, N):
    d1 = k1 * (close[t-1] - close[t-2])
    d4 = k4 * (close[t-4] - close[t-5]) if t >= 5 else 0
    d7 = k7 * (close[t-7] - close[t-8]) if t >= 8 else 0
    close[t] = close[t-1] + d1 + d4 + d7 + noise[t]
    if close[t] < 1:
        close[t] = 1

# --- plot ---
dates = pd.date_range(START_DATE, periods=N, freq="B") 
fig, ax = plt.subplots(figsize=(12,4))
ax.plot(dates, close, linewidth=1)
ax.set_title(f"{YEARS}-year 741‑lag simulation (daily bars)")
ax.xaxis.set_major_locator(mdates.YearLocator(base=5))
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
plt.xticks(rotation=45)
plt.tight_layout()

# Create output directory if it doesn't exist
output_dir = './output'
os.makedirs(output_dir, exist_ok=True)

plt.savefig(f'{output_dir}/741_simulation_{YEARS}years.png')
print(f"Simulation complete. Chart saved to {output_dir}/741_simulation_{YEARS}years.png")
plt.close()
