# Phase 4: Steganalysis & ML Detection

## Hypothesis

Machine learning models can detect steganographic embedding in financial data even without labeled examples.

## Method

1. Train anomaly detection models on "clean" market data
2. Generate synthetic stego-data for validation
3. Test detection on held-out periods
4. Ensemble methods combining Phases 1-3

## Model Approaches

- **Unsupervised**: Autoencoders, isolation forests, DBSCAN
- **Semi-supervised**: One-class SVM, deep SVDD
- **Graph-based**: GNN for order book state transitions
- **Temporal**: LSTM, Transformer for sequence anomalies

## Metrics

- ROC-AUC on synthetic stego-data
- False positive rate on known-clean data
- Detection latency (how fast can we flag?)
- Bandwidth estimation (how much was embedded?)

## Deliverables

- [ ] Synthetic stego-data generator
- [ ] Model training pipeline
- [ ] Benchmark results across methods
- [ ] Production-ready detection module
- [ ] Integration recommendations for Power Tracks

## Challenges

- No labeled real-world stego examples exist
- Adversarial adaptation by sophisticated actors
- False positives harm legitimate trading

## Status

⚪ Pending Phase 3 completion
