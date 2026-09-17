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

## 0.9.64-2

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

## 0.9.64-3

- Fix: Die Desktop-/Mobil-Apps meldeten "Something went wrong. Please try again later." beim
  Verbinden und Einloggen, sowohl mit dem Admin-Konto als auch mit neu angelegten Konten -
  reproduzierbar anhand eines vom Nutzer bereitgestellten Add-on-Logs. Ursache:
  `appflowy_cloud` wurde wiederholt mitten in laufenden Anfragen beendet (Postgres protokolliert
  dabei `unexpected EOF on client connection with an open transaction`, ohne vorausgehendes
  `received graceful shutdown signal` und ohne Rust-Panic-Trace im Log) - das Muster eines von
  außen (typischerweise dem Linux-OOM-Killer) beendeten Prozesses. `s6` startet den Dienst zwar
  automatisch binnen 1-2 Sekunden neu, doch alle Anfragen in diesem Fenster (Login, Health-Check,
  Workspace laden) schlagen mit einem generischen Fehler fehl - betroffen sind dadurch auch
  gleichzeitige Anfragen anderer, an sich unbeteiligter Konten. Die Abstürze fielen konsistent mit
  speicherintensiven Vorgängen zusammen (neues Konto samt Workspace anlegen, Dokumente per
  WebSocket öffnen) auf einem Raspberry Pi mit 2-4GB RAM, auf dem dieses Add-on zusammen mit Home
  Assistant selbst läuft. Postgres, Redis und appflowy_cloud liefen bisher ohne jede
  Speicherbegrenzung (Postgres mit reinen Server-Standardwerten, Redis komplett unbegrenzt) - jetzt
  konfiguriert: Postgres mit `shared_buffers=32MB`/`work_mem=4MB`/`maintenance_work_mem=32MB`
  (`rootfs/etc/services.d/postgres/run`), Redis mit `--maxmemory 128mb
  --maxmemory-policy allkeys-lru` (`rootfs/etc/services.d/redis/run`), und
  `APPFLOWY_DATABASE_MAX_CONNECTIONS` von 40 auf 15 gesenkt (`rootfs/etc/cont-init.d/10-config.sh`),
  passend für den typischen Heimnetz-Einsatz mit wenigen Nutzern.

## 0.9.64-4

- Nachfolge-Fix zu 0.9.64-3: Nach der dortigen Speicher-Anpassung trat der Absturz beim ersten
  Login eines Kontos (egal ob Admin- oder neu angelegtes Konto, auf einer frisch initialisierten
  Datenbank) weiterhin **jedes Mal** exakt an derselben Stelle auf - direkt nach dem Anlegen der
  Nutzerrolle in `verify_token` (`src/biz/user/user_verify.rs`, Quellcode-Verifikation Tag
  `0.9.64`), während appflowy_cloud im Anschluss die "Getting Started"-Vorlage für den neuen
  Workspace anlegt (`initialize_workspace_for_user`). Anhand eines vollständigen, vom Nutzer
  bereitgestellten Logs vom Container-Start bis zum Fehler ließ sich das eingrenzen: Der erste
  Datenbank-Transaktionsblock (Nutzer anlegen) committet nachweislich erfolgreich (ein erneuter
  Login-Versuch überspringt "create new user" bereits), aber der zweite Block (Vorlagen-Inhalte
  anlegen) wird nie fertig - appflowy_cloud stirbt dabei lautlos (kein Rust-Panic-Trace trotz
  `RUST_BACKTRACE=1`, kein reguläres Shutdown-Log), `s6` startet den Dienst neu. Ob Ursache
  weiterhin Speicherdruck ist oder ein architekturspezifischer (aarch64) Absturz in der
  CRDT-Kodierung, ließ sich aus dem Log allein nicht abschließend klären - das wird mit dem
  Nutzer anhand des Arbeitsspeicher-Graphen (Einstellungen → System → Hardware) und der
  Host-System-Logs weiter untersucht.
