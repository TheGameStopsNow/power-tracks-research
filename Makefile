.PHONY: help demo lab-00 install data test clean env

SAMPLE ?= $(POWER_TRACKS_PRICE_PATHS)
ROWS ?= $(POWER_TRACKS_SAMPLE_ROWS)
SYMBOL ?= GME
DATE ?= 2024-05-13
OUT ?= data/samples/local/$(shell echo $(SYMBOL) | tr A-Z a-z)_$(shell echo $(DATE) | tr -d -)/price_paths.csv
MICRO_SOURCE ?= data/samples/local/$(shell echo $(SYMBOL) | tr A-Z a-z)_$(shell echo $(DATE) | tr -d -)/price_paths.csv
MICRO_OUT ?= data/samples/micro/price_paths.csv

help:
	@echo "Power Tracks Research Platform"
	@echo "------------------------------"
	@echo "make install              - Install dependencies (python + notebooks)"
	@echo "make data SYMBOL=GME DATE=2024-05-13 - Fetch tiny sample via Polygon/Massive (writes to data/samples/local/..., git-ignored)"
	@echo "make micro-sample         - Trim committed sample into a tiny micro slice for demos/tests (safe to commit)"
	@echo "make demo                 - Run the Magic Demo (real sample data, PNG output)"
	@echo "make suite-<name>         - Run a research suite via pipelines/run_suite.py (selectivity|clusters|gating|portability|temporal|options|risk)"
	@echo "make lab-00               - Open the Packet Analysis Lab notebook"
	@echo "make test                 - Run pytest smoke tests"
	@echo "make test-nbval           - Run nbval on demo + labs (uses micro/local sample)"
	@echo "make publish-artifacts VERSION=vYYYYMMDD SRC=path/to/artifacts - Copy artifacts into versioned folder and refresh latest"
	@echo "make check-size           - Fail if large files are tracked outside allowed dirs"
	@echo "make clean                - Remove temp files"
	@echo "Env: POLYGON_API_KEY, MASSIVE_API_KEY, POWER_TRACKS_PRICE_PATHS, POWER_TRACKS_SAMPLE_ROWS"

install:
	pip install -r requirements.txt

data:
	python3 tools/fetch_samples.py --symbol $(SYMBOL) --date $(DATE) --out $(OUT)

micro-sample:
	python3 tools/build_micro_sample.py --source $(MICRO_SOURCE) --out $(MICRO_OUT)

demo:
	python3 getting-started/00_magic_demo.py --rows $${ROWS:-800}

suite-signal:
	python3 pipelines/run_suite.py signal

suite-selectivity:
	python3 pipelines/run_suite.py selectivity

suite-clusters:
	python3 pipelines/run_suite.py clusters

suite-gating:
	python3 pipelines/run_suite.py gating

suite-portability:
	python3 pipelines/run_suite.py portability

suite-temporal:
	python3 pipelines/run_suite.py temporal

suite-options:
	python3 pipelines/run_suite.py options

suite-risk:
	python3 pipelines/run_suite.py risk

lab-00:
	jupyter notebook labs/00_packet_analysis.ipynb

test:
	pytest

test-nbval:
	pytest --nbval-lax getting-started/01_magic_demo.ipynb labs/00_packet_analysis.ipynb labs/01_spectral_primer.ipynb

publish-artifacts:
	@if [ -z "$(VERSION)" ]; then echo "VERSION is required (e.g., VERSION=v20240513)"; exit 1; fi
	@if [ -z "$(SRC)" ]; then echo "SRC is required (path to artifacts to publish)"; exit 1; fi
	mkdir -p artifacts/$(VERSION)
	cp -R $(SRC)/* artifacts/$(VERSION)/
	rm -f artifacts/latest
	ln -s $(VERSION) artifacts/latest

check-size:
	python tools/check_size.py --limit-mb 5 --root .

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
