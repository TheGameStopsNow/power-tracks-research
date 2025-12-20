import json
from pathlib import Path


def load_notebook(path: Path):
    return json.loads(path.read_text())


def test_notebook_status_headers():
    repo = Path(__file__).resolve().parents[1]
    targets = [
        repo / "getting-started" / "01_magic_demo.ipynb",
        repo / "labs" / "00_packet_analysis.ipynb",
        repo / "labs" / "01_spectral_primer.ipynb",
    ]
    for nb_path in targets:
        nb = load_notebook(nb_path)
        assert "cells" in nb and len(nb["cells"]) > 0
        header = "".join(nb["cells"][0].get("source", []))
        assert "STATUS" in header
        assert nb.get("metadata", {}).get("status") in {"ready", "draft", "archive"}
