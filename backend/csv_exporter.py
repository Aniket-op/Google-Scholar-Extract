"""
csv_exporter.py — Converts formatted Publication and Profile dicts to CSV strings.

publications.csv  — One row per publication, all typed fields as columns.
profile_summary.csv — Single-row author metrics.
"""

import csv
import io


# All possible columns across all Publication types
PUBLICATION_COLUMNS = [
    "type",
    "title",
    "authors",
    "year",
    "doi",
    # Journal
    "journal",
    "volume",
    "pages",
    "articleNumber",
    "impactFactor",
    "publisher",
    # Conference
    "conference",
    "location",
    "date",
    # Patent
    "patentNumber",
    "applicationNumber",
    "inventors",
    # Research-Publications
    "ResearchPublications",
    # Fallback
    "citation",
]

PROFILE_COLUMNS = [
    "name",
    "affiliation",
    "email",
    "interests",
    "homepage",
    "citedby",
    "citedby5y",
    "hindex",
    "hindex5y",
    "i10index",
    "i10index5y",
    "total_publications",
]


def _join_list(value) -> str:
    """Convert a list to a semicolon-separated string."""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value) if value is not None else ""


def publications_to_csv(publications: list[dict]) -> str:
    """Serialize a list of Publication dicts to a CSV string."""
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=PUBLICATION_COLUMNS,
        extrasaction="ignore",
        lineterminator="\r\n",
    )
    writer.writeheader()
    for pub in publications:
        row = {}
        for col in PUBLICATION_COLUMNS:
            val = pub.get(col, "")
            row[col] = _join_list(val) if isinstance(val, list) else (val if val is not None else "")
        writer.writerow(row)
    return output.getvalue()


def profile_to_csv(profile: dict) -> str:
    """Serialize a profile summary dict to a single-row CSV string."""
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=PROFILE_COLUMNS,
        extrasaction="ignore",
        lineterminator="\r\n",
    )
    writer.writeheader()
    row = {}
    for col in PROFILE_COLUMNS:
        val = profile.get(col, "")
        row[col] = _join_list(val) if isinstance(val, list) else (val if val is not None else "")
    writer.writerow(row)
    return output.getvalue()
