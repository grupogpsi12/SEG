PY ?= .venv/Scripts/python.exe
.PHONY: verificar mutacion
verificar:
	$(PY) -m ruff check .
	$(PY) -m mypy
	.venv/Scripts/lint-imports.exe
	$(PY) -m pytest -q --cov=jml --cov-branch --cov-report=term-missing tests/dominio tests/aplicacion tests/contratos tests/escenarios
mutacion:
	$(PY) -m mutmut run
