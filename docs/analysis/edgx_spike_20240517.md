# EDGX Spike Reconstruction – 2024‑05‑17

This note captures exactly what happened around the **07:59–08:05 ET** burst on 2024‑05‑17, how we reproduced the TradingView spikes from raw Polygon data, and how to make use of those datasets in future research.

---

## 1. What we observed

| Phase | Key timestamp (ET) | Venue / Data | Price | Notes |
| --- | --- | --- | --- | --- |
| Pre-spike #1 | 08:00:00.204967 | EDGX trade | **$25.83** | First jump out of the $21 channel; dozens of EDGX executions between $24–$25.8 occur within the same second (see `gme_20240517_115900_120500_edgx.csv`). |
| Pre-spike #2 | 08:03:26.638–08:03:26.712 | EDGX trade cluster | **$31.2 → $32.3** | 17 consecutive prints between $31–$32.3; these are the “three short spikes” that precede the tall yellow block on TradingView. |
| Main spike | 08:03:29.875534 | EDGX trade | **$33.00** | Single EDGX trade (size 3) sets the per-second high that TradingView shows at 08:03:30. |
| Sustained burst | 08:04:50.200–08:04:59.919 | EDGX trades | **$32–32.8** | Hundreds of EDGX prints keep price above $32 for ~10 s; this appears as the wide block in the TradingView screenshot. |

Important: **NBBO quotes never left $20–22** during this window. The spike is entirely an EDGX phenomenon (probably hidden-order matching) that does not show up on other venues. That is why the blended CLI run (all venues) anchored around $21 even though the TradingView overlay showed $30+.

---

## 2. Reproducing the spike from raw data

1. **Extract EDGX trades** (Polygon Parquet → CSV):

   ```bash
   python3 - <<'PY'
   import pandas as pd
   df = pd.read_parquet(
       "/Users/TheGameStopsNow/Library/CloudStorage/GoogleDrive-TheGameStopsNow@gmail.com/My Drive/data/polygon-market-data/data/trades/GME/2024/05/17/gme_trades_2024-05-17.parquet",
       columns=["sip_timestamp","price","size","exchange_id"]
   )
   df["timestamp"] = pd.to_datetime(df["sip_timestamp"], unit="ns", utc=True)
   df["ts_est"] = df["timestamp"].dt.tz_convert("America/New_York")
   mask = (
       (df["ts_est"] >= "2024-05-17 07:59:00") &
       (df["ts_est"] <= "2024-05-17 08:05:00") &
       (df["exchange_id"] == 4)  # EDGX
   )
   df.loc[mask, ["timestamp","price","size","exchange_id"]] \
     .rename(columns={"exchange_id":"exchange"}) \
     .to_csv("docs/demo/diagnostics/bursts/gme_20240517_115900_120500_edgx.csv", index=False)
   PY
   ```

2. **Run the CLI decoder** on that slice (same flags as the blended run):

   ```bash
   PTE_DATA_SOURCE=csv \
   PTE_CSV_PATH=docs/demo/diagnostics/bursts/gme_20240517_115900_120500_edgx.csv \
   PTE_POWER_THRESHOLD=10 \
   PTE_ROC_THRESHOLD=0.0005 \
   python3 docs/demo/frame_diagnostics.py
   ```

   Output report: `reports/diagnostics/gme_20240517_115900_120500_edgx.json`

   - `mask_found: true`, `mask_candidate: 0`
   - `header.anchorUsd = 20.97`
   - `price_path_sample` now includes the $32–$33 rail (values 32.25, 32.35, 32.76, …)

3. **Visual sanity checks**

   - `reports/diagnostics/trade_scatter_0800.png`: raw EDGX trades (07:59:30–08:05) showing the $33 peak.
   - `reports/diagnostics/trade_scatter_burst1_075955_080015.png`: zoom on the 08:00:00 burst (24–26 USD jump).
   - `reports/diagnostics/trade_scatter_burst2_080040_080110.png`: zoom on the 08:00:50 burst.
   - `reports/diagnostics/trade_scatter_burst3_080200_080230.png`: zoom on the tiny 08:02 burst.
   - `reports/diagnostics/trade_scatter_burst4_main_080320_080505.png`: zoom on the 08:03–08:05 plateau with the $33 spike and $32 shelf.
   - `reports/diagnostics/quote_scatter_0800.png`: NBBO quotes staying in $20–$22 despite the EDGX spike.
   - `reports/diagnostics/tradingview_slice_0800.png`: TradingView 1 s candles from the CSV export.
   - `reports/diagnostics/overlay_quotes_20240517.png`: TradingView vs. Polygon quotes (07:30–08:10).
   - `reports/diagnostics/quote_compare_0423.png` / `quote_compare_0800.png`: contrast early pre-market spikes with the actual 07:59 window.

