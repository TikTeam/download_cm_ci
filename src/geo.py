"""
geo.py — Conversion features ArcGIS → GeoDataFrames + fusion.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry

import src.config as cfg

logger = logging.getLogger("cadastre.geo")

_TS_THRESHOLD = 1_000_000_000_000   # seuil de détection timestamp en ms

DataJson    = dict[str, dict[str, Any]]
DataFeature = dict[str, dict[str, gpd.GeoDataFrame]]


# ──────────────────────────────────────────────────────────────────────────────
# Parsing géométrie
# ──────────────────────────────────────────────────────────────────────────────
def _parse_point(geom: dict[str, Any]) -> Optional[BaseGeometry]:
    x, y = geom.get("x"), geom.get("y")
    if x is None or y is None:
        return None
    return Point(x, y)


def _parse_polygon(geom: dict[str, Any]) -> Optional[BaseGeometry]:
    rings: list = geom.get("rings") or []
    if not rings:
        return None
    # rings[0] = exterior, rings[1:] = trous éventuels
    exterior = rings[0]
    holes    = rings[1:] if len(rings) > 1 else []
    return Polygon(exterior, holes)


_GEOM_PARSERS = {
    "esriGeometryPoint":   _parse_point,
    "esriGeometryPolygon": _parse_polygon,
}


def parse_geometry(geom: dict[str, Any], geom_type: str) -> Optional[BaseGeometry]:
    """Dispatch vers le parser adapté. Retourne None si géométrie invalide."""
    if not geom:
        return None
    parser = _GEOM_PARSERS.get(geom_type)
    if parser is None:
        logger.warning("Type de géométrie non géré : '%s'.", geom_type)
        return None
    try:
        return parser(geom)
    except Exception as exc:
        logger.debug("Erreur parsing géométrie (%s) : %s", geom_type, exc)
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Conversion des timestamps
# ──────────────────────────────────────────────────────────────────────────────
def _convert_timestamps(attrs: dict[str, Any]) -> dict[str, Any]:
    """Convertit les entiers > seuil (ms epoch) en chaîne de date lisible."""
    return {
        k: datetime.fromtimestamp(v / 1_000).strftime("%d-%m-%Y")
        if isinstance(v, (int, float)) and v > _TS_THRESHOLD
        else v
        for k, v in attrs.items()
    }


# ──────────────────────────────────────────────────────────────────────────────
# Conversion features → GeoDataFrame
# ──────────────────────────────────────────────────────────────────────────────
def _features_to_geodataframe(
    features  : list[dict[str, Any]],
    geom_type : str,
    layer_name: str,
) -> gpd.GeoDataFrame:
    rows = []
    for feat in features:
        attrs = _convert_timestamps(dict(feat.get("attributes") or {}))
        attrs["layer"]    = layer_name
        attrs["date_update"] = cfg.timetext
        attrs["geometry"] = parse_geometry(feat.get("geometry") or {}, geom_type)
        rows.append(attrs)

    gdf    = gpd.GeoDataFrame(rows, crs=cfg.CRS)
    n_null = gdf.geometry.isna().sum()
    if n_null:
        logger.warning(
            "Couche '%s' — %d géométrie(s) nulle(s) ignorée(s).", layer_name, n_null
        )
    return gdf[gdf.geometry.notna()].copy()


def extract_data_feature(data_json: DataJson) -> DataFeature:
    """Convertit toutes les features JSON en GeoDataFrames."""
    result: DataFeature = {}

    for svc_name, layers in data_json.items():
        result[svc_name] = {}
        for layer_name, layer_data in layers.items():
            gdf = _features_to_geodataframe(
                features   = layer_data.get("features")  or [],
                geom_type  = layer_data.get("geom_type") or cfg.ARCGIS_GEOM_TYPE,
                layer_name = layer_name,
            )
            result[svc_name][layer_name] = gdf
            logger.info(
                "✅ '%s / %s' → %d feature(s) valide(s).",
                svc_name, layer_name, len(gdf),
            )

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Fusion de plusieurs groupes de GeoDataFrames
# ──────────────────────────────────────────────────────────────────────────────
def merge_geodataframes(*groups: dict[str, gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    """
    Fusionne N groupes {layer_name: GeoDataFrame} en un seul GeoDataFrame.
    - Ignore les GeoDataFrames vides.
    - Exclut les colonnes contenant 'guid'.
    - Préserve l'ordre de première apparition des colonnes.
    """
    gdfs = [
        gdf
        for grp in groups
        for gdf in grp.values()
        if isinstance(gdf, gpd.GeoDataFrame) and not gdf.empty
    ]

    if not gdfs:
        logger.warning("merge_geodataframes — aucun GeoDataFrame non vide.")
        return gpd.GeoDataFrame(geometry=[], crs=cfg.CRS)

    # Colonnes ordonnées, sans doublons, sans guid
    seen : set[str]  = set()
    cols : list[str] = []
    for gdf in gdfs:
        for col in gdf.columns:
            if col not in seen and "guid" not in col.lower():
                cols.append(col)
                seen.add(col)

    merged: gpd.GeoDataFrame = pd.concat(          # type: ignore[assignment]
        [gdf.reindex(columns=cols) for gdf in gdfs],
        ignore_index=True,
    )
    logger.info("Fusion → %d feature(s) au total.", len(merged))
    return merged
