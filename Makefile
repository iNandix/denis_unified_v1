PYTHON ?= python3
PROJECT_ROOT := $(CURDIR)
SANDBOX_PYTHON ?= /tmp/denis_gate_venv/bin/python

.PHONY: help preflight autopoiesis-smoke gate-pentest validate-r1 review-pack checkpoint-r1 phase11-smoke

help:
	@echo "Targets:"
	@echo "  make preflight         -> run phase10 gate preflight"
	@echo "  make autopoiesis-smoke -> run phase4 autopoiesis smoke"
	@echo "  make gate-pentest      -> run phase4 gate pentest (sandbox python)"
	@echo "  make validate-r1       -> run all R1 validations"
	@echo "  make review-pack       -> build sprint_review.json/.md"
	@echo "  make checkpoint-r1     -> validate + review + require GO"
	@echo "  make phase11-smoke     -> run sprint orchestrator smoke"

preflight:
	$(PYTHON) scripts/phase10_gate_preflight.py --out-json phase10_gate_preflight.json

autopoiesis-smoke:
	$(PYTHON) scripts/run_with_project_env.py --env-file .env -- \
		$(PYTHON) scripts/phase4_autopoiesis_smoke.py --out-json phase4_autopoiesis_smoke.json

gate-pentest:
	$(PYTHON) scripts/run_with_project_env.py --env-file .env -- \
		env DENIS_SELF_EXTENSION_SANDBOX_PYTHON="$(SANDBOX_PYTHON)" PYTHONPATH="$(PROJECT_ROOT)/.." \
		$(PYTHON) scripts/phase4_gate_pentest.py --out-json phase10_gate_pentest.json

validate-r1: preflight autopoiesis-smoke gate-pentest

review-pack:
	$(PYTHON) scripts/sprint_review_pack.py \
		--preflight phase10_gate_preflight.json \
		--smoke phase4_autopoiesis_smoke.json \
		--pentest phase10_gate_pentest.json \
		--out-json sprint_review.json \
		--out-md sprint_review.md

checkpoint-r1: validate-r1 review-pack
	$(PYTHON) scripts/sprint_review_pack.py \
		--preflight phase10_gate_preflight.json \
		--smoke phase4_autopoiesis_smoke.json \
		--pentest phase10_gate_pentest.json \
		--out-json sprint_review.json \
		--out-md sprint_review.md \
		--require-go

phase11-smoke:
	$(PYTHON) scripts/run_with_project_env.py --env-file .env -- \
		$(PYTHON) scripts/phase11_sprint_orchestrator_smoke.py \
		--out-json phase11_sprint_orchestrator_smoke.json
