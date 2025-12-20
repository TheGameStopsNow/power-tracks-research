# Phase 3: Order Book Microstructure Encoding

## Hypothesis

Transient order book configurations (spread patterns, depth ratios) may serve as covert codewords.

## Method

1. Capture order book snapshots at millisecond granularity
2. Define configuration space (spread values, depth ratios, order sizes)
3. Mine for recurring ephemeral patterns
4. Statistical testing against null (random configuration evolution)

## Data

- Level 2 order book data (if available)
- NBBO quote stream with timestamps
- Historical spread/depth metrics

## Metrics

- Pattern recurrence frequency
- Information content per configuration
- Temporal clustering of specific states
- Cross-symbol correlation of patterns

## Deliverables

- [ ] Order book state encoder
- [ ] Pattern mining notebook
- [ ] Codebook hypothesis generator
- [ ] False positive rate analysis

## Challenges

- Combinatorial explosion of possible states
- Legitimate market-making creates similar patterns
- Data availability (L2 is expensive/rare)

## Status

⚪ Pending Phase 2 completion
