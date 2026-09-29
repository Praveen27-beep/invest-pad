VENV ?= $(CURDIR)/.venv
PYTHON ?= $(shell if [ -f $(VENV)/bin/python3.12 ]; then echo $(VENV)/bin/python3.12; elif [ -f $(VENV)/bin/python ]; then echo $(VENV)/bin/python; else command -v python3 2>/dev/null; fi)
PYTEST ?= $(shell if [ -f $(VENV)/bin/pytest ]; then echo $(VENV)/bin/pytest; else command -v pytest 2>/dev/null; fi)
RUFF ?= $(shell if [ -f $(VENV)/bin/ruff ]; then echo $(VENV)/bin/ruff; else command -v ruff 2>/dev/null; fi)

.PHONY: test test-engine test-contribution test-tax test-golden test-demo-fixture test-analytics test-narrative lint fmt install dev seed-demo install-hooks approve-research-policy research-policy-status

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

# REMOVED 2026-09-24: `test-analytics` and `test-narrative` named seven test files that
# were never written. `git log --all -- 'tests/test_analytics*' 'tests/test_narrative*'`
# is empty on every branch, and none are on disk. Both targets were added by 8066d8c --
# the targets landed, the tests did not -- so `make test` has aborted at test-analytics
# ever since, which means the acceptance gate this Makefile documents has not run since
# that commit.
#
# THE GAP THEY WERE MEANT TO CLOSE IS REAL AND STILL OPEN. Nothing under tests/ imports
# app.analytics (7 modules, including verdict.py, whose own docstring calls it "THE
# HIGHEST-RISK COMPONENT") or app.narrative (13 modules, including verify.py, the check
# that stops a generated sentence inventing a figure). Removing these targets is what
# makes the gate runnable again; it is NOT what makes those modules tested. Restore a
# target here when the tests behind it actually exist -- not before.

lint:                 ## the architecture rules, enforced
	@echo "checking: no float in app/engine/"
	@! grep -rn "float(" trackr-backend/app/engine/ --include="*.py" || (echo "FAIL: float in engine" && exit 1)
	@echo "checking: engine does not import ingest, auth, routers, schemas or db"
	@! grep -rnE "^[[:space:]]*(from|import) app\.(ingest|db|storage|prices|auth|routers|schemas)\b" trackr-backend/app/engine/ --include="*.py" || (echo "FAIL: layer violation" && exit 1)
	@echo "checking: analytics layer does not import db, routers, ingest or a framework"
	@! grep -rnE "^[[:space:]]*(from|import) (app\.(db|routers|ingest|schemas|auth|storage)|fastapi|pydantic)\b" trackr-backend/app/analytics/ --include="*.py" || (echo "FAIL: analytics layer violation" && exit 1)
	@echo "checking: narrative layer does not import db, routers, ingest or a framework"
	@! grep -rnE "^[[:space:]]*(from|import) (app\.(db|routers|ingest|schemas|auth|storage)|fastapi|pydantic)\b" trackr-backend/app/narrative/ --include="*.py" || (echo "FAIL: narrative layer violation" && exit 1)
# THE HALF THAT DECIDES WHAT IS TRUE MUST NOT BE ABLE TO CALL A NETWORK. Same split as
# app/ingest/llm_extract.py (prompts, talks to a model) versus app/ingest/llm_verify.py
# (proves, no network, no model) -- and the reason that split is what makes an LLM
# feature trustworthy here at all. app/narrative/client.py is the one named exception,
# exactly as gmail_oauth.py is for the credential rule above: it is the only file
# permitted to reach a provider, so every verifier and renderer beside it is physically
# incapable of doing so rather than merely not doing so today.
	@echo "checking: only app/narrative/client.py may reach a model"
	@! grep -rnE "^[[:space:]]*(from|import) app\.ai\b" trackr-backend/app/narrative/ --include="*.py" --exclude=client.py || (echo "FAIL: narrative must not import app.ai outside client.py" && exit 1)
# BE 18/21: the research context builder, read tools and proposal guardrails decide what a
# model is shown and whether its output is recorded. None may hold a float, issue a SQL
# mutation or reach a model/provider: they read, compute and judge, and nothing else.
	@echo "checking: research context/tools/guardrails -- no float, no SQL mutation, no model"
	@! grep -nE "float\(|: float|-> float" trackr-backend/app/research/context.py trackr-backend/app/research/tools.py trackr-backend/app/research/guardrails.py || (echo "FAIL: float in research boundary" && exit 1)
	@! grep -niE "\b(INSERT[[:space:]]+INTO|UPDATE[[:space:]]+[a-z_]+[[:space:]]+SET|DELETE[[:space:]]+FROM|TRUNCATE)\b" trackr-backend/app/research/context.py trackr-backend/app/research/tools.py trackr-backend/app/research/guardrails.py || (echo "FAIL: SQL mutation in research boundary" && exit 1)
	@! grep -nE "^[[:space:]]*(from|import) (app\.(ai|narrative|ingest)|anthropic|openai|google\.generativeai|httpx|requests)\b" trackr-backend/app/research/context.py trackr-backend/app/research/tools.py trackr-backend/app/research/guardrails.py || (echo "FAIL: model or network import in research boundary" && exit 1)
