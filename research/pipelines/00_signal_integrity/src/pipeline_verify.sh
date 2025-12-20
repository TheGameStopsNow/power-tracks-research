#!/bin/bash
# Power Track Pipeline Verification Script
# Runs raw → frames → signals pipeline and validates against SHA256 checksums

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default values
INPUT_DIR="${INPUT_DIR:-$BUNDLE_DIR/sample_2024-05-13/raw_ticks}"
OUTPUT_DIR="${OUTPUT_DIR:-$BUNDLE_DIR/output}"
VERIFY_SHA256="${VERIFY_SHA256:-false}"
MASK="${MASK:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check dependencies
check_dependencies() {
    log_info "Checking dependencies..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "python3 not found"
        exit 1
    fi
    
    if ! python3 -c "import numpy, pandas" &> /dev/null; then
        log_error "Required Python packages not installed. Run: pip install -r requirements.txt"
        exit 1
    fi
    
    log_info "Dependencies OK"
}

# Calculate SHA256 checksum
calculate_sha256() {
    local file="$1"
    if command -v sha256sum &> /dev/null; then
        sha256sum "$file" | cut -d' ' -f1
    elif command -v shasum &> /dev/null; then
        shasum -a 256 "$file" | cut -d' ' -f1
    else
        log_error "No SHA256 utility found (sha256sum or shasum)"
        exit 1
    fi
}

# Verify SHA256 checksum
verify_sha256() {
    local file="$1"
    local expected="$2"
    
    if [ ! -f "$file" ]; then
        log_error "File not found: $file"
        return 1
    fi
    
    local actual=$(calculate_sha256 "$file")
    
    if [ "$actual" = "$expected" ]; then
        log_info "SHA256 verified: $(basename "$file")"
        return 0
    else
        log_error "SHA256 mismatch for $(basename "$file")"
        log_error "Expected: $expected"
        log_error "Actual:   $actual"
        return 1
    fi
}

# Process raw ticks to frames
process_raw_to_frames() {
    log_info "Processing raw ticks to frames..."
    
    local input_file="$INPUT_DIR/GME_2024-05-13_trades.csv"
    local output_file="$OUTPUT_DIR/frames.bin"
    
    if [ ! -f "$input_file" ]; then
        log_error "Input file not found: $input_file"
        exit 1
    fi
    
    # Create output directory
    mkdir -p "$OUTPUT_DIR"
    
    # Run Python script to extract frames
    python3 "$SCRIPT_DIR/raw_to_signals.py" \
        --input "$input_file" \
        --output "$output_file" \
        --format binary \
        ${MASK:+--mask "$MASK"}
    
    if [ $? -eq 0 ]; then
        log_info "Frames extracted: $output_file"
    else
        log_error "Failed to extract frames"
        exit 1
    fi
}

# Process frames to signals
process_frames_to_signals() {
    log_info "Processing frames to signals..."
    
    local input_file="$OUTPUT_DIR/frames.bin"
    local output_file="$OUTPUT_DIR/price_paths.csv"
    
    if [ ! -f "$input_file" ]; then
        log_error "Frames file not found: $input_file"
        exit 1
    fi
    
    # Run Python script to decode frames
    python3 "$SCRIPT_DIR/raw_to_signals.py" \
        --input "$input_file" \
        --output "$output_file" \
        --format csv \
        --decode \
        ${MASK:+--mask "$MASK"}
    
    if [ $? -eq 0 ]; then
        log_info "Signals extracted: $output_file"
    else
        log_error "Failed to extract signals"
        exit 1
    fi
}

# Verify outputs against SHA256 checksums
verify_outputs() {
    if [ "$VERIFY_SHA256" != "true" ]; then
        log_warn "SHA256 verification skipped (set VERIFY_SHA256=true to enable)"
        return 0
    fi
    
    log_info "Verifying outputs against SHA256 checksums..."
    
    local sha256_file="$BUNDLE_DIR/sample_2024-05-13/SHA256SUMS"
    
    if [ ! -f "$sha256_file" ]; then
        log_warn "SHA256SUMS file not found: $sha256_file"
        return 0
    fi
    
    local errors=0
    while IFS= read -r line; do
        if [ -z "$line" ] || [[ "$line" =~ ^# ]]; then
            continue
        fi
        
        local expected_hash=$(echo "$line" | cut -d' ' -f1)
        local file_path=$(echo "$line" | cut -d' ' -f2-)
        
        # Resolve relative paths
        if [[ "$file_path" != /* ]]; then
            file_path="$BUNDLE_DIR/$file_path"
        fi
        
        if ! verify_sha256 "$file_path" "$expected_hash"; then
            errors=$((errors + 1))
        fi
    done < "$sha256_file"
    
    if [ $errors -eq 0 ]; then
        log_info "All SHA256 checksums verified"
        return 0
    else
        log_error "$errors SHA256 verification(s) failed"
        return 1
    fi
}

# Main execution
main() {
    log_info "Power Track Pipeline Verification"
    log_info "=================================="
    log_info "Input:  $INPUT_DIR"
    log_info "Output: $OUTPUT_DIR"
    log_info "Verify SHA256: $VERIFY_SHA256"
    
    check_dependencies
    process_raw_to_frames
    process_frames_to_signals
    
    if [ "$VERIFY_SHA256" = "true" ]; then
        verify_outputs
    fi
    
    log_info "Pipeline verification complete"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --input)
            INPUT_DIR="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --verify-sha256)
            VERIFY_SHA256="true"
            shift
            ;;
        --mask)
            MASK="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --input DIR          Input directory (default: sample_2024-05-13/raw_ticks)"
            echo "  --output DIR         Output directory (default: output/)"
            echo "  --verify-sha256      Verify outputs against SHA256 checksums"
            echo "  --mask HEX           XOR mask to use (e.g., 0x07)"
            echo "  --help               Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Run main function
main


