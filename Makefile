.PHONY: up down logs api worker remotion seed gen test-comfy

up:            ## start full stack
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f worker

## --- local dev (no docker) ---
api:
	cd apps/api && uvicorn app.main:app --reload --port 8000

worker:
	cd apps/api && arq app.workers.tasks.WorkerSettings

remotion:
	cd apps/remotion && npm run server

## --- REAL short via Claude Director on your MAX plan (topic -> mp4) ---
gen-real:
	.venv/bin/python make_gen.py "$(T)"          # make gen-real T="Why inflation is back"

## --- offline end-to-end, ZERO paid keys (mock director, local tts, ffmpeg render) ---
smoke:
	cd apps/api && DIRECTOR_MODE=mock python ../../scripts/smoke.py

## --- smoke test: one finance short (needs API + running stack) ---
gen:
	curl -s localhost:8000/generate -H 'content-type: application/json' \
	  -d '{"channel_id":"usa_finance","niche":"usa_finance","topic":"why CPI came in hot this month"}' | jq

batch:
	curl -s localhost:8000/generate/batch -H 'content-type: application/json' \
	  -d '{"channel_id":"usa_election","niche":"usa_election","count":5}' | jq

## --- remote ComfyUI: generate a sample image on the Colab GPU ---
test-comfy:
	.venv/bin/python scripts/test_remote_comfy.py "cinematic dramatic documentary scene, ultra realistic"
