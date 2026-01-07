import asyncio
import base64
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import (BackgroundTasks, Body, FastAPI, File, Form, HTTPException,
                     UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from temporalio.client import Client

from .activities import evaluate_application
from .config import TEMPORAL_TARGET, TEMPORAL_TASK_QUEUE, UPLOAD_DIR
from .workflows import ApplicationWorkflow

ALLOWED_CONTENT_TYPES = {"application/pdf"}

app = FastAPI(title="Application Screening API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _save_upload(file: UploadFile) -> Path:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    safe_name = Path(file.filename or "upload.pdf").name
    destination = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"
    content = file.file.read()
    destination.write_bytes(content)
    return destination


async def _trigger_temporal_workflow(payload: dict) -> None:
    try:
        client = await Client.connect(TEMPORAL_TARGET)
        await client.start_workflow(
            ApplicationWorkflow.run,
            payload,
            # id=f"application-{uuid.uuid4().hex}",
            id=f"application-{payload['email']}-{uuid.uuid4().hex}",
            task_queue=TEMPORAL_TASK_QUEUE,
        )
    except Exception as exc:
        print(f"Temporal unavailable ({exc}); running evaluation inline.")
        await evaluate_application(payload)


@app.post("/api/applications")
async def submit_application(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    file: UploadFile = File(...),
):
    stored_path = _save_upload(file)
    payload = {
        "email": email,
        "title": title,
        "description": description,
        "file_path": str(stored_path),
        "source": "web",
    }

    background_tasks.add_task(_trigger_temporal_workflow, payload)

    return {
        "status": "received",
        "file_path": str(stored_path),
        "queued_to_task_queue": TEMPORAL_TASK_QUEUE,
    }


def _extract_gmail_payload(raw: Dict[str, Any]) -> Dict[str, str]:
   
    if "message" in raw and isinstance(raw["message"], dict):
        msg = raw["message"]
        data = msg.get("data")
        if data:
            try:
                decoded = base64.b64decode(data).decode("utf-8")
                try:
                    inner = json.loads(decoded)
                    return _extract_gmail_payload(inner)
                except Exception:
                    return {"email": "", "title": "(no subject)", "description": decoded}
            except Exception:
                pass
        attrs = msg.get("attributes") or {}
        raw = {**raw, **attrs}

    email = raw.get("sender") or raw.get("from") or raw.get("email") or raw.get("address")
    subject = raw.get("subject") or raw.get("title") or raw.get("topic")
    body = raw.get("body") or raw.get("message") or raw.get("text") or raw.get("content")
    return {
        "email": email or "",
        "title": subject or "(no subject)",
        "description": body or "",
    }


@app.post("/webhooks/gmail")
async def gmail_webhook(background_tasks: BackgroundTasks, payload: Dict[str, Any] = Body(...)):
    
    parsed = _extract_gmail_payload(payload)
    if not parsed.get("email"):
        raise HTTPException(status_code=400, detail="Missing sender email in webhook payload.")

    wf_payload: Dict[str, Any] = {
        **parsed,
        "file_path": None,
        "source": "gmail-webhook",
    }
    background_tasks.add_task(_trigger_temporal_workflow, wf_payload)
    return {"status": "received", "queued_to_task_queue": TEMPORAL_TASK_QUEUE}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
