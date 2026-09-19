"""Development entry point: python run.py (or flask --app run.py run)."""
from __future__ import annotations

from app import create_app

app = create_app()

if __name__ == "__main__":
    # waitress is used instead of the Flask dev server so the local runtime
    # is a real WSGI server on Windows; docker/production uses the same app.
    from waitress import serve

    import os

    port = int(os.getenv("PORT", "5000"))
    print(f"HeatWatch AI backend listening on http://127.0.0.1:{port}")
    serve(app, host="0.0.0.0", port=port, threads=8)
