# Study 05: Effect Roles

## Hypothesis

**"Can we classify events into functional roles to provide context?"**

We hypothesized four distinct roles:

1. **Impactor**: Short-term volatility driver.
2. **Binder**: Long-term trend driver.
3. **Echo**: Long-lag replay (Trap).
4. **Macro**: Basket-wide co-occurrence.

## Data

* **Input**: `historical_bursts.json` (335 events).
* **Artifacts**:
  * `effect_roles_labels.json`: Labeled events.
  * `effect_roles_validation.md`: Statistical validation report.

## Methodology

1. **Labeling**: Apply logic for each role (e.g., Echo = TISA match < 2.5).
2. **Validation**: Compare returns of labeled events vs. baseline.

### What this test does (plain language)

* Assign each burst simple behavioural tags:
  * **Impactor** if it explodes right away (big 1‑day runup).
  * **Binder** if it drifts upward over weeks/months (needs 30/90d data).
  * **Echo** if it looks like a past squeeze (GME‑2021 template match).
  * **Macro** if many basket names fire on the same day.
* Then check if these tagged bursts actually behave differently from the rest.

### Reproduction

1. **Download Data**:

   ```bash
   python research/pipelines/05_effect_roles/download_data.py
   ```

2. **Label Roles**:

   ```bash
   python research/pipelines/05_effect_roles/scripts/label_effect_roles.py
   ```

3. **Analyze Effect Roles**:

   ```bash
   python research/pipelines/05_effect_roles/scripts/analyze_effect_roles.py
   ```

## Results

* **Impactor**: **Strongly Validated.** Significantly higher short-term returns (p < 1e-9).
* **Binder**: **Pending.** Historical scan lacks long-term data.
* **Echo**: **Directionally Validated (Trap).** Rare (N=7), negative returns (-5.4% vs +9.2%).
* **Macro**: **Validated as Dampener.** Common (38%), but returns are slightly lower than isolated bursts.

## Interpretation

Context matters. An "Impactor" is a buy signal. An "Echo" is a warning. A "Macro" event suggests crowdedness and potential drag.
