#!/bin/bash
set -e

# May 13
echo "Processing 2024-05-13..."
python3 research/phase57_detection_stack/detection_harness.py --ticker GME --date 2024-05-13 --extended --output research/phase57_detection_stack/GME_2024-05-13_patch2.json
python3 research/phase58_atlas_and_scoring/score_report.py --report research/phase57_detection_stack/GME_2024-05-13_patch2.json --output research/phase57_detection_stack/GME_2024-05-13_patch2_scored.json
python3 research/phase72_rega/classify_window.py research/phase57_detection_stack/GME_2024-05-13_patch2_scored.json > research/phase57_detection_stack/GME_2024-05-13_class.txt

# May 14
echo "Processing 2024-05-14..."
python3 research/phase57_detection_stack/detection_harness.py --ticker GME --date 2024-05-14 --extended --output research/phase57_detection_stack/GME_2024-05-14_patch2.json
python3 research/phase58_atlas_and_scoring/score_report.py --report research/phase57_detection_stack/GME_2024-05-14_patch2.json --output research/phase57_detection_stack/GME_2024-05-14_patch2_scored.json
python3 research/phase72_rega/classify_window.py research/phase57_detection_stack/GME_2024-05-14_patch2_scored.json > research/phase57_detection_stack/GME_2024-05-14_class.txt

# May 15
echo "Processing 2024-05-15..."
python3 research/phase57_detection_stack/detection_harness.py --ticker GME --date 2024-05-15 --extended --output research/phase57_detection_stack/GME_2024-05-15_patch2.json
python3 research/phase58_atlas_and_scoring/score_report.py --report research/phase57_detection_stack/GME_2024-05-15_patch2.json --output research/phase57_detection_stack/GME_2024-05-15_patch2_scored.json
python3 research/phase72_rega/classify_window.py research/phase57_detection_stack/GME_2024-05-15_patch2_scored.json > research/phase57_detection_stack/GME_2024-05-15_class.txt

# May 16
echo "Processing 2024-05-16..."
python3 research/phase57_detection_stack/detection_harness.py --ticker GME --date 2024-05-16 --extended --output research/phase57_detection_stack/GME_2024-05-16_patch2.json
python3 research/phase58_atlas_and_scoring/score_report.py --report research/phase57_detection_stack/GME_2024-05-16_patch2.json --output research/phase57_detection_stack/GME_2024-05-16_patch2_scored.json
python3 research/phase72_rega/classify_window.py research/phase57_detection_stack/GME_2024-05-16_patch2_scored.json > research/phase57_detection_stack/GME_2024-05-16_class.txt

# May 17
echo "Processing 2024-05-17..."
python3 research/phase57_detection_stack/detection_harness.py --ticker GME --date 2024-05-17 --extended --output research/phase57_detection_stack/GME_2024-05-17_patch2.json
python3 research/phase58_atlas_and_scoring/score_report.py --report research/phase57_detection_stack/GME_2024-05-17_patch2.json --output research/phase57_detection_stack/GME_2024-05-17_patch2_scored.json
python3 research/phase72_rega/classify_window.py research/phase57_detection_stack/GME_2024-05-17_patch2_scored.json > research/phase57_detection_stack/GME_2024-05-17_class.txt

echo "Batch Complete"