# BT-P02 (RP 01): the operator's platform inference credential is named in exactly two files --
# app/config.py (where the runtime environment is read) and app/research/platform_inference.py
# (the only module that uses it, inside the worker). Narrow on purpose: this ADDS a rule rather
# than relaxing the credential ban below, which still refuses broker/API secrets everywhere.
	@echo "checking: platform inference credential confined to config + adapter"
	@! grep -rn "platform_inference_key" trackr-backend/app --include="*.py" | grep -vE "^trackr-backend/app/(config\.py|research/platform_inference\.py):" || (echo "FAIL: platform credential referenced outside its two authorised files" && exit 1)
# BUTLER_INVESTOR_MEMORY s.7 / BUTLER_REPORTS s.9: no report module may reach the investor
# notebook. The hosted worker imports reflection lazily, inside its reflection branch only.
	@echo "checking: report path does not import investor-notebook code"
	@! grep -nE "^[[:space:]]*(from|import) app\.(db\.butler_notebook|db\.butler_episodes|research\.butler_notebook_policy|research\.butler_episodes|research\.butler_reflection|schemas\.butler_notebook)\b|from app\.(db|research|schemas) import .*\b(butler_notebook|butler_episodes|butler_reflection|butler_notebook_policy)\b" trackr-backend/app/research/report_contract.py trackr-backend/app/research/report_corpus.py trackr-backend/app/routers/reports.py trackr-backend/app/schemas/reports.py trackr-backend/app/db/hosted_jobs.py || (echo "FAIL: report path imports notebook code" && exit 1)
	@echo "checking: Trackr+ ships no notebook client"
	@! grep -rnE "butler/notebook|Understanding you" trackr-frontend/app trackr-frontend/lib packages --include="*.ts" --include="*.tsx" 2>/dev/null || (echo "FAIL: notebook code in the Plus app or shared packages" && exit 1)
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
# An ad hoc script must not be able to inherit the real database. The incident class is
# written up in app/db/scratch.py's docstring: a one-off probe imports the same connect()
# the application uses, gets DATABASE_URL, and the only thing between a read-only script
# and a destructive one is that whoever typed it did not make a mistake. That module is
# the runtime guard for a script that ASKS for a disposable connection; this rule is for
# the script that does not ask, and it works by refusing to let one into the repo.
# NAMED EXCEPTION: scripts/check_migration_drift.py, whose whole job is to inspect the
# configured real database. It is read-only, and it is the one file reviewed as such.
	@echo "checking: no ad hoc script opens its own database connection"
	@bad=$$(git ls-files '*.py' \
		| grep -v '^trackr-backend/app/' \
		| grep -v '^tests/' \
		| grep -v '^scripts/check_migration_drift\.py$$' \
		| xargs -r grep -lE 'psycopg\.connect|connection\.connect|database_url\(\)' || true); \
	if [ -n "$$bad" ]; then \
		echo "FAIL: script(s) open a database connection directly. Use"; \
		echo "      app.db.scratch.connect_scratch, which refuses anything but a tagged"; \
		echo "      disposable database, instead of inheriting DATABASE_URL:"; \
		echo "$$bad"; exit 1; fi
# The one check here that looks at a REAL database's state rather than at source text --
# see app.db.migrate.check_drift and scripts/check_migration_drift.py for why this exists:
# six migrations sat fully tested while a real local database silently stayed six
# versions behind, because the test suite migrates its own throwaway cluster
# automatically and this was the one comparison nothing else ever made. Skips cleanly
# (exit 0) when trackr-backend/.env has no DATABASE_URL or it is unreachable -- same
# posture as the Postgres-backed test suite skipping when initdb/pg_ctl are absent -- and
# fails loudly when a real, reachable database is missing a migration that exists on disk.
	@echo "checking: schema migrations match the configured database"
# Only DATABASE_URL is read across, and it is extracted rather than exported wholesale.
# `export $$(... | xargs)` died on the FIRST .env value containing a space or a '#' --
# it splits mid-value and hands sh a syntax error, which killed the entire gate with no
# output at all. One mistyped key in a local, gitignored file must not be able to
# silently disable an architecture check for everyone.
	@DATABASE_URL="$$(sed -n 's/^DATABASE_URL=//p' trackr-backend/.env 2>/dev/null | head -1)" \
		$(PYTHON) scripts/check_migration_drift.py
	$(RUFF) check .

approve-research-policy: ## owner: approve BE-Q04 source rights + BE-Q05 retention draft in one step
	@test -n "$(BY)" || (echo 'usage: make approve-research-policy BY="Owner Name"' && exit 2)
	cd trackr-backend && ../.venv/bin/python -m app.research.policy_approval approve --by "$(BY)"

research-policy-status: ## APPROVED | NOT_APPROVED | STALE for the drafted research policy
	cd trackr-backend && ../.venv/bin/python -m app.research.policy_approval status

fmt:
	$(RUFF) format .

dev:
	cd trackr-backend && uvicorn app.main:app --reload

seed-demo:            ## realistic mock portfolio for local dev / screenshots -- idempotent
	cd trackr-backend && export $$(grep -v '^\s*#' .env | grep -v '^\s*$$' | xargs) && $(PYTHON) -m app.db.seed_demo

install-hooks:        ## wires scripts/pre-commit into .git/hooks -- git never clones
	ln -sf ../../scripts/pre-commit .git/hooks/pre-commit
	@echo "installed: .git/hooks/pre-commit -> scripts/pre-commit"
