# Power Tracks Research

Research repository for the "Stock Galaxy" and "Warped Prism" market mechanics series.

## Structure

This repository is organized into research phases, each targeting a specific hypothesis or validation step.

### Key Phases (Warped Prism Series)

- **Phase 72-74**: [RegA Detection Stack](research/phase74_rega/) (Gamma Suppression)
- **Phase 75**: [Predictability & Echoes](research/phase75_predictability/)
- **Phase 76**: [Echo Quant](research/phase76_echo_quant/)
- **Phase 77**: [Greek Echo](research/phase77_greek_echo/) (Charm & Vanna)
- **Phase 78**: [Context Morphology](research/phase78_context_morphology/)
- **Phase 79**: [Control Group](research/phase79_control/) (Low Gamma Validation)
- **Phase 80**: [Generality](research/phase80_generality/) (NVDA Validation)
- **Phase 81**: [Precision](research/phase81_precision/) (Universe/Thresholds)
- **Phase 82**: [Project Reporting](research/phase82_reporting/)
- **Phase 83**: [Math Model](research/phase83_math_model/)

## Usage

Each phase directory contains a `manifest.json` describing necessary data and a `download_data.py` script to fetch it (requires Polygon.io / ThetaData keys).

run `python research/phaseXX_name/download_data.py` to hydrate the data for a specific phase.
