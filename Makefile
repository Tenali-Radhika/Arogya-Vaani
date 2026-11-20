# ArogyaVaani: handy targets (Linux/macOS/AWS; on Windows use `bun run test` / `bun run dev`)
PY ?= server/venv/bin/python
test:            ## backend tests
	cd server && $(PY:server/%=%) -m pytest -q
demo-reset:      ## seed doctors + Lakshmi profile, clear bookings (server must be running)
	curl -s -X POST http://127.0.0.1:8000/demo/reset
run:
	cd server/src && ../$(PY:server/%=%) server.py
.PHONY: test demo-reset run
