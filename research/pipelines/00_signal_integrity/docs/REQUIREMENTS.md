# Requirements and Dependencies

## Python Dependencies

All Python dependencies are pinned in `requirements.txt` for reproducibility.

### Core Dependencies

- **numpy** (>=1.24.0, <2.0.0): Numerical computing
- **pandas** (>=2.0.0, <3.0.0): Data manipulation and analysis
- **pyarrow** (>=14.0.0, <15.0.0): Parquet file support

### Testing

- **pytest** (>=7.4.0, <8.0.0): Test framework

### Optional Dependencies

- **scipy** (>=1.10.0, <2.0.0): Scientific computing (for signal processing)
- **pyshark** (>=0.6): Packet analysis (for Wireshark integration)
- **matplotlib** (>=3.7.0, <4.0.0): Plotting and visualization
- **jupyter** (>=1.0.0): Jupyter notebook support
- **notebook** (>=7.0.0): Jupyter notebook server
- **ipykernel** (>=6.25.0): Jupyter kernel

## Node.js Dependencies

All Node.js dependencies are pinned in `package.json`.

### Development Dependencies

- **typescript** (^5.3.0): TypeScript compiler
- **jest** (^30.0.0): Test framework
- **ts-jest** (^29.1.0): TypeScript support for Jest
- **@types/jest** (^30.0.0): TypeScript types for Jest
- **@types/node** (^20.10.0): TypeScript types for Node.js

## Installation

### Python Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Node.js Environment

```bash
# Install dependencies
npm install
```

## System Requirements

- **Python**: 3.8 or higher
- **Node.js**: 18.18.0 or higher
- **npm**: 9.0.0 or higher

## Optional Tools

### Binary Analysis

- **010 Editor**: For binary file analysis (use template in `tools/010_editor/`)
- **Kaitai Struct**: For binary format parsing (use schema in `tools/kaitai/`)
- **Wireshark**: For packet analysis (use dissector in `tools/wireshark/`)

### Data Versioning

- **DVC**: For data version control (optional, see `DVC_GUIDE.md`)

## Verification

After installation, verify dependencies:

```bash
# Python
python -c "import numpy, pandas, pyarrow; print('Python dependencies OK')"

# Node.js
npm test
```


