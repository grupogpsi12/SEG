# Windows (el equipo) y Linux (CI): el venv guarda los ejecutables en carpetas distintas.
ifeq ($(OS),Windows_NT)
BIN ?= .venv/Scripts
else
BIN ?= .venv/bin
endif
PY ?= $(BIN)/python
.PHONY: verificar mutacion
# Compuertas del nucleo (Fase 1, item 1.13): estilo, tipos estrictos, capas, pruebas y
# cobertura de ramas por capa (dominio >= 95 %, aplicacion >= 90 %).
verificar:
	$(PY) -m ruff check .
	$(PY) -m mypy
	$(BIN)/lint-imports
	$(PY) -m pytest -q --cov=jml --cov-branch tests/dominio tests/aplicacion tests/contratos tests/escenarios tests/adaptadores tests/seguridad
	$(PY) -m coverage report --include="src/jml/dominio/*" --fail-under=95
	$(PY) -m coverage report --include="src/jml/aplicacion/*" --fail-under=90
# Lento. NO editar src/ ni correr pruebas mientras corre: mutmut modifica los archivos en su sitio.
# En Windows usa mutmut 2.x (mutmut 3 necesita fork). Ver docs/spikes/mutacion.md.
mutacion:
	HYPOTHESIS_PROFILE=mutacion PYTHONUTF8=1 $(PY) -m coverage run --branch -m pytest tests/dominio -q -p no:cacheprovider
	HYPOTHESIS_PROFILE=mutacion PYTHONUTF8=1 $(PY) -m mutmut run --use-coverage --simple-output
