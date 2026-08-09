"""
parser.py — Parsing HTML/JSON d'initialisation + download paginé ArcGIS.
"""
from __future__ import annotations

import codecs
import json
import logging
import re
import time
from typing import Any, Optional

from bs4 import BeautifulSoup

import src.config as cfg
from src.http_client import arcgis_get, arcgis_post, http_get

logger = logging.getLogger("cadastre.parser")

# Types métier
DataInfo = dict[str, dict[str, Any]]
DataJson = dict[str, dict[str, Any]]


# ──────────────────────────────────────────────────────────────────────────────
# Fetch + parse du JSON d'initialisation
# ──────────────────────────────────────────────────────────────────────────────
def fetch_init_json(url: str, json_name: str = "MainPage.Init") -> dict[str, Any]:
    """Récupère la page principale et extrait le JSON d'initialisation."""
    response = http_get(url)
    return _parse_init_json(response.text, json_name)


def _parse_init_json(html: str, json_name: str) -> dict[str, Any]:
    soup    = BeautifulSoup(html, "html.parser")
    pattern = re.compile(
        re.escape(json_name) + r"""\s*\(\s*['"]((?:\\.|[^'"])+?)['"]\s*,""",
        re.DOTALL,
    )
    for script in soup.find_all("script", {"type": "text/javascript"}):
        m = pattern.search(script.get_text(strip=True))
        if m:
            obj: dict[str, Any] = json.loads(
                codecs.decode(m.group(1), "unicode_escape")
            )
            logger.info("JSON '%s' extrait (%d clés).", json_name, len(obj))
            return obj

    raise RuntimeError(
        f"'{json_name}' introuvable dans la page. "
        "La structure du portail a peut-être changé."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Extraction des métadonnées des services
# ──────────────────────────────────────────────────────────────────────────────
def extract_data_info(html_json: dict[str, Any]) -> DataInfo:
    """
    Retourne un dict des services Dynamic ArcGIS avec leurs couches associées.
    Structure : { DisplayName: {RestUrl, ArcGISToken, LayerName[], LayerID[]} }
    """
    data_info: DataInfo = {}

    map_services    : list[dict] = html_json.get("MapServices")    or []
    group_templates : list[dict] = html_json.get("GroupByTemplates") or []

    # Index O(1) : MapServiceName → groupe
    grp_index: dict[str, dict] = {
        g["MapServiceName"]: g
        for g in group_templates
        if "MapServiceName" in g
    }

    for ms in map_services:
        if ms.get("MapServiceType") != "Dynamic":
            continue

        display_name: str = ms.get("DisplayName") or "Unknown"
        entry: dict[str, Any] = {
            "RestUrl":     ms.get("RestUrl"),
            "ArcGISToken": ms.get("ArcGISToken"),
            "LayerName":   [],
            "LayerID":     [],
        }

        grp = grp_index.get(ms.get("Name") or "")
        if grp:
            templates = grp.get("LayerTemplates") or []
            entry["LayerName"] = [
                t["LayerName"][0] for t in templates if t.get("LayerName")
            ]
            entry["LayerID"] = [
                int(t["LayerID"]) for t in templates if "LayerID" in t
            ]

        data_info[display_name] = entry
        logger.info(
            "Service '%s' → %d couche(s) | token: %s",
            display_name,
            len(entry["LayerID"]),
            "présent" if entry["ArcGISToken"] else "absent",
        )

    return data_info


# ──────────────────────────────────────────────────────────────────────────────
# Construction de l'URL de requête ArcGIS
# ──────────────────────────────────────────────────────────────────────────────
def _build_query_url(
    rest_url: str,
    layer_id: int,
    token: Optional[str],
    offset: int,
) -> str:
    params: dict[str, str] = {
        "f":                 cfg.ARCGIS_F,
        "where":             cfg.ARCGIS_WHERE,
        "returnGeometry":    "true",
        "spatialRel":        cfg.ARCGIS_SPATIAL_REL,
        "geometryType":      cfg.ARCGIS_GEOM_TYPE,
        "outFields":         "*",
        "outSR":             str(cfg.ARCGIS_OUT_SR),
        "resultOffset":      str(offset),
        "resultRecordCount": str(cfg.ARCGIS_RECORD_COUNT),
    }
    if token:
        params["token"] = token

    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{rest_url}/{layer_id}/query?{qs}"


# ──────────────────────────────────────────────────────────────────────────────
# Download paginé d'une couche
# ──────────────────────────────────────────────────────────────────────────────
def _fetch_layer_features(
    rest_url  : str,
    layer_id  : int,
    layer_name: str,
    token     : Optional[str],
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """
    Télécharge toutes les features d'une couche (pagination automatique).
    Stratégie : GET direct → fallback proxy GET → fallback POST (HTTP 405).
    Retourne (features, geometryType).
    En cas d'échec partiel : log WARNING + retourne les features déjà collectées.
    """
    features  : list[dict[str, Any]] = []
    geom_type : Optional[str]        = None
    offset    : int                  = 0
    partial   : bool                 = False  # flag données tronquées

    while True:
        url      = _build_query_url(rest_url, layer_id, token, offset)
        response = None
        last_exc : Optional[Exception] = None

        # ── Retry loop : GET → POST (405) ─────────────────────────────────────
        for attempt in range(1, cfg.HTTP_MAX_RETRIES + 1):
            try:
                response = arcgis_get(url)
                last_exc = None
                break  # succès

            except Exception as exc:
                last_exc = exc
                http_code = _extract_http_code(str(exc))

                # HTTP 405 → le proxy bloque le GET à cet offset → essayer POST
                if http_code == 405:
                    logger.debug(
                        "Couche '%s' — HTTP 405 (offset=%d) → tentative POST.",
                        layer_name, offset,
                    )
                    try:
                        response = arcgis_post(rest_url, layer_id, token, offset)
                        last_exc = None
                        break  # POST réussi
                    except Exception as post_exc:
                        last_exc = post_exc
                        logger.debug(
                            "Couche '%s' — POST échoué : %s", layer_name, post_exc
                        )
                        break  # inutile de retenter, le proxy bloque

                # Autres erreurs → retry avec backoff
                if attempt < cfg.HTTP_MAX_RETRIES:
                    wait = cfg.HTTP_RETRY_DELAY * attempt
                    logger.warning(
                        "Couche '%s' — tentative %d/%d échouée, retry dans %ds…",
                        layer_name, attempt, cfg.HTTP_MAX_RETRIES, wait,
                    )
                    time.sleep(wait)

        # ── Échec définitif sur cette page ────────────────────────────────────
        if last_exc is not None:
            if features:
                partial = True
                logger.warning(
                    "⚠️ Couche '%s' — données PARTIELLES : %d features "
                    "(échec à offset=%d : %s).",
                    layer_name, len(features), offset, last_exc,
                )
            else:
                logger.error(
                    "❌ Couche '%s' — requête échouée : %s", layer_name, last_exc
                )
            break

        # ── Parse JSON ────────────────────────────────────────────────────────
        try:
            data: dict[str, Any] = response.json()
        except Exception:
            logger.error(
                "Couche '%s' — réponse JSON invalide (offset=%d).",
                layer_name, offset,
            )
            break

        # Erreur ArcGIS dans le corps de la réponse
        if "error" in data:
            err = data["error"]
            logger.error(
                "Couche '%s' — erreur ArcGIS code=%s : %s",
                layer_name, err.get("code"), err.get("message"),
            )
            break

        batch: list[dict] = data.get("features") or []
        if not batch:
            break  # fin de pagination normale

        geom_type  = data.get("geometryType", geom_type)
        features.extend(batch)
        offset    += cfg.ARCGIS_RECORD_COUNT

        logger.info(
            "Couche '%s' — page +%d (total : %d).",
            layer_name, len(batch), len(features),
        )

        # Dernière page : batch incomplet → inutile de requêter la suivante
        if len(batch) < cfg.ARCGIS_RECORD_COUNT:
            break

    # ── Log final ─────────────────────────────────────────────────────────────
    if not features:
        logger.warning("Couche '%s' — aucune feature récupérée.", layer_name)
    elif partial:
        logger.warning(
            "⚠️ Couche '%s' — %d features (PARTIEL — vérifier manuellement).",
            layer_name, len(features),
        )
    else:
        logger.info(
            "✅ Couche '%s' — %d features.", layer_name, len(features),
        )  # ce log sera écrasé par extract_data_json, c'est normal

    return features, geom_type


# ──────────────────────────────────────────────────────────────────────────────
# Helpers privés
# ──────────────────────────────────────────────────────────────────────────────
def _extract_http_code(error_msg: str) -> Optional[int]:
    """Extrait le code HTTP (ex: 405) depuis un message d'erreur RuntimeError."""
    m = re.search(r"HTTP (\d{3})", error_msg)
    return int(m.group(1)) if m else None

# ──────────────────────────────────────────────────────────────────────────────
# Orchestration du download de tous les services
# ──────────────────────────────────────────────────────────────────────────────
def extract_data_json(data_info: DataInfo) -> DataJson:
    """
    Télécharge les features de tous les services/couches.
    Retourne : { DisplayName: { LayerName: {features, geom_type} } }
    """
    data_json: DataJson = {}

    for svc_name, svc in data_info.items():
        rest_url    : Optional[str]  = svc.get("RestUrl")
        token       : Optional[str]  = svc.get("ArcGISToken")
        layer_ids   : list[int]      = svc.get("LayerID")   or []
        layer_names : list[str]      = svc.get("LayerName") or []

        if not rest_url or not layer_ids:
            logger.warning(
                "Service '%s' ignoré (RestUrl ou LayerID manquants).", svc_name
            )
            continue

        data_json[svc_name] = {}

        for lid, lname in zip(layer_ids, layer_names):
            features, geom_type = _fetch_layer_features(rest_url, lid, lname, token)
            if features:
                data_json[svc_name][lname] = {
                    "features":  features,
                    "geom_type": geom_type,
                }
                logger.info(
                    "✅ '%s / %s' — %d features.", svc_name, lname, len(features)
                )

    return data_json
