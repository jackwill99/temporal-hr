# Temporal testing

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Temporal locally
temporal server start-dev

# worker
python -m app.worker

# API
uvicorn app.main:app --reload --port 8000

# scheduler
cd backend
source .venv/bin/activate
python -m app.scheduler

# frontend (root dir)
python -m http.server 5173 -d frontend

```
