"""
http_client.py — Requêtes HTTP avec retries + fallback proxy Landfolio.
Session persistante partagée (module-level singleton via fonction).
"""
from __future__ import annotations

import time
import logging
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import src.config as cfg

logger = logging.getLogger("cadastre.http")

# Session partagée (initialisée une seule fois)
_session: Optional[requests.Session] = None


# ──────────────────────────────────────────────────────────────────────────────
# Session
# ──────────────────────────────────────────────────────────────────────────────
def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=cfg.HTTP_MAX_RETRIES,
        backoff_factor=cfg.HTTP_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://",  adapter)
    session.headers.update(cfg.HTTP_HEADERS)
    return session


def get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = _make_session()
    return _session


# ──────────────────────────────────────────────────────────────────────────────
# GET générique avec retry applicatif
# ──────────────────────────────────────────────────────────────────────────────
def http_get(url: str, timeout: int = cfg.HTTP_TIMEOUT) -> requests.Response:
    """
    GET avec retry exponentiel applicatif.
    Lève une exception après épuisement des tentatives.
    """
    session    = get_session()
    last_exc: Optional[Exception] = None

    for attempt in range(1, cfg.HTTP_MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as exc:
            last_exc = exc
            wait = cfg.HTTP_BACKOFF * attempt
            if attempt < cfg.HTTP_MAX_RETRIES:
                logger.warning(
                    "Tentative %d/%d échouée — retry dans %.1fs (%s)",
                    attempt, cfg.HTTP_MAX_RETRIES, wait, type(exc).__name__,
                )
                time.sleep(wait)

    logger.error("Échec définitif après %d tentatives.", cfg.HTTP_MAX_RETRIES)
    raise last_exc  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────────────────────
# GET ArcGIS avec fallback proxy
# ──────────────────────────────────────────────────────────────────────────────
def arcgis_get(url: str) -> requests.Response:
    """
    Tente un accès direct à l'API ArcGIS.
    Si échec ou réponse invalide → fallback sur le proxy Landfolio.
    """
    session = get_session()

    # ── Tentative directe ─────────────────────────────────────────────────────
    try:
        r = session.get(url, timeout=cfg.HTTP_TIMEOUT)
        if r.status_code == 200 and "features" in r.text:
            return r
        logger.debug("Direct KO (HTTP %s) → fallback proxy.", r.status_code)
    except Exception as exc:
        logger.debug("Direct exception (%s) → fallback proxy.", type(exc).__name__)

    # ── Fallback proxy ────────────────────────────────────────────────────────
    proxy_session = _make_session()
    proxy_session.headers.update({"Referer": cfg.PROXY_REFERER})

    # Initialisation de la session proxy (cookie)
    try:
        proxy_session.get(cfg.PROXY_REFERER, timeout=cfg.HTTP_TIMEOUT)
    except Exception:
        pass

    r = proxy_session.get(
        cfg.PROXY_BASE + url,
        timeout=cfg.HTTP_TIMEOUT,
    )

    if r.status_code != 200 or "features" not in r.text:
        raise RuntimeError(
            f"Direct + proxy échoués (HTTP {r.status_code}) pour : {url}"
        )

    logger.debug("Proxy OK.")
    return r

def arcgis_post(
    rest_url  : str,
    layer_id  : int,
    token     : Optional[str],
    offset    : int,
    ) -> requests.Response :
    """
    Fallback POST pour contourner HTTP 405 du proxy sur les offsets élevés.
    Utilise application/x-www-form-urlencoded (standard ArcGIS REST).
    """
    from src.http_client import get_session

    url = f"{rest_url}/{layer_id}/query"

    params: dict[str, str] = {
        "f"                : cfg.ARCGIS_F,
        "where"            : cfg.ARCGIS_WHERE,
        "returnGeometry"   : "true",
        "spatialRel"       : cfg.ARCGIS_SPATIAL_REL,
        "geometryType"     : cfg.ARCGIS_GEOM_TYPE,
        "outFields"        : "*",
        "outSR"            : str(cfg.ARCGIS_OUT_SR),
        "resultOffset"     : str(offset),
        "resultRecordCount": str(cfg.ARCGIS_RECORD_COUNT),
        }
    if token:
        params["token"] = token

    session = get_session()
    r = session.post(url, data=params, timeout=cfg.HTTP_TIMEOUT)

    if r.status_code != 200 or "features" not in r.text:
        raise RuntimeError(
            f"POST échoué (HTTP {r.status_code}) pour : {url} | offset={offset}"
        )

    logger.debug("Couche — POST OK (offset=%d).", offset)
    return r