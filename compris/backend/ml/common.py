import json
from datetime import datetime, timezone

from ml import config


def update_metrics(section: str, values: dict) -> None:
    """Fusionne `values` dans models/metrics.json sous la clé `section` (lu par GET /ml/metrics)."""
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.MODELS_DIR / "metrics.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data[section] = {**values, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def data_source(path) -> str:
    return "synthetic" if "_synthetic" in str(path) else "real"
