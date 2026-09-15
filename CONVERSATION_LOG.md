# Chat-Verlauf: AppFlowy Home Assistant Add-on

Diese Datei fasst den Chatverlauf (Anfragen und Ergebnisse) zusammen, damit die Arbeit auf
einem anderen Gerät fortgesetzt werden kann. Die eigentlichen erstellten Dateien liegen als
Add-on-Repository neben dieser Datei (Ordner `appflowy/`, `repository.yaml`, `README.md`).

---

## 1. Ausgangsanfrage

> Erstelle eine HomeAssistant Add-On, basierend auf folgendem link:
> https://github.com/AppFlowy-IO/AppFlowy
>
> Das Add-On soll vollständig sein, und keine weiteren Add-Ons benötigen. Dies Beinhaltet auch
> Datenbanken, die bei AppFlowy genutzt werden.

**Ergebnis der Recherche:** Der verlinkte Link ist nur der AppFlowy-Client. Der eigentliche
Server ("AppFlowy-Cloud", https://github.com/AppFlowy-IO/AppFlowy-Cloud) wurde am **11.09.2026
archiviert** und auf ein **kommerziell lizenziertes** Repository umgestellt
(`AppFlowy-IO/AppFlowy-SelfHost-Commercial`). Dessen Lizenz verbietet Kopieren, Verändern und
Weiterverteilen der Software und verlangt einen an eine Maschine gebundenen Lizenzschlüssel –
ein selbstgebautes, weiterverteilbares Home-Assistant-Add-on lässt sich darauf nicht rechtmäßig
stützen.

## 2. Rückfrage zur Lizenzproblematik

Drei Optionen wurden zur Auswahl gestellt:
1. Letzte AGPL-Version verwenden (empfohlen)
2. Trotzdem die kommerzielle Version einbauen (eigener Lizenzschlüssel nötig)
3. Abbrechen / erst mehr Infos

**Nutzerfrage:** "Von wann ist die letzte AGPL-3.0 Version?"

**Antwort:** Letzter Versions-Tag im noch AGPL-3.0-lizenzierten Repo: **0.9.64 vom 4. Juli
2025**. Danach nur noch Commits zur Lizenz-Erkennung (ab Oktober 2025) bzw. reine
README-Hinweise auf das neue Repo (ab August 2026). Archiviert wurde das Repo am 11.09.2026.

**Nutzerfrage:** "Ist bekannt, welche Features in der letzten AGPL-3.0 Version vorhanden sind,
welche in der aktuell kommerziellen Version nicht mehr vorhanden sind?"

**Antwort (Kernpunkte):**
- Die 1-Seat-Nutzerbegrenzung existierte schon vor der Kommerzialisierung (seit ca. September
  2025, also kurz nach 0.9.64) – nicht erst seit dem Lizenzwechsel im September 2026.
- Ursprünglich (Stand September 2024) war Self-Hosting laut einem AppFlowy-Mitarbeiter
  "completely free" ohne Seat-Limit.
- Eingeschränkt in der kommerziellen Version: unbegrenzte Nutzer-Seats (jetzt: 1 Seat + max. 3
  Gäste), Enterprise-SSO (SCIM/LDAP/SAML) nur noch im bezahlten "Seed"-Plan.
- Neu in der kommerziellen Version: formales Lizenzserver-/Lizenzschlüsselsystem,
  Signup-Whitelisting, KI-Admin-Schalter.
- Nicht zweifelsfrei verifizierbar: ob genau Tag 0.9.64 den Lizenz-Check-Code schon enthielt.

## 3. Entscheidung des Nutzers

> Nutze AGPL-Basis ohne Seat-Limit-Patch und erstelle daraus wie zu Beginn festgelegt ein
> HomeAssistant Add-On

→ Es wurde **kein** Patch vorgenommen, um irgendein Seat-Limit zu entfernen; der Code des
AGPL-Tags 0.9.64 wurde unverändert übernommen (nur Konfiguration/Orchestrierung als eigener
Code hinzugefügt).

## 4. Technische Recherche vor dem Bau

- Docker-Compose-Struktur, `deploy.env`, `nginx.conf`, Dockerfiles (appflowy_cloud,
  admin_frontend, appflowy_worker, gotrue, appflowy_web) wurden direkt aus dem Git-Tag
  `0.9.64` von `AppFlowy-IO/AppFlowy-Cloud` geladen und ausgewertet.
- Über die Docker-Hub-API wurden für `appflowy_cloud`, `admin_frontend` und `appflowy_worker`
  die exakten, seit 2025-07-04 **unveränderten** Image-Digests (amd64 + arm64) ermittelt und
  verifiziert (`tag_last_pushed == last_updated`).
- `gotrue` (AppFlowy-Fork von Supabase Auth, MIT-Lizenz) und `AppFlowy Web`
  (AGPL-3.0, eigenständiges, nicht archiviertes Repo) werden stattdessen direkt aus dem
  Quellcode gebaut (Branch/Tag `0.8.0` bzw. `v0.1.18`, passend zum Juli-2025-Stand).
- `appflowy_ai` (optionale KI-Chat-Funktion) wurde bewusst **ausgeklammert**, da dessen
  Docker-Images zeitlich nicht im Gleichschritt mit dem restlichen 0.9.64-Release standen und
  kein zuverlässiger Versions-Pin möglich war.
- Kein Docker verfügbar in der Arbeitsumgebung → das Ergebnis wurde sorgfältig aus den
  Original-Dockerfiles/Compose-Dateien abgeleitet, aber **nicht selbst gebaut/getestet**.

## 5. Erstelltes Add-on (Architektur-Zusammenfassung)

Ein einzelner Container (s6-overlay als Prozess-Supervisor) mit folgenden Diensten:

- PostgreSQL 16 + pgvector (Debian-Pakete über apt.postgresql.org/PGDG)
- Redis (Debian-Paket)
- MinIO (S3-kompatibler Objektspeicher, aktuelles Release-Binary)
- GoTrue (Login/Auth, aus Quellcode gebaut, Branch `0.8.0`)
- appflowy_cloud (API/Echtzeit-Sync, aus gepinntem Docker-Hub-Digest extrahiert)
- appflowy_worker (Hintergrundjobs, aus gepinntem Docker-Hub-Digest extrahiert)
- admin_frontend (Admin-Konsole, aus gepinntem Docker-Hub-Digest extrahiert)
- AppFlowy Web (Browser-Client, statischer Build aus Quellcode, `v0.1.18`)
- nginx (reverse proxy, fasst alles auf einem Port zusammen)

Persistente Daten liegen im Add-on-eigenen `/data`-Verzeichnis (Postgres, MinIO, generierte
Geheimnisse) und bleiben bei Neustarts/Updates erhalten.

Details, Konfigurationsoptionen und bekannte Einschränkungen: siehe `appflowy/DOCS.md`.
Herkunfts- und Lizenznachweis jeder Komponente: siehe `appflowy/NOTICE.md`.

## 6. Geänderte/erstellte Dateien

```
repository.yaml
README.md
appflowy/config.yaml
appflowy/build.yaml
appflowy/Dockerfile
appflowy/DOCS.md
appflowy/NOTICE.md
appflowy/CHANGELOG.md
appflowy/rootfs/etc/nginx/nginx.conf
appflowy/rootfs/etc/cont-init.d/10-config.sh
appflowy/rootfs/etc/cont-init.d/20-postgres.sh
appflowy/rootfs/etc/services.d/postgres/run
appflowy/rootfs/etc/services.d/redis/run
appflowy/rootfs/etc/services.d/minio/run
appflowy/rootfs/etc/services.d/gotrue/run
appflowy/rootfs/etc/services.d/appflowy_cloud/run
appflowy/rootfs/etc/services.d/appflowy_worker/run
appflowy/rootfs/etc/services.d/admin_frontend/run
appflowy/rootfs/etc/services.d/nginx/run
```

## 7. Docker-Build/Test (auf einem zweiten Gerät, macOS/Apple Silicon, fortgesetzt)

Auf einem anderen Rechner (macOS, arm64, Docker Desktop bereits installiert) wurde der in
Punkt 7 offen gelassene Build- und Funktionstest durchgeführt (`docker buildx build --platform
linux/arm64 -t appflowy-addon-test --load .`, danach Container mit simuliertem
`/data/options.json` gestartet und über `curl` durchgetestet). Dabei wurden vier reale Bugs
gefunden und behoben, die beim rein statischen Ableiten aus den Original-Dateien (ohne
tatsächlichen Build/Lauf, siehe Punkt 4) nicht auffallen konnten:

1. **MinIO-Download tot**: `https://dl.min.io/server/minio/release/<arch>/minio` liefert
   inzwischen HTTP 410 (Gone) - MinIO hat die Direkt-Binary-Downloads abgeschaltet und auch den
   `minio/minio`-Docker-Hub-Namespace entfernt. Fix: Binary wird jetzt per Multi-Stage-`COPY`
   aus dem offiziellen `quay.io/minio/minio:latest`-Image bezogen.
2. **`/etc` mit `700` statt `755` im fertigen Image**: `COPY rootfs/ /` im Dockerfile übernimmt
   die exakten Unix-Berechtigungen des lokalen `appflowy/rootfs/`-Verzeichnisses vom Build-Host.
   Dieses lag (vermutlich durch Erstellung/Transfer mit restriktivem umask 077 auf dem ersten
   Gerät) komplett mit `700` vor und hat dadurch beim Build `/etc` von `755` auf `700`
   überschrieben - kein Nicht-Root-Dienst (Postgres, Redis, GoTrue, ...) konnte danach noch
   `/etc/passwd` lesen (`initdb: could not look up effective user ID ...: Permission denied`).
   Fix: Rechte im Repository korrigiert (Verzeichnisse 755, Dateien 644, Skripte 755) UND das
   Dockerfile setzt `/etc`, `/etc/nginx`, `/etc/cont-init.d`, `/etc/services.d/*` nach dem
   `COPY` zusätzlich explizit neu, damit das künftig nicht mehr vom Host-Zustand abhängt.
3. **`/data/redis` und `/data/minio` fehlten zur Laufzeit**: Diese Verzeichnisse wurden nur zur
   Build-Zeit im Image angelegt - wirkungslos, sobald Home Assistant `/data` als Bind-Mount vom
   Host überlagert (Bind-Mounts zeigen immer den tatsächlichen, ggf. leeren Host-Ordner, nie den
   Image-Inhalt an dieser Stelle). Fix: Beide `run`-Skripte legen ihr Datenverzeichnis jetzt
   selbst beim Dienst-Start an (wie es `20-postgres.sh` für Postgres bereits tat).
4. **nginx startete nie**: Der Readiness-Check wartete auf `curl http://127.0.0.1:3000/`
   (admin_frontend), aber admin_frontend beantwortet nur `/console/*` (bare `/` → 404) - die
   Warteschleife lief endlos. Fix: Check auf `/console` umgestellt (liefert 308).

Nach allen vier Fixes: Build läuft sauber durch, alle acht Dienste starten fehlerfrei, `/`
(AppFlowy Web), `/console` (Redirect zu `/console/web/login`) und der GoTrue-Login
(`POST /gotrue/token?grant_type=password`) wurden per `curl` end-to-end verifiziert (gültiges
JWT erhalten). Ein Container-Neustart mit demselben Volume zeigte, dass Postgres-Daten,
generierte Secrets und der Admin-Login den Neustart überstehen. Details siehe
`appflowy/CHANGELOG.md`.

**Offen/nicht getestet:** amd64-Architektur (nur arm64 lokal gebaut/getestet, amd64-Digests
sind aber identisch bezogen und sollten funktionieren); echter Betrieb unter dem
Home-Assistant-Supervisor selbst (nur simuliert via `docker run` + manuell befülltem
`/data/options.json`); SMTP/OAuth-Optionen; MinIO-Objektupload/-Download über die
AppFlowy-Clients (nur der Bucket-Anlage-Log wurde verifiziert, kein echter Datei-Upload).