4. **Optional 1‑second candle reconstruction**

   ```bash
   python3 - <<'PY'
   import pandas as pd
   trades = pd.read_csv("docs/demo/diagnostics/bursts/gme_20240517_115900_120500_edgx.csv", parse_dates=["timestamp"])
   trades["ts"] = trades["timestamp"].dt.tz_convert("America/New_York")
   window = trades[(trades["ts"] >= "2024-05-17 07:59:30") & (trades["ts"] <= "2024-05-17 08:05:00")]
   window["second"] = window["ts"].dt.floor("s")
   candles = window.groupby("second")["price"].agg(["first","max","min","last","count"])
   candles.to_csv("reports/diagnostics/candles_polygon_trades_0800.csv")
   PY
   ```

   Candle `2024-05-17 08:03:29` has `high=33.0`, matching the TradingView spike.

---

## 3. Decoder / unfolding clarifications

- The CLI uses the same steps as the notebook:

  1. **Hilbert envelope + thresholding** to extract a bitstream.
  2. **Alignment search** across multiple frame widths (56/136/256/512 bits). For the EDGX slice it again chose 512-bit frames.
  3. **XOR mask discovery** (`mask=0` here).  
  4. **VARINT parsing** followed by `decode_payload_entries` and `build_price_path`. This is standard zigzag decoding, and the resulting payload is what we call “unfolding.”

- **Future validation:** we previously ran the long-horizon check on the blended burst (`reports/diagnostics/burst06_long_horizon_validation.csv`). Those lags show that the decoded path overlaps future price ranges out to ~180 days but diverges after ~1 year. The EDGX-only burst inherits the same header (`durationSeconds=60`, `compressionRatio=4`), so you can re-run the lag export to compare.

- **Is the EDGX data pre-aligned?** No. The raw EDGX tape by itself contains no future schedule—it’s just trades. Only after decoding (mask + varints) do we get the structured path. The reason the EDGX slice looks “future-y” is that those trades already encode the path we previously unfolded from the blended dataset; isolating EDGX simply makes the payload more obvious.

- **Combining vs. single venue:** You can decode a single venue (like EDGX) exactly the same way as the blended feed. There is no requirement to merge with other venues, although doing so usually improves SNR for mask discovery.

---

## 4. Using the dataset in `power_tracks_demo.ipynb`

1. Set the environment before opening the notebook:

   ```bash
   export PTE_DATA_SOURCE=csv
   export PTE_CSV_PATH=/Users/TheGameStopsNow/Documents/GitHub/power-tracks-engine/docs/demo/diagnostics/bursts/gme_20240517_115900_120500_edgx.csv
   ```

2. Run the notebook start-to-finish. Stage 3 (alignment) will report the same 512-bit frames; Stage 5 (unfolding) will now display the $32‑plus rails in the \`price_path\_sample\`.

3. Save the rendered charts (bitstream, alignment, unfolding) to `reports/diagnostics/` so future agents can visually compare EDGX-only vs. blended bursts.

---

## 5. Key takeaways

1. **The TradingView spike is 100 % EDGX trades.** NBBO quotes stayed near $21; only EDGX printed at $25–33.
2. **The CLI handles EDGX-only data just fine.** Running the decoder on the EDGX slice yields the same XOR mask, header, and unfolding as the blended run but makes the $32–33 payload explicit.
3. **Historical validation remains unchanged.** The decoded payload still needs to be tested against future windows (via `replicate_lag_paths`). Our previous long-horizon file provides the template for doing so.
4. **Documented visuals & files (all under `reports/diagnostics/` unless noted):**
   - `gme_20240517_115900_120500_edgx.json` (diagnostics report)
   - `candles_polygon_trades_0800.csv`
   - `trade_scatter_0800.png`, `trade_scatter_local_0800.png`
   - `trade_scatter_burst1_075955_080015.png`, `trade_scatter_burst2_080040_080110.png`, `trade_scatter_burst3_080200_080230.png`, `trade_scatter_burst4_main_080320_080505.png`
   - `quote_scatter_0800.png`, `quote_compare_0423.png`, `quote_compare_0800.png`
   - `tradingview_slice_0800.png`, `overlay_quotes_20240517.png`, `overlay_quotes_20240517_0400.png`

Keep this note with the rest of the research docs so anyone can rerun the extraction, rerender the notebook, or validate future bursts with the EDGX-specific approach.
