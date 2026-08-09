"""
main.py — Point d'entrée unique.
Conçu pour GitHub Actions (cron quotidien) + upload Google Drive.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import src.config as cfg
from src.logging_setup import setup_logger, get_logger
from src import parser, geo, storage


def run() -> int:
    """
    Pipeline complet : fetch → parse → download → convert → save → upload.
    Retourne 0 (succès) ou 1 (erreur critique).
    """
    timestamp = datetime.now(tz=timezone.utc).strftime("%d%m%Y%H%M")
    logger    = setup_logger(log_dir=cfg.LOG_DIR, log_filename=f"cadastre_{timestamp}.log")

    logger.info("══════════════════════════════════════════════════════")
    logger.info("  Cadastre Minier CI — Extraction quotidienne")
    logger.info("  Timestamp UTC : %s", timestamp)
    logger.info("══════════════════════════════════════════════════════")

    try:
        # ── 1. JSON d'initialisation ─────────────────────────────────────────
        logger.info("[1/5] Récupération du JSON d'initialisation…")
        html_json = parser.fetch_init_json(cfg.URL_CADASTRE)

        # ── 2. Métadonnées des services ──────────────────────────────────────
        logger.info("[2/5] Extraction des métadonnées des services…")
        data_info = parser.extract_data_info(html_json)

        # ── 3. Download des features ArcGIS ──────────────────────────────────
        logger.info("[3/5] Téléchargement des features ArcGIS…")
        data_json = parser.extract_data_json(data_info)

        # ── 4. Conversion en GeoDataFrames ───────────────────────────────────
        logger.info("[4/5] Conversion en GeoDataFrames…")
        data_feature = geo.extract_data_feature(data_json)

        # ── 5. Sauvegarde + Upload ────────────────────────────────────────────
        logger.info("[5/5] Sauvegarde locale et upload Google Drive…")
        saved: list[Path] = []

        # Licences : fusion des groupes Demandes + Licences
        licence_groups = {
            k: v for k, v in data_feature.items()
            if k in cfg.LICENCE_GROUPS
        }
        if licence_groups:
            licence_gdf = geo.merge_geodataframes(*licence_groups.values())
            saved.append(storage.save_single(licence_gdf, "Cadastre_Minier_Ci", timestamp))
        else:
            logger.warning("Aucun groupe Demandes/Licences disponible.")

        # Administration : fichier multi-couches
        admin = data_feature.get(cfg.ADMIN_GROUP) or {}
        if admin:
            saved.append(storage.save_layered(admin, "Admin_Ci", timestamp))
        else:
            logger.warning("Aucune couche '%s' disponible.", cfg.ADMIN_GROUP)

        # ✅ Ajouter le fichier `.log` à l'upload
        log_file = Path(cfg.LOG_DIR) / f"cadastre_{timestamp}.log"
        if log_file.exists():
            saved.append(log_file)
            logger.info("📋 Fichier log ajouté : %s", log_file.name)
        else:
            logger.warning("⚠️  Fichier log introuvable : %s", log_file)
        
        # Upload Google Drive
        uploaded = storage.upload_outputs(saved)
        if uploaded:
            logger.info(
                "✅ %d fichier(s) uploadé(s) : %s",
                len(uploaded), list(uploaded.keys()),
            )
        else:
            logger.warning("Aucun fichier uploadé sur Drive.")

        logger.info("══════════════════════════════════════════════════════")
        logger.info("  Pipeline terminé avec succès.")
        logger.info("══════════════════════════════════════════════════════")
        return 0

    except Exception as exc:
        get_logger().exception("❌ ERREUR CRITIQUE : %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(run())
