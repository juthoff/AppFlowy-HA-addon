# Changelog

## 0.9.64-1

- Erste Version. Bündelt AppFlowy-Cloud `0.9.64` (letzte AGPL-3.0-Version vor der
  Kommerzialisierung/Archivierung) vollständig in einem Add-on: PostgreSQL 16 + pgvector,
  Redis, MinIO, GoTrue, appflowy_cloud, appflowy_worker, admin_frontend, AppFlowy Web.
- Build-Fix: MinIO wird nicht mehr per Direkt-Download von `dl.min.io` bezogen (diese
  Downloads wurden von MinIO inzwischen abgeschaltet, HTTP 410), sondern aus dem offiziellen
  `quay.io/minio/minio`-Image kopiert.
- Fix: `/etc` landete im fertigen Image mit `700` statt `755`, weil `COPY rootfs/ /` die
  Berechtigungen 1:1 vom Build-Host übernimmt und das lokale `rootfs/`-Verzeichnis mit einem
  restriktiven umask ausgecheckt/übertragen worden war. Dadurch konnte kein Dienst, der nicht
  als root läuft (Postgres, Redis, GoTrue, ...), noch `/etc/passwd` lesen - `initdb` scheiterte
  mit "could not look up effective user ID". Das Dockerfile setzt die Rechte von `/etc` und den
  Add-on-eigenen Unterverzeichnissen jetzt nach dem `COPY` explizit neu, unabhängig vom
  Host-Zustand; zusätzlich wurden die Rechte im Repository selbst korrigiert.
- Fix: `/data/redis` und `/data/minio` wurden nur zur Build-Zeit im Image angelegt - das ist
  wirkungslos, sobald Home Assistant `/data` als Bind-Mount vom Host überlagert (Bind-Mounts
  werden nie mit Image-Inhalten vorbefüllt). Beide Verzeichnisse werden jetzt beim
  Dienst-Start in den jeweiligen `run`-Skripten angelegt, analog zu Postgres.
- Fix: nginx wartete beim Start per `curl http://127.0.0.1:3000/` auf `admin_frontend`, das
  aber nur unter `/console` antwortet (bare `/` liefert 404) - nginx kam dadurch nie hoch. Der
  Readiness-Check prüft jetzt `/console`.
- Build und Funktionstest (Docker, arm64) erfolgreich durchgeführt: alle Dienste starten
  fehlerfrei, `/`, `/console` (Redirect zu `/console/web/login`) und der GoTrue-Login
  (`/gotrue/token`) wurden verifiziert; Daten/Login überleben einen Container-Neustart.
