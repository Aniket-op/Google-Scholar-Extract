"""
scraper.py — Google Scholar profile fetcher using scholarly + ScraperAPI.
Mirrors the working logic from Google_Scholar_Scraper.ipynb exactly.
"""

import re
import time
from scholarly import scholarly, ProxyGenerator


def extract_user_id(raw: str) -> str:
    """Extract Scholar user ID from a full URL or return as-is."""
    match = re.search(r"user=([A-Za-z0-9_-]+)", raw)
    return match.group(1) if match else raw.strip().rstrip("/")


def fetch_profile(
    profile_url: str,
    fill_all: bool = True,
    scraper_api_key: str | None = None,
    use_free_proxy: bool = False,
    progress_callback=None,
    stage_callback=None,
) -> dict:
    """
    Fetch a Google Scholar author profile using scholarly.
    Mirrors CELL 3 + CELL 4 of Google_Scholar_Scraper.ipynb exactly.
    """

    def _stage(key: str, msg: str) -> None:
        if stage_callback:
            stage_callback(key, msg)

    # ── Proxy setup (mirrors notebook Cell 3 setup_proxy) ──────────
    if scraper_api_key:
        _stage("proxy", "Configuring ScraperAPI proxy...")
        try:
            pg = ProxyGenerator()
            pg.ScraperAPI(scraper_api_key)
            scholarly.use_proxy(pg)
            _stage("proxy", "ScraperAPI proxy active.")
        except Exception as e:
            _stage("proxy", f"Proxy setup warning: {e}")
    elif use_free_proxy:
        _stage("proxy", "Setting up free proxy (may take 30s)...")
        try:
            pg = ProxyGenerator()
            ok = pg.FreeProxies()
            if ok:
                scholarly.use_proxy(pg)
                _stage("proxy", "Free proxy ready.")
            else:
                _stage("proxy", "No free proxy found, trying direct.")
        except Exception as e:
            _stage("proxy", f"Free proxy failed: {e}")

    user_id = extract_user_id(profile_url)
    _stage("connecting", f"Connecting to Google Scholar (user: {user_id})...")

    # ── Fetch author (mirrors Cell 4) ──────────────────────────────
    try:
        author_raw = scholarly.search_author_id(user_id)
    except Exception as exc:
        err_msg = str(exc)
        if "MaxTriesExceeded" in err_msg or "Cannot Fetch" in err_msg or "429" in err_msg:
            raise Exception(
                "Google Scholar is rate-limiting this IP. "
                "Please enter your ScraperAPI key in the field below and try again. "
                "Get a free key at https://www.scraperapi.com/"
            )
        raise Exception(f"Could not fetch profile: {err_msg}")

    _stage("loading", "Profile found. Loading full sections (indices, coauthors, publications)...")

    try:
        author = scholarly.fill(
            author_raw,
            sections=["basics", "indices", "counts", "coauthors", "publications"],
        )
    except Exception as exc:
        raise Exception(f"Failed to load profile sections: {exc}")

    pubs = author.get("publications", [])
    total = len(pubs)
    _stage("profile_done", f"Profile loaded. Found {total} publications.")

    # ── Per-publication fill (mirrors Cell 4 loop) ─────────────────
    if fill_all and total > 0:
        _stage("fetching_pubs", f"Fetching full details for {total} publications...")
        for i, pub in enumerate(pubs, 1):
            try:
                scholarly.fill(pub)
            except Exception:
                pass  # skip individual failures gracefully
            if progress_callback:
                progress_callback(i, total)
            if stage_callback:
                stage_callback("pub_progress", f"Fetched {i} of {total} publications...")
            time.sleep(0.3)

    _stage("done", "Extraction complete.")
    return author
