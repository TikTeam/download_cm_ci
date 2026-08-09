"""
logging_setup.py — Initialisation du logger application.
- Fichier rotatif (1/jour, 30 jours)
- Console stdout (visible dans GitHub Actions)
- Filtre de masquage des URLs / tokens
Idempotent : sans effet si appelé plusieurs fois.
"""
from __future__ import annotations

import logging
import re
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

_TOKEN_RE = re.compile(r"(token=)([^&\s]+)", re.IGNORECASE)
_LOGGER_NAME = "cadastre"


# ──────────────────────────────────────────────────────────────────────────────
# Masquage des données sensibles
# ──────────────────────────────────────────────────────────────────────────────
def _safe_str(value: str) -> str:
    """Masque le token dans une URL ou une chaîne quelconque."""
    try:
        parts = urlsplit(value)
        if parts.scheme and parts.netloc:
            clean_query = _TOKEN_RE.sub(r"\1***", parts.query)
            return urlunsplit(("***", "***", "***", clean_query, ""))
    except Exception:
        pass
    return _TOKEN_RE.sub(r"\1***", value)


def _redact(args: object) -> object:
    """Applique _safe_str récursivement sur les arguments d'un LogRecord."""
    if isinstance(args, dict):
        return {k: _safe_str(v) if isinstance(v, str) else v for k, v in args.items()}
    if isinstance(args, tuple):
        return tuple(_safe_str(a) if isinstance(a, str) else a for a in args)
    if isinstance(args, str):
        return _safe_str(args)
    return args


def _make_redact_filter() -> logging.Filter:
    """Retourne un Filter fonctionnel sans classe utilisateur."""
    f = logging.Filter()

    def _filter(record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _safe_str(record.msg)
        record.args = _redact(record.args)
        return True

    f.filter = _filter   # type: ignore[method-assign]
    return f


# ──────────────────────────────────────────────────────────────────────────────
# Setup principal
# ──────────────────────────────────────────────────────────────────────────────
def setup_logger(log_dir: Path, log_filename: str) -> logging.Logger:
    """
    Initialise et retourne le logger 'cadastre'.
    Idempotent : si les handlers sont déjà présents, retourne le logger existant.
    """
    logger = logging.getLogger(_LOGGER_NAME)

    if logger.handlers:          # déjà initialisé → ne rien refaire
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Handler fichier rotatif ───────────────────────────────────────────────
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = TimedRotatingFileHandler(
        log_dir / log_filename,
        when="midnight",
        backupCount=30,
        encoding="utf-8",
        utc=True,
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # ── Handler console (GitHub Actions) ─────────────────────────────────────
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # ── Filtre de sécurité ────────────────────────────────────────────────────
    logger.addFilter(_make_redact_filter())

    # ── Réduire le bruit des bibliothèques tierces ────────────────────────────
    for lib in ("urllib3", "requests", "fiona", "shapely", "googleapiclient"):
        logging.getLogger(lib).setLevel(logging.WARNING)
    logging.captureWarnings(True)

    return logger


def get_logger() -> logging.Logger:
    """Raccourci : récupère le logger sans le reconfigurer."""
    return logging.getLogger(_LOGGER_NAME)
