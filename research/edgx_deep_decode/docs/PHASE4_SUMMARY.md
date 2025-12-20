# Operation Glasshouse - Phase 4 Summary

## Frame Detection Results

### Methodology
- Searched for Start-of-Frame (SOF) markers using pattern matching
- Tested marker lengths: 8, 12, 16, 24, 32 bits
- Analyzed spacing regularity (CV-based metric)

### Findings

**Top Candidate: 32-bit pattern**
- Pattern: `10000000000000000000000000000000`
- Occurrences: 180
- **Regularity: 0.5323** (53.2%)
- Mean spacing: 273.6 bits (~274-bit frames)

**Second Candidate: 24-bit pattern**
- Pattern: `000000000000000000000001`
- Occurrences: 218
- Regularity: 0.5257 (52.6%)
- Mean spacing: 229.3 bits

### Interpretation

**Moderate Regularity Detected** (~53%)
- Frame structure is *possible* but not definitive
- Regularity threshold: typically need >70% for confident framing
- The 53% score suggests:
  - Either: Weak frame structure exists (noisy channel)
  - Or: Patterns are coincidental (false positive)

**Frame hypothesis**: If real, frames are ~274 bits long

## Price Action Correlation (In Progress)

Currently analyzing whether extracted signals predict future price movements at:
- 60s (1 min)
- 300s (5 min)
- 900s (15 min)
- 3600s (1 hour)

Testing signals:
1. `price_lsb_1c` (0.8342 autocorr - highest suspicion)
2. `timing_1ms`
3. `price_lsb_01c`

*Analysis running on 99,247 trades...*

## Next Steps

1. **Complete correlation analysis**
2. **NIST Test Suite integration** (Dieharder)
3. **Cross-symbol validation** (AMC, BB, etc.)
4. **If predictive signal found**: Protocol reverse engineering
5. **If no prediction**: Alternative hypotheses (HFT artifacts, market mechanics)
