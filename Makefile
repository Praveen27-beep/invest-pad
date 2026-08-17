.PHONY: test test-engine test-golden test-demo-fixture lint fmt install dev seed-demo

# Runtime code lives under trackr-backend/app/ (see docs/structure_revamp_plan.md).
# trackr-backend is installed editable into the same venv as this root package's dev
# tools, so `app.*` resolves from anywhere without a PYTHONPATH hack, and `pytest
# tests/` (still run from the repo root) imports it exactly like any other dependency.
install:
	pip install -e ".[dev]"
	pip install -e "trackr-backend[dev,db,storage,pdf]"

test: test-engine test-golden test-demo-fixture lint

test-engine:          ## hand-computed cases from ENGINE_SPEC.md
	pytest tests/test_engine_cases.py -v

test-golden:          ## the real 324-trade portfolio
	pytest tests/test_golden_portfolio.py -v

test-demo-fixture:    ## fixtures/demo_portfolio.json replayed through the real engine
	pytest tests/test_demo_fixture.py -v

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
	ruff check .

fmt:
	ruff format .

dev:
	cd trackr-backend && uvicorn app.main:app --reload

seed-demo:            ## realistic mock portfolio for local dev / screenshots -- idempotent
	cd trackr-backend && python -m app.db.seed_demo
