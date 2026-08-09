"""
config.py — Configuration centralisée du projet CadastreExtrac.
Toutes les constantes sont déclarées ici — aucun secret codé en dur.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from datetime import datetime, timezone
timecode = datetime.now(tz=timezone.utc).strftime("%d%m%Y%H%M")
timetext = datetime.now(tz=timezone.utc).strftime("%d-%m-%Y_%H-%M")

# ── dotenv ────────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass   # en CI, pas de .env — les secrets viennent des env vars GitHub


# ──────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
#  1. SECRETS & VARIABLES D'ENVIRONNEMENT
# ══════════════════════════════════════════════════════════════════════════════

# ── Portail Cadastre ─────────────────────────────────────────────────────────
URL_CADASTRE: str = os.environ.get("URL_CADASTRE", "")
"""URL du portail LandFolio CI."""

PROXY_BASE: str = os.environ.get("PROXY_BASE", "")
"""Proxy HTTP de base (optionnel, ex: http://proxy:8080)."""

PROXY_REFERER: str = os.environ.get("PROXY_REFERER", "")
"""Valeur du header Referer attendue par le portail."""


# ── Google Drive ──────────────────────────────────────────────────────────────
DRIVE_FOLDER_ID: str = os.environ.get("DRIVE_FOLDER_ID", "")
"""ID du dossier Drive cible (depuis l'URL: .../folders/<ID>)."""

GDRIVE_CREDS_FILE: str = os.environ.get("GDRIVE_CREDENTIALS_FILE", "/tmp/gdrive_credentials.json")
"""Chemin vers le JSON du Service Account (écrit par le workflow GitHub)."""

# ── Service Account JSON ──────────────────────────────────────────────────────
GDRIVE_SA_JSON: str = os.environ.get("GDRIVE_SA_JSON", "")
"""Contenu ou chemin du fichier JSON du Service Account Google Drive."""

# ── OAuth2 (fallback si pas de Service Account) ───────────────────────────────
GDRIVE_CLIENT_ID: str = os.environ.get("GDRIVE_CLIENT_ID", "")
GDRIVE_CLIENT_SECRET: str = os.environ.get("GDRIVE_CLIENT_SECRET", "")
GDRIVE_REFRESH_TOKEN: str = os.environ.get("GDRIVE_REFRESH_TOKEN", "")


# ──────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
#  2. PARAMÈTRES HTTP
# ══════════════════════════════════════════════════════════════════════════════

HTTP_TIMEOUT: int = int(os.environ.get("HTTP_TIMEOUT", "15"))
"""Timeout des requêtes HTTP (secondes)."""

HTTP_MAX_RETRIES: int = int(os.environ.get("HTTP_MAX_RETRIES", "5"))
"""Nombre de tentatives en cas d'erreur HTTP (backoff exponentiel)."""

HTTP_BACKOFF: int = int(os.environ.get("HTTP_BACKOFF", "3"))


HTTP_RECORD_COUNT: int = int(os.environ.get("HTTP_RECORD_COUNT", "1000"))
"""Nombre d'enregistrements par requête ArcGIS."""

HTTP_HEADERS    : dict = {"User-Agent": "Mozilla/5.0"}
HTTP_RETRY_ATTEMPTS = int(os.getenv("HTTP_RETRY_ATTEMPTS", "5"))
HTTP_RETRY_DELAY = float(os.getenv("HTTP_RETRY_DELAY", "3.0"))



# ──────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
#  3. CONSTANTES ARCGIS
# ══════════════════════════════════════════════════════════════════════════════

ARCGIS_SR: str = "102100"
"""Spatial Reference EPSG pour la reprojection WGS84 → Web Mercator."""

ARCGIS_RECORD_COUNT : int = 1_000
ARCGIS_F            : str = "json"
ARCGIS_WHERE        : str = "1=1"
ARCGIS_SPATIAL_REL  : str = "esriSpatialRelIntersects"
ARCGIS_GEOM_TYPE    : str = "esriGeometryPolygon"
ARCGIS_OUT_SR       : int = 4326
CRS                 : str = f"EPSG:{ARCGIS_OUT_SR}"


# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
LOG_LEVEL       : str = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT      : str = "[%(asctime)s] %(levelname)-8s | %(name)s — %(message)s"
LOG_DATEFORMAT  : str = "%Y-%m-%d %H:%M:%S"



# ──────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
#  4. COUCHES À EXTRAIRE
# ══════════════════════════════════════════════════════════════════════════════

LICENCE_GROUPS: list[str] = [
    "Demandes",
    "Licences",
]
"""Groupes de couches traités comme licences (fusionnés)."""

ADMIN_GROUP: str = "Administration"
"""Nom du groupe multi-couches pour les couches administratives."""


# ──────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
#  5. UPLOAD DRIVE
# ══════════════════════════════════════════════════════════════════════════════

GDRIVE_KEEP_LAST_N: int = int(os.environ.get("GDRIVE_KEEP_LAST_N", "5"))
"""Nombre de versions à conserver sur Drive (rotation)."""

GDRIVE_UPLOAD_FORMATS: set[str] = {
    ".gpkg",
    ".shp",
    ".geojson",
    ".csv",
    ".log",
}
"""Formats de fichier uploadés sur Drive."""


# ──────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
#  6. LOGGING
# ══════════════════════════════════════════════════════════════════════════════

LOG_DIR: Path = Path("data/logs")
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")


# ──────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
#  7. DOSSIERS
# ══════════════════════════════════════════════════════════════════════════════

DATA_DIR: Path = Path("data")


# ──────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
#  8. VALIDATION AU DÉMARRAGE
# ══════════════════════════════════════════════════════════════════════════════

def _check_required() -> None:
    """
    Vérifie que les secrets obligatoires sont présents.
    Appelé une seule fois au premier import de ce module.
    Appelée explicitement par main.py après setup_logger().
    """
    missing: list[str] = []

    if not URL_CADASTRE:
        missing.append("URL_CADASTRE")

    # Au moins une méthode d'auth Drive
    has_sa = bool(GDRIVE_SA_JSON) and Path(GDRIVE_CREDS_FILE).exists()
    has_oauth = all([GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN])
    if not (has_sa or has_oauth):
        missing.append(
            "GDRIVE auth: il faut GDRIVE_SA_JSON ou "
            "(GDRIVE_CLIENT_ID + GDRIVE_CLIENT_SECRET + GDRIVE_REFRESH_TOKEN)"
        )

    if missing:
        joined = ", ".join(missing)
        logging.critical(
            "❌ Secrets obligatoires manquants : %s\n"
            "→ Configurez ces variables dans GitHub → Settings → Secrets.",
            joined,
        )
        sys.exit(1)

    logging.debug("✅ Validation secrets : tous OK.")


# Validation lazy (appelée par main.py)
def ensure_config() -> None:
    """API publique pour forcer la validation config + création dirs."""
    _ensure_dirs()
    _check_required()


def _ensure_dirs() -> None:
    """Crée les dossiers data/ et data/log/ si absents."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
