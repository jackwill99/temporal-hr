import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from .adk_tools import run_adk_pipeline
from .config import GEMINI_MODEL, GOOGLE_API_KEY

logger = logging.getLogger(__name__)
KEYWORDS = ["react", "node"]


def _extract_pdf_text(file_path: Optional[Path]) -> str:
    if not file_path:
        return ""
    try:
        from pypdf import PdfReader
    except Exception as exc: 
        logger.warning("pypdf not available for %s (%s)", file_path, exc)
        return ""

    try:
        reader = PdfReader(str(file_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except Exception as exc:  
        logger.warning("Failed to extract PDF text from %s (%s)", file_path, exc)
        return ""


def _parse_json_response(raw: str) -> Optional[Dict]:
    raw = raw.strip()
    raw = raw.strip("` \n")
    if raw.lower().startswith("json"):
        raw = raw[4:].strip()

    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def _call_gemini(prompt: str) -> Optional[Dict]:
    try:
        import google.generativeai as genai
    except Exception as exc:
        logger.error("google-generativeai not installed or failed to import: %s", exc)
        return None

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        instructions = (
            "You are screening candidates for a Senior Full-Stack Developer role. Overall 3 years of experience can be assumed for the senior level candidate."
            "Decide if the applicant is senior-level and explicitly mentions React, Node.js. "
            "Respond with compact JSON: "
            '{"qualifies":true|false,"reason":"string","missing_keywords":["react","node"]}'
        )
        response = model.generate_content(
            [
                instructions,
                f"Application materials:\n{prompt}",
            ]
        )
        raw = response.text.strip() if response and response.text else ""
        parsed = _parse_json_response(raw)
        if not parsed:
            logger.error("Gemini response not JSON parseable: %s", raw[:200])
            return None
        parsed["used_gemini"] = True
        return parsed
    except Exception as exc:  # noqa: BLE001 - best effort
        logger.error("Gemini call failed (model=%s): %s", GEMINI_MODEL, exc)
        return None


def _keyword_screen(text_blob: str, file_path: Optional[Path]) -> Dict:
    lowered = text_blob.lower()
    missing_keywords: List[str] = [kw for kw in KEYWORDS if kw not in lowered]
    senior_signal = "senior" in lowered or "sr" in lowered
    qualifies = senior_signal and not missing_keywords
    reason = (
        "Matches senior full-stack criteria with React, Node.js."
        if qualifies
        else "Missing senior signal or required keywords."
    )
    return {
        "qualifies": qualifies,
        "reason": reason,
        "missing_keywords": missing_keywords,
        "used_gemini": False,
        "file_path": str(file_path) if file_path else "",
    }


async def analyze_application(email: str, title: str, description: str, file_path: Optional[Path]) -> Dict:
    pdf_text = _extract_pdf_text(file_path)
    combined = "\n".join([title, description, pdf_text])

    if GOOGLE_API_KEY:
        try:
            adk_result = await run_adk_pipeline(
                application_id=email,
                email=email,
                title=title,
                description=description,
                resume_path=str(file_path) if file_path else None,
            )
            if adk_result:
                adk_result["file_path"] = str(file_path) if file_path else ""
                return adk_result
        except Exception as exc:  # noqa: BLE001
            logger.error("ADK screening failed so genai will be used: %s", exc)

        gemini_result = await asyncio.to_thread(_call_gemini, combined)
        if gemini_result:
            gemini_result["file_path"] = str(file_path)
            return gemini_result
        logger.warning("Falling back to keyword screen because Gemini returned no result.")

    return _keyword_screen(combined, file_path)
