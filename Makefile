# Python interpreter: the project's virtualenv if it exists, otherwise python3.
# Override any time:  make test PYTHON=/path/to/python
PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else command -v python3 || command -v python; fi)

.PHONY: venv install api web dev doctor test check api-docs run docker purge

venv:               ## create .venv (run once) — then `make install`
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip

install:            ## backend + frontend dependencies
	$(PYTHON) -m pip install -r requirements-dev.txt
	cd frontend && npm install

api:                ## Flask API with auto-reload on :5001 (not 5000: macOS AirPlay Receiver owns 5000 and answers 403)
	REPLY_DELAYS_ENABLED=false $(PYTHON) -m flask --app wsgi run --debug --port 5001

web:                ## Vue dev server on :5173 (proxies /api to :5001)
	cd frontend && npm run dev

dev:                ## both, in one terminal (Ctrl-C stops both)
	$(MAKE) -j2 api web

doctor:             ## check API, web, proxy, database, AI model and WhatsApp setup; prints how to fix (run while `make dev` runs)
	$(PYTHON) scripts/doctor.py

test:               ## backend tests + frontend static checks
	$(PYTHON) -m pytest -q tests
	$(PYTHON) frontend/scripts/check.py

api-docs:           ## regenerate docs/API_BACKEND.md, docs/openapi.json, docs/API_FRONTEND.md from the code
	$(PYTHON) scripts/gen_api_docs.py

check:              ## real frontend compile check (needs npm install)
	cd frontend && npm run build

run:                ## production-style API on :8000
	$(PYTHON) -m gunicorn wsgi:app --bind 0.0.0.0:8000 --workers 1 --threads 16 --timeout 120

docker:             ## build and start with Docker (needs .env: scripts/init-env.sh your.domain)
	docker compose up -d --build

purge:              ## apply data-retention settings (run nightly from cron)
	$(PYTHON) -m flask --app wsgi purge
