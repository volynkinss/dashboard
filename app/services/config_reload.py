from __future__ import annotations

from pathlib import Path
from threading import Lock

from scripts.seed_from_dashy import import_config


class ConfigReloadError(RuntimeError):
    pass


class ConfigReloadInProgressError(ConfigReloadError):
    pass


_reload_lock = Lock()


def reload_config_from_dashy(*, config_path: str, deactivate_missing: bool = True) -> None:
    path = Path(config_path)
    if not path.exists():
        raise ConfigReloadError(f"Dashy config does not exist: {path}")
    if not path.is_file():
        raise ConfigReloadError(f"Dashy config is not a file: {path}")

    if not _reload_lock.acquire(blocking=False):
        raise ConfigReloadInProgressError("Dashy config reload is already in progress")

    try:
        try:
            import_config(path, deactivate_missing=deactivate_missing)
        except SystemExit as exc:
            message = str(exc).strip() or "Dashy config import failed"
            raise ConfigReloadError(message) from exc
    finally:
        _reload_lock.release()
