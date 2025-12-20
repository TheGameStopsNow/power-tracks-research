# Phase 2: Timing Channel Analysis

## Hypothesis

Inter-arrival times of orders/trades may encode covert information through intentional modulation.

## Method

1. Build inter-event time distributions for order flow
2. Detect regularity patterns (clustering around specific intervals)
3. Apply entropy-based steganalysis from network security literature
4. Compare HFT vs. retail timing signatures

## Data

- Trade-level timestamps (if available)
- Quote update timestamps
- Order submission/cancellation timestamps

## Metrics

- Inter-arrival time distribution entropy
- Coefficient of variation in timing
- Spectral analysis of timing sequences
- Anomaly detection via LSTM/autoencoder

## Deliverables

- [ ] Timing extraction pipeline
- [ ] Distribution analysis notebook
- [ ] Comparison to known HFT patterns
- [ ] Covert channel bandwidth estimation

## Challenges

- Clock synchronization assumptions
- Natural timing variance from network latency
- Separating intentional from algorithmic timing

## Status

⚪ Pending Phase 1 completion