- In der Zwischenzeit weitere, unabhängig von der Ursache sinnvolle Ressourcen-Reduktion in
  `rootfs/etc/cont-init.d/10-config.sh`: appflowy_cloud öffnet für seinen Redis-Stream-Router
  standardmäßig **60** eigene Redis-Verbindungen samt Threads (`APPFLOWY_REDIS_WORKERS`,
  Quellcode-Verifikation in `src/config/config.rs`, Tag `0.9.64`) - für einen
  Heimnetz-Einsatz mit wenigen Nutzern deutlich überdimensioniert, jetzt auf `4` gesenkt.
  Außerdem wird der KI-Indexer (`APPFLOWY_INDEXER_ENABLED`) jetzt explizit deaktiviert, da
  dieses Add-on ohnehin keinen OpenAI-/Azure-Schlüssel konfiguriert und der Indexer damit
  wirkungslos ist, aber weiterhin bei jedem neuen Collab-Dokument Puffer/Threads reserviert.

## 0.9.64-5

- **Tatsächliche Ursache gefunden und behoben** für den in 0.9.64-3/-4 beschriebenen Absturz
  beim ersten Login eines Kontos: Es war nie Speicherdruck. Der Nutzer bestätigte anhand des
  Arbeitsspeicher-Verlaufs (Einstellungen → System → Hardware) und der Host-System-Logs, dass
  weder eine Speicherspitze noch eine OOM-Meldung zum Absturzzeitpunkt auftrat. Recherche in
  den (weiterhin lesbaren) GitHub-Issues des archivierten AppFlowy-Cloud-Repos ergab eine exakte
  Übereinstimmung: [Issue #1623](https://github.com/AppFlowy-IO/AppFlowy-Cloud/issues/1623)
  beschreibt denselben Absturz (Exit-Code 132 = SIGILL/"illegal instruction", kein Rust-Panic,
  kein sauberes Shutdown-Log) beim Datei-Upload auf einem Raspberry Pi - Ursache: Das
  appflowy_cloud-Release-Binary wurde mit CPU-Krypto-/AES-/SHA-Erweiterungen kompiliert, die der
  jeweilige ARM-Kern nicht unterstützt; sobald Code diesen Instruktionspfad ausführt (bei uns:
  jeder Datei- bzw. Collab-Upload zu MinIO über den appflowy_cloud/appflowy_worker-eigenen
  `aws-sdk-s3`-Client, z.B. beim Anlegen der "Getting Started"-Vorlage für einen neuen
  Account), stürzt der Prozess sofort und lautlos ab.
- Fix: `appflowy_cloud` und `appflowy_worker` werden für `arm64` jetzt **aus dem Quellcode**
  gebaut (Tag `0.9.64`, AGPL-3.0, exakt nach dem Build-Rezept aus AppFlowy-Clouds eigenem
  Dockerfile: `cargo build --release`, `SQLX_OFFLINE=true`, `protobuf-compiler`/`lld`/`clang`),
  statt wie bisher das vorgefertigte Docker-Hub-Image zu verwenden - mit
  `RUSTFLAGS="-C target-feature=-crypto,-aes,-sha2,-sha3"` (der im Issue vorgeschlagene Fix), um
  genau die CPU-Erweiterungen abzuschalten, die den Absturz auslösen. `amd64` ist von diesem
  Problem nicht betroffen und bleibt beim vorgefertigten Image; `admin_frontend` nutzt den
  betroffenen S3-Upload-Codepfad nicht und bleibt auf beiden Architekturen vorgefertigt.
  Achtung: Da dieses Add-on ohne registrierten `image:`-Eintrag lokal auf dem Home-Assistant-Host
  gebaut wird, läuft dieser Rust-Kompilierlauf jetzt beim Bauen/Aktualisieren direkt auf dem
  Gerät selbst (z.B. dem Raspberry Pi) und dauert dadurch spürbar länger als zuvor.

## 0.9.64-6

- Löst den in `0.9.64-5` neu entstandenen Nachteil (spürbar längere Build-Zeit direkt auf dem
  Home-Assistant-Gerät, weil `appflowy_cloud`/`appflowy_worker` auf `aarch64` seitdem aus dem
  Quellcode gebaut werden): Das komplette Add-on-Image wird jetzt per GitHub Actions
  (`.github/workflows/build.yaml`) vorgefertigt gebaut und nach
  [GHCR](https://ghcr.io/juthoff/appflowy) veröffentlicht - der Rust-Kompilierlauf für `aarch64`
  läuft dabei weiterhin (mit denselben `RUSTFLAGS`, die den SIGILL-Fix aus `0.9.64-5`
  ausmachen), aber einmalig auf GitHubs eigener Build-Infrastruktur statt auf jedem einzelnen
  Nutzergerät. `config.yaml` verweist jetzt über ein `image:`-Feld auf dieses vorgefertigte
  Image; Home Assistant Supervisor lädt es nur noch herunter, statt es selbst zu bauen.
  Architektur: `amd64` und `aarch64` werden auf GitHubs jeweils nativen Runnern gebaut (kein
  QEMU nötig, u.a. dank nativer `aarch64`-Runner), die beiden Architektur-Images werden
  anschließend zu einem einzigen Multi-Arch-Manifest zusammengeführt und mit Cosign signiert.
  **Wichtig (einmaliger manueller Schritt):** GitHub veröffentlicht neue Container-Pakete unter
  einem persönlichen Account standardmäßig als **privat** - nach dem ersten erfolgreichen
  Workflow-Lauf müssen die drei entstandenen Pakete (`amd64-appflowy`, `aarch64-appflowy`,
  `appflowy`) unter github.com/juthoff im Reiter "Packages" jeweils manuell auf "Public"
  gestellt werden, sonst kann Supervisor das Image nicht ohne Zugangsdaten herunterladen.

## 0.9.64-7

- Nur Dokumentation, keine Änderung am Image. Neuer Eintrag unter "Bekannte Probleme" in
  DOCS.md: Desktop-/Mobil-Apps ab ca. `0.10` (verifiziert mit Desktop `0.14.3` auf macOS)
  zeigen den persönlichen Workspace eines angemeldeten Kontos leer bzw. schreibgeschützt an,
  `+` legt scheinbar keine Seite an – ein anonymes/lokales Konto funktioniert dagegen. Ursache
  ist **kein** Serverfehler, sondern eine Inkompatibilität: Neuere Apps laden die Seitenleiste
  ausschließlich über HTTP-Endpunkte (`/api/workspace/<id>/view/<id>`, `.../navigation`,
  `.../collab/<id>/permission`, `/api/server-info` u.a.), die es erst im kommerziellen,
  nicht mehr quelloffenen AppFlowy-Cloud nach `0.9.64` gibt; nginx antwortet darauf mit `404`
  (sichtbar in `/var/log/nginx/access.log` im Container). Das Anlegen einer Seite gelingt
  serverseitig sogar, die App kann den Seitenbaum danach aber nicht zurücklesen. Ein Nachbau
  in nginx ist nicht möglich, die App hat keinen Fallback. Abhilfe: das mitgelieferte AppFlowy
  Web nutzen oder eine App aus der Zeit des `0.9.64`-Servers (Desktop `0.9.4`/`0.9.5`, Juli
  2025 – gegen genau den in `0.9.64` enthaltenen Client-API-Stand gebaut; verifiziert mit
  Desktop `0.9.5`: Login, Workspace-Anlage, Seitenbaum und Realtime-Sync fehlerfrei). DOCS.md
  enthält dazu Download-/winget-Anleitung für macOS und Windows, die zu entfernenden lokalen
  Datenordner und den Hinweis, In-App-Updates abzulehnen. "Ersteinrichtung" verweist jetzt auf
  diese Versionsgrenze.

## 0.9.64-8

- **Fix (wirklich) für den SIGILL-Absturz von `appflowy_cloud` auf dem Raspberry Pi 4** beim
  ersten Login eines Kontos bzw. bei jedem ersten Upload nach MinIO (Symptome: Desktop-App
  "Record not found", Admin-Konsole erst beim zweiten Login-Versuch, im Add-on-Log ein
  `[appflowy_cloud] waiting for gotrue...` mitten im Betrieb ohne Panic-Trace, direkt nach
  Postgres' `unexpected EOF on client connection with an open transaction`). Der Absturz trat
  auch mit `0.9.64-6`/`-7` auf; der in `0.9.64-5` eingebaute "Fix" war nie mit einem echten
  Erst-Login getestet worden und konnte prinzipiell nicht wirken.
- Tatsächliche Ursache (im Quellcode der beteiligten Crates verifiziert): `aws-sdk-s3` →
  `aws-smithy-checksums 0.63.3` → **`crc-fast 1.2.1`**, so in AppFlowy-Clouds `Cargo.lock` für
  Tag `0.9.64` festgepinnt. `crc-fast 1.2.1` hat auf `aarch64` **keine
  Laufzeit-Erkennung** der CPU-Fähigkeiten: `src/arch/mod.rs` springt immer in Funktionen mit
  `#[target_feature(enable = "neon,aes")]`, die PMULL ausführen – auf dem BCM2711 des Pi 4
  (Cortex-A72, CPU-Flags `fp asimd evtstrm crc32 cpuid`, kein `aes`/`pmull`/`sha3`) ist das
  eine illegale Instruktion, der Prozess stirbt ohne jede Meldung (Exit-Code 132). Genau das
  beschreibt [Issue #1623](https://github.com/AppFlowy-IO/AppFlowy-Cloud/issues/1623) (letzte
  Logzeile dort: `applying Crc32 of the request body as a header`).
- Warum `RUSTFLAGS="-C target-feature=-crypto,-aes,-sha2,-sha3"` aus `0.9.64-5` nichts
  bewirkte: Diese Features sind auf `aarch64-unknown-linux-gnu` ohnehin standardmäßig aus, und
  per-Funktion-Attribute `#[target_feature(enable = ...)]` werden davon nicht berührt; `crypto`
  ist zudem gar kein gültiges Feature mehr (rustc-Warnung `unknown and unstable feature` im
  Build-Log). Das GitHub-Actions-Image aus `0.9.64-6` hatte dieselben Flags gesetzt (im
  aarch64-Job-Log geprüft) – es gab also keine Regression durch den CI-Build, der Fehler war
  nur nie weg. Die `RUSTFLAGS`-Zeile ist entfernt.
- Fix: Im `aarch64`-Quellcode-Build wird `crc-fast` per `cargo update -p crc-fast --precise
  1.9.0` angehoben. Seit `crc-fast 1.6.0` (PR #21 "Improve runtime feature detection") wird die
  Implementierung zur Laufzeit gewählt: ohne `aes` → `SoftwareTable`, also eine reine
  Tabellen-Implementierung; auch der CRC32-"Fusion"-Schnellpfad wird nur auf CPUs mit
  AES/PMULL betreten. `1.9.0` ist die letzte Version mit MSRV 1.81 (passt zu `rust:1.86` im
  Builder; `1.10.0` bräuchte Rust 1.89), erfüllt die Anforderung `^1.2.1` von
  `aws-smithy-checksums` und ist API-kompatibel (Semver 1.x). Der Build gibt die gepinnte
  Version aus `Cargo.lock` im Log aus.
- **Auf einem Raspberry Pi 4 verifiziert** (Home Assistant OS, Add-on aus dem GHCR-Image
  `0.9.64-8`): Erster Login des Admin-Kontos, Anlegen weiterer Konten und deren Login liefen
  ohne Absturz durch – die erste Version dieses Add-ons, bei der das auf der echten Hardware
  bestätigt wurde.
- Diagnose-Verbesserung: Neue s6-`finish`-Skripte für `appflowy_cloud` und `appflowy_worker`
  loggen Exit-Code und Signal, wenn ein Dienst stirbt (`exited with code 256 (signal 4)` =
  SIGILL). Bisher war ein solcher Absturz nur indirekt am erneuten "waiting for gotrue..." zu
  erkennen.
- **Wichtig nach dem Update:** Ein Konto, dessen erster Login auf `0.9.64-7` oder älter den
  Server zum Absturz gebracht hat, bleibt kaputt – Benutzer, Workspace und Berechtigungen
  existieren, die Start-Collabs des Workspace haben MinIO aber nie erreicht und werden nicht
  nachträglich angelegt (Log: wiederholt `failed to get collab ... from S3: Record not found`,
  die App verbindet sich im Sekundentakt neu). Abhilfe siehe DOCS.md "Bekannte Probleme":
  Add-on deinstallieren und neu installieren (löscht `/data`), oder Konto in der Konsole
  löschen und mit anderer E-Mail neu registrieren.
- Doku: Neuer Eintrag zu "Record not found" / "rocksdb dropped" in der Desktop-App, wenn
  dieselbe App-Installation zuvor bei einem anderen AppFlowy-Server (z. B. dem lokalen
  `docker-compose`-Test) angemeldet war – erkennbar an `fail to decode token,
  error:InvalidSignature`, `Refresh Token Not Found` und einem Fremdschlüssel-Fehler auf
  `af_collab` mit unbekannter Workspace-ID im Add-on-Log. Abhilfe: `data_<host>`-Ordner der App
  löschen und neu anmelden.
