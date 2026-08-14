.PHONY: test test-engine test-golden lint fmt install dev

install:
	pip install -e ".[dev]"

test: test-engine test-golden lint

test-engine:          ## hand-computed cases from ENGINE_SPEC.md
	pytest tests/test_engine_cases.py -v

test-golden:          ## the real 324-trade portfolio
	pytest tests/test_golden_portfolio.py -v

lint:                 ## the architecture rules, enforced
	@echo "checking: no float in engine/"
	@! grep -rn "float(" engine/ --include="*.py" || (echo "FAIL: float in engine" && exit 1)
	@echo "checking: engine does not import ingest, api or db"
	@! grep -rnE "^[[:space:]]*(from|import) (ingestion|ingest|api|db|storage|prices)\b" engine/ --include="*.py" || (echo "FAIL: layer violation" && exit 1)
	@echo "checking: no credential storage"
# NARROW, NAMED EXCEPTION: ingest/gmail_oauth.py only. That module handles a revocable,
# Google-mediated OAuth grant over the DEVELOPER'S OWN mailbox - read-only, no trading
# capability, cannot move money, revocable from a Google settings page at any time. It is
# categorically not a stored broker API secret, which is what this rule exists to keep out
# and what the no-FIU-registration position depends on. The exception is per-file on
# purpose: every other file in the repo, including any future adapter, stays covered.
	@! grep -rniE "broker_password|api_secret|access_token|otp_secret|encrypted_token|refresh_token|broker_api_credential" --include="*.py" --include="*.sql" --exclude-dir=.venv --exclude=gmail_oauth.py . || (echo "FAIL: credential storage" && exit 1)
	ruff check .

fmt:
	ruff format .

dev:
	uvicorn api.main:app --reload
