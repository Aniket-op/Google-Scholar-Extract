"""
app.py — Flask REST API for Google Scholar Profile Extractor.

Endpoints:
    POST /api/extract                         → start extraction job
    GET  /api/status/<job_id>                 → poll job status + progress
    GET  /api/result/<job_id>                 → get full structured JSON result
    GET  /api/download/<job_id>/publications_csv   → download publications.csv
    GET  /api/download/<job_id>/profile_csv        → download profile_summary.csv
    GET  /api/download/<job_id>/publications_json  → download publications.json

Run:
    python app.py
"""

import json
import threading
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

from csv_exporter import profile_to_csv, publications_to_csv
from formatter import format_profile, format_publications
from scraper import fetch_profile

# ─── App setup ────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

# Default ScraperAPI key — used automatically if none is provided in the request
DEFAULT_SCRAPER_API_KEY = "181b5badff311b3ad954f238cdcf5be3"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app)

# In-memory job store: {job_id: {...}}
jobs: dict[str, dict] = {}


# ─── Background worker ────────────────────────────────────────────────────────

def _run_extraction(
    job_id: str,
    profile_url: str,
    fill_all: bool,
    scraper_api_key: str | None,
    use_free_proxy: bool,
) -> None:
    """Worker thread: fetch + format + store results."""
    jobs[job_id]["status"] = "running"

    def _progress(current: int, total: int) -> None:
        jobs[job_id]["progress"] = current
        jobs[job_id]["total"] = total

    def _stage(key: str, msg: str) -> None:
        jobs[job_id]["stage"] = key
        jobs[job_id]["message"] = msg
        # When we hit per-pub fetching, also reset progress denominator
        if key == "fetching_pubs":
            # total is already set by profile_done stage
            pass

    try:
        author = fetch_profile(
            profile_url,
            fill_all=fill_all,
            scraper_api_key=scraper_api_key,
            use_free_proxy=use_free_proxy,
            progress_callback=_progress,
            stage_callback=_stage,
        )
        publications = format_publications(author)
        profile = format_profile(author)

        jobs[job_id].update(
            {
                "status": "done",
                "stage": "done",
                "message": "Extraction complete.",
                "profile": profile,
                "publications": publications,
            }
        )
    except Exception as exc:
        jobs[job_id].update(
            {
                "status": "error",
                "stage": "error",
                "message": str(exc),
            }
        )


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the frontend SPA."""
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/api/extract", methods=["POST"])
def extract():
    """Start an extraction job and return a job_id."""
    data = request.get_json(silent=True) or {}
    profile_url: str = data.get("profile_url", "").strip()
    fill_all: bool = bool(data.get("fill_all", True))
    # Use key from request if provided, otherwise fall back to the hardcoded default
    scraper_api_key: str = data.get("scraper_api_key") or DEFAULT_SCRAPER_API_KEY
    use_free_proxy: bool = bool(data.get("use_free_proxy", False))

    if not profile_url:
        return jsonify({"error": "profile_url is required"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "pending",
        "stage": "pending",
        "progress": 0,
        "total": 0,
        "message": "Starting extraction...",
    }

    thread = threading.Thread(
        target=_run_extraction,
        args=(job_id, profile_url, fill_all, scraper_api_key, use_free_proxy),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id}), 202


@app.route("/api/status/<job_id>")
def status(job_id: str):
    """Return current job status and progress."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    resp: dict = {
        "status": job["status"],
        "stage": job.get("stage", ""),
        "progress": job.get("progress", 0),
        "total": job.get("total", 0),
        "message": job.get("message", ""),
    }

    if job["status"] == "done":
        resp["profile"] = job.get("profile", {})
        resp["publication_count"] = len(job.get("publications", []))

    if job["status"] == "error":
        resp["error"] = job.get("message", "Unknown error")

    return jsonify(resp)


@app.route("/api/result/<job_id>")
def result(job_id: str):
    """Return full structured result (profile + publications list)."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] != "done":
        return jsonify({"error": "Job not yet complete", "status": job["status"]}), 409

    return jsonify(
        {
            "profile": job["profile"],
            "publications": job["publications"],
        }
    )


@app.route("/api/download/<job_id>/publications_csv")
def download_publications_csv(job_id: str):
    """Download publications.csv."""
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Not ready"}), 409

    csv_data = publications_to_csv(job["publications"])
    name = job["profile"].get("name", "scholar").replace(" ", "_").lower()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}_publications.csv"'},
    )


@app.route("/api/download/<job_id>/profile_csv")
def download_profile_csv(job_id: str):
    """Download profile_summary.csv."""
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Not ready"}), 409

    csv_data = profile_to_csv(job["profile"])
    name = job["profile"].get("name", "scholar").replace(" ", "_").lower()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}_profile_summary.csv"'},
    )


@app.route("/api/download/<job_id>/publications_json")
def download_publications_json(job_id: str):
    """Download publications.json following the Publication schema."""
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Not ready"}), 409

    json_data = json.dumps(job["publications"], indent=2, ensure_ascii=False)
    name = job["profile"].get("name", "scholar").replace(" ", "_").lower()
    return Response(
        json_data,
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}_publications.json"'},
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Google Scholar Extractor API")
    print("   Frontend -> http://localhost:5000/")
    print("   API      -> http://localhost:5000/api/")
    app.run(debug=False, port=5000, threaded=True)
