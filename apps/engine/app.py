"""ASGI entrypoint shared by local Uvicorn, Docker and Vercel."""
from pathlib import Path
import sys

# Vercel loads the source checkout; installed-wheel imports work without this.
source = str(Path(__file__).resolve().parent / "src")
if source not in sys.path:
    sys.path.insert(0, source)

from bestar_work_hours.service.http import create_app

app = create_app()
