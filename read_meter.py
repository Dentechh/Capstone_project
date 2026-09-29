"""
read_meter.py - DEV-ONLY Firestore read counter for Flask.

Prints one line per request showing how many documents Firestore returned
and which collections they came from, e.g.

    [READS] GET /admin_dashboard -> 87 docs  {'Customer_Account': 26, 'appointments (group)': 26, 'Approve (group)': 26, 'Stats/doc': 1}
    [READS] GET /admin/financial_chart_data -> 0 docs

Use it to see which request (and which query) is spending your reads, and to
check that a fix actually helped.

HOW TO USE
    1. Put this file next to main.py.
    2. In main.py, right after the line   self._app = Flask(__name__)   add:

           import read_meter; read_meter.install(self._app)

    3. Restart Flask and watch the terminal while you refresh the dashboard.
    4. To turn it off without editing code, set the environment variable
       READ_METER=0 (or just delete the two lines above).

WHAT IT COUNTS
    Documents returned by query .stream()/.get() and by document .get().
    Firestore bills one read per document returned (an empty query still
    costs 1, which this does not add). It does NOT count aggregation
    count() queries, which cost roughly 1 read per 1000 index entries.
    Reads made outside a web request (background threads) are not counted.
"""

import os

from flask import g, request


def _bump(label):
    try:
        g.fs_reads = getattr(g, "fs_reads", 0) + 1
        breakdown = getattr(g, "fs_breakdown", None)
        if breakdown is None:
            breakdown = g.fs_breakdown = {}
        breakdown[label] = breakdown.get(label, 0) + 1
    except RuntimeError:
        pass  # no request context (background thread, startup code)


def install(app):
    if os.getenv("READ_METER", "1") == "0":
        return

    from google.cloud.firestore_v1.query import Query
    from google.cloud.firestore_v1.document import DocumentReference

    # The Flask reloader imports main.py twice; patch only once per process.
    if getattr(Query.stream, "_metered", False):
        return

    original_stream = Query.stream
    original_get = DocumentReference.get

    def metered_stream(self, *args, **kwargs):
        parent = getattr(self, "_parent", None)
        label = getattr(parent, "id", "?")
        if getattr(self, "_all_descendants", False):
            label += " (group)"
        for doc in original_stream(self, *args, **kwargs):
            _bump(label)
            yield doc

    def metered_get(self, *args, **kwargs):
        parent = getattr(self, "parent", None)
        _bump(f"{getattr(parent, 'id', '?')}/doc")
        return original_get(self, *args, **kwargs)

    metered_stream._metered = True
    Query.stream = metered_stream
    DocumentReference.get = metered_get

    @app.after_request
    def report_reads(response):
        if request.path.startswith("/static"):
            return response
        total = getattr(g, "fs_reads", 0)
        if total:
            print(f"[READS] {request.method} {request.path} -> {total} docs  {getattr(g, 'fs_breakdown', {})}")
        else:
            print(f"[READS] {request.method} {request.path} -> 0 docs")
        return response