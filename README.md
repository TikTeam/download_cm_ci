## ⛏️ download_cm_ci
> Extraction automatisée des données du cadastre minier, conversion géospatiale et archivage sur Google Drive.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-automatisé-2088FF?logo=github-actions&logoColor=white)](https://docs.github.com/actions)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-green.svg)](LICENSE)

## 🌍 Vue d’ensemble

CadastreExtrac exécute le pipeline suivant :

1. récupération de la page du portail cadastral ;
2. extraction du JSON d’initialisation et des métadonnées des services ArcGIS ;
3. téléchargement paginé des couches et de leurs géométries ;
4. conversion des features en `GeoDataFrame` WGS84 (`EPSG:4326`) ;
5. fusion des groupes **Demandes** et **Licences** ;
6. sauvegarde locale des données et des logs ;
7. upload des fichiers vers un dossier Google Drive.

Le projet est conçu pour une exécution périodique via GitHub Actions, mais peut aussi être lancé localement. Les requêtes ArcGIS utilisent un accès direct puis, si nécessaire, un fallback via proxy et une requête POST en cas de blocage HTTP 405.

> ⚠️ Le portail source et sa structure JSON restent des dépendances externes. Un changement du portail peut nécessiter une adaptation de `parser.py`.
