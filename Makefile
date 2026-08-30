VENV ?= $(CURDIR)/.venv
PYTHON ?= $(shell if [ -f $(VENV)/bin/python3.12 ]; then echo $(VENV)/bin/python3.12; elif [ -f $(VENV)/bin/python ]; then echo $(VENV)/bin/python; else command -v python3 2>/dev/null; fi)
PYTEST ?= $(shell if [ -f $(VENV)/bin/pytest ]; then echo $(VENV)/bin/pytest; else command -v pytest 2>/dev/null; fi)
RUFF ?= $(shell if [ -f $(VENV)/bin/ruff ]; then echo $(VENV)/bin/ruff; else command -v ruff 2>/dev/null; fi)

.PHONY: test test-engine test-contribution test-tax test-golden test-demo-fixture lint fmt install dev seed-demo install-hooks

# Runtime code lives under trackr-backend/app/ (see docs/structure_revamp_plan.md).
# trackr-backend is installed editable into the same venv as this root package's dev
# tools, so `app.*` resolves from anywhere without a PYTHONPATH hack, and `pytest
# tests/` (still run from the repo root) imports it exactly like any other dependency.
install:
	pip install -e ".[dev]"
	pip install -e "trackr-backend[dev]"

test: test-engine test-contribution test-tax test-golden test-demo-fixture lint

test-engine:          ## hand-computed cases from ENGINE_SPEC.md
	$(PYTEST) tests/test_engine_cases.py -v

test-contribution:    ## per-open-question assertions for ENGINE_SPEC.md section 10
	$(PYTEST) tests/test_contribution.py -v

test-tax:              ## Phase 3 tax engine -- hand-computed cases, docs/TAX_ENGINE.md
	$(PYTEST) tests/test_tax_classification.py tests/test_grandfathering.py \
	       tests/test_indexation.py tests/test_demerger.py tests/test_schedule_112a.py \
	       tests/test_itr_capital_gains.py tests/test_cii_source.py \
	       tests/test_fmv_31jan2018_source.py tests/test_market_cap_sources.py \
	       tests/test_import_staging.py -v

test-golden:          ## the real 324-trade portfolio
	$(PYTEST) tests/test_golden_portfolio.py -v

test-demo-fixture:    ## fixtures/demo_portfolio.json replayed through the real engine
	$(PYTEST) tests/test_demo_fixture.py -v

lint:                 ## the architecture rules, enforced
	@echo "checking: no float in app/engine/"
	@! grep -rn "float(" trackr-backend/app/engine/ --include="*.py" || (echo "FAIL: float in engine" && exit 1)
	@echo "checking: engine does not import ingest, auth, routers, schemas or db"
	@! grep -rnE "^[[:space:]]*(from|import) app\.(ingest|db|storage|prices|auth|routers|schemas)\b" trackr-backend/app/engine/ --include="*.py" || (echo "FAIL: layer violation" && exit 1)
	@echo "checking: no credential storage"
# NARROW, NAMED EXCEPTION: app/ingest/gmail_oauth.py only. That module handles a
# revocable, Google-mediated OAuth grant over the DEVELOPER'S OWN mailbox - read-only, no
# trading capability, cannot move money, revocable from a Google settings page at any
# time. It is categorically not a stored broker API secret, which is what this rule
# exists to keep out and what the no-FIU-registration position depends on. The exception
# is per-file on purpose: every other file in the repo, including any future adapter and
# the new app/auth/ session table, stays covered -- app_session stores a HASH
# (session_token_hash), never a token, precisely so it never matches this ban either.
	@! grep -rniE "broker_password|api_secret|access_token|otp_secret|encrypted_token|refresh_token|broker_api_credential" --include="*.py" --include="*.sql" --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=.next --exclude=gmail_oauth.py . || (echo "FAIL: credential storage" && exit 1)
# Same allowlist as .gitignore's own `!fixtures/...` exceptions and scripts/pre-commit's
# $$allowed_regex -- keep all three in sync. Catches the docs/Docs copy.zip class of bug:
# a client-document-shaped file that is tracked, OR untracked but not actually matched
# by any .gitignore rule (an extension the *.pdf/*.xlsx/*.xls/*.csv rule doesn't cover).
	@echo "checking: no un-ignored client documents anywhere in the working tree"
	@bad=$$(git ls-files --cached --others --exclude-standard -- '*.pdf' '*.xlsx' '*.xls' '*.csv' '*.zip' 2>/dev/null | grep -vE '^fixtures/(engine_cases\.json|bhavcopy/.*\.csv|nse_sector_sample\.csv|amfi_market_cap_sample\.xlsx)$$' || true); \
	if [ -n "$$bad" ]; then echo "FAIL: client-document-shaped file(s) not covered by .gitignore:"; echo "$$bad"; exit 1; fi
	$(RUFF) check .

fmt:
	$(RUFF) format .

dev:
	cd trackr-backend && uvicorn app.main:app --reload

seed-demo:            ## realistic mock portfolio for local dev / screenshots -- idempotent
	cd trackr-backend && export $$(grep -v '^\s*#' .env | grep -v '^\s*$$' | xargs) && $(PYTHON) -m app.db.seed_demo

install-hooks:        ## wires scripts/pre-commit into .git/hooks -- git never clones
	ln -sf ../../scripts/pre-commit .git/hooks/pre-commit
	@echo "installed: .git/hooks/pre-commit -> scripts/pre-commit"
