"""
formatter.py — Maps raw scholarly publication dicts to the typed Publication schema.

Input: raw scholarly pub dict with pub['bib'] containing title, author, pub_year,
       journal, venue, booktitle, publisher, doi, etc.

Output Publication schema:
    { citation: string }
    | { type: 'journal'|'conference'|'book-authored'|'book-edited'
             |'patent-granted'|'patent-published'|'Research-Publications',
        title, authors, year, doi, ... type-specific fields }
"""

from __future__ import annotations


def _parse_authors(raw: str) -> list[str]:
    """Split 'A and B and C' style scholarly author strings."""
    if not raw:
        return []
    return [a.strip() for a in raw.split(" and ") if a.strip()]


def _parse_year(raw) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _contains(haystack: str, *needles: str) -> bool:
    h = (haystack or "").lower()
    return any(n.lower() in h for n in needles)


def classify_publication(pub: dict) -> dict:
    """Return a typed Publication object from a scholarly pub dict."""
    bib = pub.get("bib", {})

    title       = bib.get("title", "")
    authors     = _parse_authors(bib.get("author", ""))
    year        = _parse_year(bib.get("pub_year"))
    doi         = bib.get("doi", "")
    publisher   = bib.get("publisher", "")
    volume      = bib.get("volume", "")
    pages       = bib.get("pages", "")
    journal     = bib.get("journal", "")
    venue       = bib.get("venue", "")
    conference  = bib.get("conference", bib.get("booktitle", ""))
    entry_type  = bib.get("ENTRYTYPE", "").lower()
    pub_url     = pub.get("pub_url", "")

    # ── 1. Patent ─────────────────────────────────────────────────
    is_patent = (
        entry_type == "patent"
        or _contains(publisher, "patent")
        or _contains(title, "patent")
        or _contains(pub_url, "patents.google.com", "/patent/")
    )
    if is_patent:
        is_granted = _contains(title, "granted", "issued") or entry_type == "patent"
        return {
            "type": "patent-granted" if is_granted else "patent-published",
            "title": title,
            "authors": authors,
            "year": year,
            "patentNumber": bib.get("number", bib.get("patent_number", "")),
            "applicationNumber": bib.get("application_number", ""),
            "inventors": authors,
            "publisher": publisher,
        }

    # ── 2. Book ───────────────────────────────────────────────────
    is_book = entry_type in ("book", "inbook", "incollection", "booklet")
    if is_book:
        is_edited = "editor" in bib or _contains(title, " ed.", "edition", "handbook", "edited")
        return {
            "type": "book-edited" if is_edited else "book-authored",
            "title": title,
            "authors": authors,
            "year": year,
            "doi": doi,
            "pages": pages,
            "publisher": publisher,
        }

    # ── 3. Conference ─────────────────────────────────────────────
    is_conference = (
        entry_type in ("inproceedings", "proceedings", "conference")
        or bool(conference)
        or _contains(venue, "conference", "proceedings", "workshop", "symposium",
                     "congress", "acm", "ieee", "icml", "nips", "neurips",
                     "cvpr", "iccv", "eccv", "aaai", "ijcai", "sigchi")
    )
    if is_conference:
        return {
            "type": "conference",
            "title": title,
            "authors": authors,
            "year": year,
            "conference": conference or venue,
            "location": bib.get("address", ""),
            "date": bib.get("month", ""),
            "doi": doi,
            "publisher": publisher,
        }

    # ── 4. Journal ────────────────────────────────────────────────
    if journal or entry_type == "article":
        return {
            "type": "journal",
            "title": title,
            "authors": authors,
            "journal": journal or venue,
            "volume": volume,
            "pages": pages,
            "articleNumber": bib.get("article_number", bib.get("eid", "")),
            "year": year,
            "doi": doi,
            "publisher": publisher,
        }

    # ── 5. Research Publications (generic with title) ──────────────
    if title:
        return {
            "type": "Research-Publications",
            "title": title,
            "authors": authors,
            "year": year,
            "doi": doi,
            "publisher": publisher,
            "ResearchPublications": venue or journal or "",
        }

    # ── 6. Citation fallback ───────────────────────────────────────
    return {"citation": bib.get("citation", bib.get("abstract", str(bib)))}


def format_publications(author: dict) -> list[dict]:
    return [classify_publication(pub) for pub in author.get("publications", [])]


def format_profile(author: dict) -> dict:
    bib = author.get("bib", {})
    return {
        "name":               bib.get("name", ""),
        "affiliation":        bib.get("affiliation", ""),
        "email":              bib.get("email", ""),
        "interests":          bib.get("interests", []),
        "homepage":           bib.get("homepage", ""),
        "citedby":            author.get("citedby", 0),
        "citedby5y":          author.get("citedby5y", 0),
        "hindex":             author.get("hindex", 0),
        "hindex5y":           author.get("hindex5y", 0),
        "i10index":           author.get("i10index", 0),
        "i10index5y":         author.get("i10index5y", 0),
        "total_publications": len(author.get("publications", [])),
        "cites_per_year":     author.get("cites_per_year", {}),
        "coauthors": [
            {
                "name":        ca.get("bib", {}).get("name", ""),
                "affiliation": ca.get("bib", {}).get("affiliation", ""),
                "scholar_id":  ca.get("scholar_id", ""),
            }
            for ca in author.get("coauthors", [])
        ],
    }
