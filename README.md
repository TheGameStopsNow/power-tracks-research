# Power Tracks Research

Comprehensive research repository for "Power Tracks," "Stock Galaxy," and "Warped Prism" market mechanics. This codebase contains the tools, pipelines, and validation suites used to uncover and map systemic anomalies in modern market microstructure.

## Structure

The research is divided into three primary pillars:

### I. The Signal: Power Tracks & Steganography
*Detecting the anomalous "heartbeat" and hidden data channels.*

- **Phase 57**: [Detection Stack](research/phase57_detection_stack/) - The primary harness for detecting Power Tracks.
- **Steganography**: [26-Day Analysis](research/steganography/) - Comprehensive study of covert signaling in print data.
- **EDGX Decode**: [Operation Glasshouse](research/edgx_deep_decode/) - Deep dive into exchange-specific order types and opcodes.

### II. The Map: Stock Galaxy & Cartography
*Mapping the interconnected "hydraulic" system of volatility.*

- **Phase 14**: [Genome Sequencing](research/phase14_genome/) - Initial classification of ticker behavior.
- **Phase 16**: [Galaxy Scan](research/phase16_galaxy/) - Broad market-wide cluster analysis.
- **Phase 26**: [Hydraulics](research/phase26_hydraulics/) - Proof of conservation of volatility.
- **Phase 29**: [System Cartography](research/phase29_system_cartography/) - The "7-4-1" signal and system map.
- **Phase 30**: [Interconnectedness](research/phase30_interconnectedness/) - Final verification of system-wide coupling.

*(Also includes Phases 18, 22, 23, 24, 25, 27)*

### III. The Physics: Warped Prism & Market Mechanics
*Analyzing the specific gamma/IV mechanics driving the signal.*

- **Phase 74**: [RegA Detection](research/phase74_rega/) - Identifying Gamma Suppression zones.
- **Phase 75**: [Predictability](research/phase75_predictability/) - Causal links between options flow and price action.
- **Phase 77**: [Greek Echo](research/phase77_greek_echo/) - Isolating Charm and Vanna flows.
- **Phase 82**: [Warped Prism Report](research/phase82_reporting/) - Final synthesis of the mechanical model.
- **Phase 83**: [Math Model](research/phase83_math_model/) - The "Prism Equation" formalization.

*(Also includes Phases 76, 78, 79, 80, 81, 86)*

## Usage

Each phase directory contains a `manifest.json` describing necessary data and a `download_data.py` script to fetch it (requires Polygon.io / ThetaData keys).

To hydrate data for a phase:
```bash
python research/phaseXX_name/download_data.py
```
