# NOTICE - Herkunft und Lizenzen der gebündelten Komponenten

Dieses Add-on bündelt mehrere unabhängige Open-Source-Projekte in einem Container. Es verändert
deren Quellcode nicht (nur Konfiguration/Orchestrierung), mit Ausnahme der in der Ursprungs-
Dokumentation selbst vorgesehenen Build-Anpassung an `AppFlowy-Web` (Entfernen einer
hart-codierten Test-API-URL, siehe `docker/web/Dockerfile` im AppFlowy-Cloud-Repository).

| Komponente | Quelle | Referenz | Lizenz |
|---|---|---|---|
| appflowy_cloud | `appflowyinc/appflowy_cloud` (Docker Hub) | Tag `0.9.64`, Digest `sha256:ded3da3a25fe7a76c28108adb9849b8aa0ce02b0da5898bc7dd58a09c00e5139` (amd64) / `sha256:0b0f11031b6787579148e3138f152485c12f8aba1c228cb5bbccde1a521e16d2` (arm64), gepusht 2025-07-04 | AGPL-3.0 |
| admin_frontend | `appflowyinc/admin_frontend` (Docker Hub) | Digest `sha256:443d92faa034b002a1c71e6692245f7a3dcc352f55e4c6dcfdd4b1aa53eaf063` (amd64) / `sha256:1e79dcf3efe6425228fef075afd7a11e344189da43e5a958d670fa01513d6f99` (arm64), gepusht 2025-07-04 | AGPL-3.0 |
| appflowy_worker | `appflowyinc/appflowy_worker` (Docker Hub) | Digest `sha256:e9bcb9f712b2fb75318674fa874c0ef460d7b3b7487c99560f2b5ce5564991d2` (amd64) / `sha256:7986e875e4fc825c73de0bad7a58f464ae81019c6c6bdb2c3c0c5790df69b4f5` (arm64), gepusht 2025-07-04 | AGPL-3.0 |
| Quellcode (appflowy_cloud/admin_frontend/appflowy_worker) | https://github.com/AppFlowy-IO/AppFlowy-Cloud | Git-Tag `0.9.64` | AGPL-3.0 |
| gotrue (Auth) | https://github.com/AppFlowy-IO/auth | Branch/Tag `0.8.0`, aus Quellcode gebaut | MIT |
| AppFlowy Web | https://github.com/AppFlowy-IO/AppFlowy-Web | Tag `v0.1.18`, aus Quellcode gebaut | AGPL-3.0 |
| PostgreSQL | Debian-Paket `postgresql-16` | apt.postgresql.org (PGDG) | PostgreSQL-Lizenz |
| pgvector | Debian-Paket `postgresql-16-pgvector` | apt.postgresql.org (PGDG) | PostgreSQL-Lizenz |
| Redis | Debian-Paket `redis-server` | Debian bookworm | RSALv2/SSPLv1/AGPL-3.0 (je Version) |
| MinIO | `quay.io/minio/minio` (offizielles Multi-Arch-Image) | Binary `/usr/bin/minio`, Tag `latest`, jeweils aktuellstes stabiles Release zum Build-Zeitpunkt | AGPL-3.0 |
| nginx | Debian-Paket `nginx` | Debian bookworm | BSD-2-Clause |
| s6-overlay | https://github.com/just-containers/s6-overlay | v3.2.3.2 | ISC |

## Warum diese Version und nicht die aktuelle?

`AppFlowy-IO/AppFlowy-Cloud` wurde am 11.09.2026 archiviert; der README-Hinweis des Repos
verweist seitdem ausschließlich auf `AppFlowy-IO/AppFlowy-SelfHost-Commercial`, dessen
`SELF_HOST_LICENSE_AGREEMENT.md` Kopieren, Verändern und Weiterverteilen der Software
ausdrücklich untersagt und einen an eine Maschine gebundenen Lizenzschlüssel voraussetzt.
Ein Home-Assistant-Add-on – das per Definition weiterverteilbarer, veränderbarer Code ist –
lässt sich darauf nicht rechtmäßig aufbauen.

`0.9.64` (04.07.2025) ist der letzte Versions-Tag des Repos, der noch unter der ursprünglichen
AGPL-3.0-Lizenz stand. Alle oben verlinkten Docker-Hub-Digests wurden über die Docker-Hub-API
verifiziert: `tag_last_pushed` entspricht exakt `last_updated`, d. h. keiner dieser Layer wurde
nach dem 04.07.2025 verändert.

## AGPL-3.0-Hinweis (§13, Netzwerknutzung)

Der vollständige, unveränderte Quellcode von appflowy_cloud, admin_frontend und appflowy_worker
in der hier verwendeten Version steht unter der oben verlinkten Tag-Referenz
(`https://github.com/AppFlowy-IO/AppFlowy-Cloud/tree/0.9.64`) zur Verfügung. Dieses Add-on
selbst (Dockerfile, Konfigurationsskripte, nginx-Konfiguration) ist eigener Code des Add-on-
Autors und liegt im selben Repository wie dieses NOTICE.md.
