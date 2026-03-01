.PHONY: setup dev test dashboard-setup dashboard

setup:
	cd pipeline && uv venv && uv pip install -e ".[dev]"

dev:
	cd pipeline && uv run uvicorn pipeline.main:app --reload --port 8001

test:
	cd pipeline && uv run pytest -v

dashboard-setup:
	cd dashboard && npm install

dashboard:
	cd dashboard && npm run dev
