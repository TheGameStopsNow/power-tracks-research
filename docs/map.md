# Repository Map

```mermaid
graph TD
    Root[Repo Root] --> Start[getting-started/]
    Root --> Labs[labs/]
    Root --> Pipelines[pipelines/]
    Root --> Artifacts[artifacts/]
    Root --> Data[data/]
    Root --> Docs[docs/]
    Root --> Tests[tests/]
    Docs --> Troubleshooting[troubleshooting.md]
    Docs --> Walkthrough[walkthrough.md]

    Start --> DemoCLI[00_magic_demo.py]
    Start --> DemoNB[01_magic_demo.ipynb]

    Labs --> Lab00[00_packet_analysis.ipynb]
    Labs --> Lab01[01_spectral_primer.ipynb]

    Pipelines --> P00[00_signal_integrity]
    Pipelines --> P01[01_selectivity]
    Pipelines --> P02[02_clusters_gating]

    Artifacts --> Latest[latest/]
    Artifacts --> V1[v20240513/]

    Data --> Raw[raw/]
    Data --> Samples[samples/]
    Samples --> Micro[micro/]

    Tests --> DemoTest[test_magic_demo.py]
```

## Directory Guide

### 🟢 Start Here
-   **`getting-started/`**: The entry point. Run the magic demo to see the engine in action.

### 🟡 Learn
-   **`labs/`**: Interactive notebooks to learn the concepts step-by-step.

### 🔴 Research
-   **`pipelines/`**: The core research suites. Use `pipelines/run_suite.py` or `make suite-<name>` to invoke (falls back to legacy scripts if present).

### 🔵 Resources
-   **`artifacts/`**: Validated outputs (cluster centroids, templates).
-   **`data/`**: The data library.
-   **`docs/`**: Manuals and specifications (see `troubleshooting.md` for common fixes).
-   **`tests/`**: Smoke tests (demo, pipelines once added).
