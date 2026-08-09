"""
storage.py — Sauvegarde locale (GPKG/SHP) + upload Google Drive.
"""
from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Optional

import geopandas as gpd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import src.config as cfg

logger = logging.getLogger("cadastre.storage")

_DRIVERS: dict[str, str] = {
    ".gpkg": "GPKG",
    ".shp":  "ESRI Shapefile",
}
_GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


# ──────────────────────────────────────────────────────────────────────────────
# Chemins de sortie
# ──────────────────────────────────────────────────────────────────────────────
def _output_path(name: str, suffix: str, timestamp: str) -> Path:
    cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return cfg.DATA_DIR / f"{name}_{timestamp}{suffix}"


# ──────────────────────────────────────────────────────────────────────────────
# Sauvegarde locale
# ──────────────────────────────────────────────────────────────────────────────
def save_layered(
    layers   : dict[str, gpd.GeoDataFrame],
    name     : str,
    timestamp: str,
    fmt      : str = ".gpkg",
    encoding : str = "utf-8",
) -> Optional[Path]:
    """
    Sauvegarde un dict {couche: GeoDataFrame} dans un fichier multi-couches.
    Retourne le chemin créé ou None si rien à sauvegarder.
    """
    if not layers:
        logger.warning("save_layered('%s') — dict vide.", name)
        return None

    driver  = _DRIVERS.get(fmt, "GPKG")
    path    = _output_path(name, fmt, timestamp)
    written = 0

    for layer_name, gdf in layers.items():
        if gdf.empty:
            logger.warning("Couche '%s' vide — ignorée.", layer_name)
            continue
        # GPKG supporte l'ajout de couches (mode "a"), SHP nécessite "w"
        mode = "a" if fmt == ".gpkg" else "w"
        gdf.to_file(str(path), layer=layer_name, driver=driver, encoding=encoding, mode=mode)
        logger.info("  ↳ Couche '%s' écrite → %s", layer_name, path.name)
        written += 1

    if written:
        logger.info("✅ '%s' sauvegardé (%d couche(s)).", path.name, written)
        return path

    logger.warning("Aucune couche non-vide à écrire pour '%s'.", name)
    return None


def save_single(
    gdf      : gpd.GeoDataFrame,
    name     : str,
    timestamp: str,
    fmt      : str = ".gpkg",
    encoding : str = "utf-8",
) -> Optional[Path]:
    """Sauvegarde un GeoDataFrame unique. Retourne le chemin ou None."""
    if gdf.empty:
        logger.warning("save_single('%s') — GeoDataFrame vide.", name)
        return None

    driver = _DRIVERS.get(fmt, "GPKG")
    path   = _output_path(name, fmt, timestamp)
    gdf.to_file(str(path), driver=driver, encoding=encoding, mode="w")
    logger.info("✅ '%s' sauvegardé (%d features).", path.name, len(gdf))
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Google Drive — Authentification OAuth 2.0
# ──────────────────────────────────────────────────────────────────────────────
def _build_drive_service():
    """
    Authentification OAuth 2.0 uniquement (pas de Service Account).
    """
    client_id = os.getenv('GDRIVE_CLIENT_ID')
    client_secret = os.getenv('GDRIVE_CLIENT_SECRET')
    refresh_token = os.getenv('GDRIVE_REFRESH_TOKEN')
    
    if not all([client_id, client_secret, refresh_token]):
        logger.error("❌ Secrets OAuth manquants")
        raise ValueError(
            "GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN "
            "doivent être définis"
        )
    
    logger.info("Drive auth : OAuth 2.0 (refresh token).")
    
    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=_GDRIVE_SCOPES,  # ✅ Doit correspondre au token généré
        )
        
        # Rafraîchir immédiatement pour vérifier
        request = Request()
        creds.refresh(request)
        
        return build("drive", "v3", credentials=creds, cache_discovery=False)
        
    except Exception as e:
        logger.error(f"❌ Erreur OAuth : {e}")
        raise

# ──────────────────────────────────────────────────────────────────────────────
# Google Drive — Opérations fichiers
# ──────────────────────────────────────────────────────────────────────────────
def _list_drive_files(service, folder_id: str, name_prefix: str) -> list[dict]:
    """Liste les fichiers d'un dossier Drive dont le nom commence par `name_prefix`."""
    query = (
        f"'{folder_id}' in parents "
        f"and name contains '{name_prefix}' "
        f"and trashed=false"
    )
    result = service.files().list(
        q=query,
        fields="files(id, name, createdTime)",
        orderBy="createdTime desc",
    ).execute()
    return result.get("files") or []


def _delete_old_files(service, files: list[dict], keep: int) -> None:
    """Supprime les fichiers excédentaires (conserve les `keep` plus récents)."""
    for f in files[keep:]:
        service.files().delete(fileId=f["id"]).execute()
        logger.info("🗑️  Fichier Drive supprimé : %s", f["name"])


def upload_to_drive(local_path: Path, folder_id: Optional[str] = None) -> Optional[str]:
    """
    Upload un fichier local sur Google Drive.
    
    Args:
        local_path: Chemin du fichier local à uploader
        folder_id: ID du dossier Drive (par défaut : DRIVE_FOLDER_ID)
    
    Returns:
        ID du fichier Drive uploadé, ou None en cas d'erreur
    """
    folder_id = folder_id or os.getenv("DRIVE_FOLDER_ID")
    
    if not folder_id:
        logger.error("DRIVE_FOLDER_ID non défini — upload ignoré.")
        return None
    
    if not local_path.exists():
        logger.error("Fichier introuvable pour upload : %s", local_path)
        return None

    try:
        service = _build_drive_service()
        mime_type = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"

        # Préparer et uploader le fichier
        logger.info("📤 Upload en cours : %s", local_path.name)
        metadata = {"name": local_path.name, "parents": [folder_id]}
        media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=True)
        
        result = service.files().create(
            body=metadata,
            media_body=media,
            fields="id, name"
        ).execute()

        file_id: str = result["id"]
        logger.info("✅ Upload Drive OK : %s (id=%s)", result["name"], file_id)

        return file_id

    except Exception as exc:
        logger.error("❌ Échec upload Drive (%s) : %s", local_path.name, exc)
        return None


def upload_outputs(paths: list[Optional[Path]]) -> dict[str, str]:
    """
    Upload une liste de fichiers locaux sur Drive.
    
    Ignore les None et les formats absents de GDRIVE_UPLOAD_FORMATS.
    
    Returns:
        {filename: drive_id}
    """
    results: dict[str, str] = {}
    
    upload_formats = getattr(cfg, "GDRIVE_UPLOAD_FORMATS", [".gpkg", ".shp"])
    
    for path in paths:
        if path is None:
            continue

        # ✅ LOGS toujours uploadés, même hors GDRIVE_UPLOAD_FORMATS
        is_log = path.suffix == ".log"
        is_valid_format = path.suffix in upload_formats

        if not (is_log or is_valid_format):
            logger.debug(
                "Format '%s' ignoré (hors GDRIVE_UPLOAD_FORMATS).", 
                path.suffix
            )
            continue
        
        if not path.exists():
            logger.warning("⏭️  Fichier introuvable : %s", path)
            continue
        
        drive_id = upload_to_drive(path)
        if drive_id:
            results[path.name] = drive_id
            emoji = "📋" if is_log else "📦"
            logger.info("%s Uploadé : %s → %s", emoji, path.name, drive_id)
        else:
            logger.error("❌ Échec upload : %s", path.name)
    
    return results
