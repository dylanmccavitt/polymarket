.PHONY: lint typecheck test

PYTHON ?= python3

lint:
	$(PYTHON) -m compileall -q polymarket_paper tests
	$(PYTHON) -m polymarket_paper.guardrails

typecheck:
	$(PYTHON) -m compileall -q polymarket_paper tests

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'
