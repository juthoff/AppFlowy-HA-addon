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
- Fix: appflowy_cloud parst `smtp_email` (Quellcode-Verifikation in `libs/mailer/src/sender.rs`,
  Tag 0.9.64) direkt als Absenderadresse. Das Konfigurationsskript setzte dieses Feld bisher
  fälschlich auf den SMTP-**Benutzernamen** statt auf eine echte Absenderadresse - bei
  Anbietern mit einem nicht-E-Mail-förmigen SMTP-Benutzernamen (z.B. Resend, wo er zwingend
  `resend` sein muss) schlug das Adress-Parsing fehl und E-Mail-Einladungen scheiterten. Nutzt
  jetzt korrekt `smtp_admin_email` als Absenderadresse (wie von GoTrue an anderer Stelle
  bereits gehandhabt).
- `smtp_host` ist jetzt standardmäßig auf `smtp.resend.com` vorbelegt (Port 465/`wrapper`
  passten als Default bereits). [Resend](https://resend.com) wurde als empfohlener
  SMTP-Anbieter recherchiert: Signup verlangt nur eine E-Mail-Adresse, keine weiteren
  persönlichen Daten oder Kreditkarte. API-Key und Absenderadresse (`smtp_admin_email`,
  Domain muss bei Resend verifiziert sein) müssen weiterhin individuell in der
  Add-on-Konfiguration eingetragen werden - sie sind bewusst **nicht** vorbelegt und landen
  nicht im Repository.
- Fix: Das Add-on war nur über `http://localhost:8099` nutzbar, nicht aber von anderen
  Geräten im Netzwerk (z.B. über die Host-IP, wie es beim regulären Betrieb unter Home
  Assistant der Normalfall ist) - die Seite lud zwar, Login/Admin-Konsole schlugen aber
  fehl. Ursache: GoTrue (Quellcode-Verifikation in `internal/api/token.go`, Tag `0.8.0`)
  setzt seine Session-Cookies fest verdrahtet mit dem `Secure`-Attribut. Browser
  akzeptieren `Secure`-Cookies nur über eine als vertrauenswürdig geltende Verbindung;
  `http://localhost` ist dafür eine Sonderausnahme, jede andere Adresse über reines HTTP
  (LAN-IP, Hostname) nicht - und das Add-on spricht bewusst nie selbst HTTPS. Das
  `Secure`-Attribut wird beim Bauen von GoTrue jetzt per `sed`-Patch entfernt (analog zum
  bereits bestehenden Quellcode-Patch für AppFlowy Web im Dockerfile); ein Cookie ohne
  `Secure` funktioniert unverändert auch hinter einem eigenen HTTPS-Reverse-Proxy.
- Fix: Die Desktop-/Mobil-Apps meldeten beim Verbinden mit dem Add-on
  "Connection failed... Health check failed (HTTP 404)". Ursache: appflowy_cloud
  registriert seinen Health-Check unprefixed als `GET /health` (Quellcode-Verifikation in
  `src/application.rs`, Tag `0.9.64`), die Clients fragen ihn aber unter `/api/health` ab.
  `nginx.conf` hatte dafür keine eigene Regel - die Anfrage lief über die generische
  `/api`-Weiterleitung durch, unter der appflowy_cloud diese Route aber nicht kennt (404).
  Ein bloßes `/health` traf zudem mangels eigener Regel den Web-App-Catch-all und lieferte
  irreführend `200` mit der SPA statt einer echten Backend-Antwort. Beide Pfade werden
  jetzt per `location = ...` explizit auf `GET /health` bei appflowy_cloud weitergeleitet.
