# Convenience targets for ARIA developers.
#
# Run `make help` for a list of targets.

PY ?= python
PYTEST ?= $(PY) -m pytest

.PHONY: help test fast slow lint type screen advisor cfs-test smoke clean production-validate production-validate-quick

help:
	@echo "ARIA developer Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  make test          run the fast unit + integration suite"
	@echo "  make fast          alias for make test"
	@echo "  make slow          run the slow / non-core test markers"
	@echo "  make smoke         run only R43-R47 integration tests (~3 s)"
	@echo "  make production-validate  run all replay validators (Apollo, Saturn V, Artemis 2, Iridium-Cosmos, Soyuz, historical conjunctions); single PASS/FAIL gate"
	@echo "  make production-validate-quick  same but skips Soyuz + historical-conjunctions (fast subset)"
	@echo "  make lint          ruff check . (if ruff installed)"
	@echo "  make type          mypy on aria.products + aria.security"
	@echo "  make screen        run the conjunction screener locally"
	@echo "  make advisor       run the cubesat advisor service locally"
	@echo "  make cfs-test      run the cFS bridge equivalence suite"
	@echo "  make clean         remove __pycache__, .pytest_cache, build/"

test fast:
	$(PYTEST) -m "not slow and not noncore" -q

slow:
	$(PYTEST) -m "slow or noncore" -q

smoke:
	$(PYTEST) tests/integration/test_apollo_replay.py \
	          tests/integration/test_iridium_cosmos_replay.py \
	          tests/integration/test_iridium_authentic_tles.py \
	          tests/integration/test_cubesat_deorbit_advisor.py \
	          tests/integration/test_cubesat_advisor_extras.py \
	          tests/integration/test_cfs_bridge_equivalence.py \
	          tests/integration/test_conjunction_screener_service.py \
	          tests/integration/test_screener_tenant_store.py \
	          tests/integration/test_screener_admin_endpoints.py \
	          tests/integration/test_artemis2_replay.py \
	          tests/integration/test_historical_conjunctions.py \
	          -q

lint:
	@if command -v ruff >/dev/null 2>&1 ; then \
	    ruff check . ; \
	else \
	    echo "ruff not installed — pip install ruff" ; exit 1 ; \
	fi

type:
	@if command -v mypy >/dev/null 2>&1 ; then \
	    mypy src/aria/products src/aria/security ; \
	else \
	    echo "mypy not installed — pip install mypy" ; exit 1 ; \
	fi

screen:
	$(PY) -m aria.products.conjunction_screener serve --host 127.0.0.1 --port 8443

advisor:
	$(PY) -m aria.products.cubesat_deorbit serve --host 127.0.0.1 --port 8444

cfs-test:
	$(PYTEST) tests/integration/test_cfs_bridge_equivalence.py -q

production-validate:
	$(PY) -m tools.run_production_validation

production-validate-quick:
	$(PY) -m tools.run_production_validation --quick

clean:
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache build/ dist/ *.egg-info
	@echo "cleaned"
