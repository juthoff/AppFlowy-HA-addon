# AppFlowy Add-on

Vollständig selbst-gehostetes [AppFlowy](https://github.com/AppFlowy-IO/AppFlowy) in **einem** Add-on:
PostgreSQL 16 + pgvector, Redis, MinIO (Objektspeicher), GoTrue (Login), AppFlowy Cloud
(API/Realtime-Sync), AppFlowy Worker, Admin-Konsole und AppFlowy Web laufen alle in diesem
einen Container. Es wird kein weiteres Add-on benötigt.

## Wichtig: Warum diese Version?

AppFlowy-Cloud (der Server) wurde am 11.09.2026 archiviert und auf eine **kommerzielle Lizenz**
umgestellt, die Kopieren/Verändern/Weiterverteilen verbietet. Dieses Add-on verwendet deshalb
bewusst die **letzte AGPL-3.0-Version (0.9.64, veröffentlicht am 04.07.2025)** – die letzte,
die man legal selbst bauen und weitergeben darf. Es gibt dafür **keine Updates oder
Sicherheitspatches** vom Hersteller mehr. Details und Quellen jeder Komponente stehen in
[NOTICE.md](https://github.com/AppFlowy-IO/AppFlowy-Cloud/tree/0.9.64).

Bewusst **nicht** enthalten: die optionale KI-Chat-Funktion (`appflowy_ai`) – ihre Docker-Images
liefen zeitlich nicht im Gleichschritt mit dem übrigen 0.9.64-Release, ein sauberer Versions-Pin
war daher nicht zuverlässig möglich. Alles andere (Notizen, Datenbanken, Kanban, Dokumente,
Echtzeit-Zusammenarbeit, Freigaben/Publish, Team-Workspaces, Import) ist vorhanden.

## Systemanforderungen

- **CPU-Architektur**: nur `amd64` und `aarch64` (kein 32-Bit-`armhf` – die Original-Images
  unterstützen das nicht).
- **RAM**: mindestens **4GB** auf dem Home-Assistant-Host, **8GB oder mehr ist komfortabel**.
  Dieses Add-on bündelt PostgreSQL, Redis, MinIO, GoTrue, appflowy_cloud, appflowy_worker,
  admin_frontend und nginx in einem einzigen Container – zusätzlich zu Home Assistant Core
  selbst und eventuellen weiteren Add-ons auf demselben Gerät. Mit nur 2GB RAM (z. B. ältere/
  kleinere Raspberry-Pi-Modelle) kann es unter Last (neues Konto samt Workspace anlegen,
  mehrere Dokumente gleichzeitig öffnen) zu spürbarem Speicherdruck kommen.
- **Freier Speicherplatz**: Postgres-Datenbank und MinIO-Objektspeicher wachsen mit der Nutzung;
  auf `aarch64` kommen beim Bauen zusätzlich temporäre Rust-Build-Artefakte hinzu (siehe unten).
  Ein paar GB frei sollten vor einer (Erst-)Installation bzw. einem Update vorhanden sein.
- **Build-Zeit**: Ab Version `0.9.64-6` wird das Add-on-Image **vorgefertigt per GitHub Actions**
  gebaut und nach [GHCR](https://ghcr.io) veröffentlicht (`image:`-Feld in `config.yaml`,
  Workflow unter `.github/workflows/build.yaml`) – Home Assistant Supervisor lädt das fertige
  Image dann nur noch herunter, statt es selbst zu bauen. Auf `aarch64` (z. B. Raspberry Pi)
  werden `appflowy_cloud` und `appflowy_worker` dabei weiterhin aus dem Rust-Quellcode gebaut
  (siehe CHANGELOG.md, Version `0.9.64-5`) – das passiert jetzt aber einmalig auf GitHubs
  Build-Infrastruktur statt auf jedem einzelnen Home-Assistant-Gerät. In `0.9.64-5` (ohne
  vorgefertigtes Image) lief dieser Rust-Kompilierlauf noch lokal auf dem Gerät selbst und
  dauerte auf einem Raspberry Pi potenziell 30+ Minuten pro Installation/Update.

Auf einem **Raspberry Pi 4 mit 8GB RAM** ist der laufende Betrieb damit unproblematisch: 8GB
liegt deutlich über der empfohlenen Untergrenze, und da das Image jetzt vorgefertigt
heruntergeladen statt lokal gebaut wird, spielt die CPU-Geschwindigkeit für Installation/Update
kaum noch eine Rolle.

## Ersteinrichtung

1. **Passwort setzen**: Unter "Konfiguration" mindestens `admin_password` setzen (und optional
   `admin_email` ändern, Standard: `admin@example.com`). Ohne Passwort startet der Login-Dienst
   zwar, aber es wird kein Admin-Konto angelegt.
2. Add-on starten. Der erste Start dauert länger (Datenbank wird initialisiert, Migrationen
   laufen, Container-Images werden beim ersten Bauen kompiliert).
3. Im Browser `http://<home-assistant-ip>:8099/` öffnen → AppFlowy Web.
   Admin-Konsole: `http://<home-assistant-ip>:8099/console` (Login mit `admin_email`/`admin_password`).
4. Für die Desktop-/Mobil-Apps von AppFlowy: beim Einrichten "Self-hosted" wählen und als
   Server-URL `http://<home-assistant-ip>:8099` eintragen.

## Konfigurationsoptionen

| Option | Beschreibung |
|---|---|
| `fqdn` | Domain/IP, unter der das Add-on von außen erreichbar ist (leer = `localhost:8099`). Nur den Host angeben, **ohne** `http(s)://`. |
| `scheme` | `http` oder `https` – **nur** relevant, wenn ein eigener Reverse Proxy mit TLS davorsteht. Das Add-on selbst spricht immer HTTP. |
| `admin_email` / `admin_password` | Erstes Admin-Konto (Login über die Admin-Konsole oder die AppFlowy-App). |
| `enable_signup` | Ob sich neue Nutzer selbst registrieren können. |
| `smtp_*` | Optional – ohne SMTP funktioniert alles außer "Magic Link"-Login und E-Mail-Einladungen; Nutzer/Einladungen lassen sich dann nur über die Admin-Konsole verwalten. `smtp_host` ist bereits auf [Resend](https://resend.com) vorbelegt (kostenloser Plan, Signup nur mit E-Mail-Adresse, keine weiteren persönlichen Daten nötig); dort einen API-Key erzeugen und als `smtp_password` eintragen. **Wichtig:** `smtp_user` muss bei Resend wörtlich `resend` sein (keine E-Mail-Adresse) – die tatsächliche Absenderadresse wird über `smtp_admin_email` gesetzt, die zu einer in Resend verifizierten Domain gehören muss (ohne eigene Domain nur `onboarding@resend.dev`, sendet dann nur an die eigene Resend-Konto-Adresse). |
| `oauth_google_*` / `oauth_github_*` | Optionaler Login über Google/GitHub. |
| `log_level` | Rust-Log-Level der Kernel-Dienste. |

## Datenpersistenz

Alle Daten (Postgres, MinIO, generierte Geheimnisse) liegen im Add-on-eigenen `/data`-Verzeichnis
und bleiben bei Neustarts/Updates des Add-ons erhalten. Ein Backup über die normale Home-Assistant-
Sicherung (Snapshot/Backup) sichert damit auch alle AppFlowy-Inhalte mit.

## Bekannte Einschränkungen

- Kein eingebautes TLS/HTTPS – dafür bei Bedarf einen eigenen Reverse Proxy (z. B. eigene
  Domain + Let's-Encrypt-Proxy) **vor** dieses Add-on stellen. Für reinen LAN-Betrieb ist das
  nicht nötig.
- Das Login-Session-Cookie wird ohne `Secure`-Attribut gesetzt (nötig, damit der Zugriff über
  die Host-IP im LAN per HTTP überhaupt funktioniert – Browser verwerfen `Secure`-Cookies
  sonst außerhalb von `localhost` auf unverschlüsselten Verbindungen). Das Cookie wird dadurch
  auch über unverschlüsseltes HTTP übertragen; wer denselben Netzwerkabschnitt mitlauschen kann
  (offenes/kompromittiertes WLAN, bösartiges Gerät im selben LAN), könnte es abgreifen und die
  Session übernehmen. Für ein vertrauenswürdiges Heimnetz ist das Risiko gering – wer das
  Add-on über ein nicht vertrauenswürdiges Netz oder das Internet erreichbar macht, sollte
  dafür unbedingt den oben genannten eigenen Reverse Proxy mit TLS davorsetzen.
- KI-Chat-Funktion nicht enthalten (siehe oben).
- Da AppFlowy-Cloud archiviert ist, bekommt diese Version keine Sicherheitsupdates mehr vom
  Hersteller. Für ein reines Heimnetz-Setup ist das Risiko gering, für einen öffentlich erreichbaren
  Server sollte man sich dessen bewusst sein.

## Bekannte Probleme

- **Desktop-/Mobil-App meldet "Something went wrong. Please try again later." (behoben in
  `0.9.64-5`)**: Auf manchen ARM-CPUs (u. a. beobachtet auf einem Raspberry Pi 4) stürzte
  `appflowy_cloud` beim ersten Login eines Kontos ab, konkret beim Anlegen des Standard-
  "Getting Started"-Workspace, sobald dabei zum ersten Mal Inhalte zu MinIO hochgeladen wurden.
  Zu erkennen im Add-on-Log an `[appflowy_cloud] waiting for gotrue...` / `waiting for
  minio...`, dem NICHT wie bei einem regulären Neustart ein `received graceful shutdown
  signal` vorausgeht, und ganz ohne Rust-Panic-Trace. Ursache war **nicht** Speicherdruck
  (das wurde durch Beobachtung des Arbeitsspeicher-Verlaufs unter Einstellungen → System →
  Hardware sowie der Host-System-Logs ausgeschlossen), sondern ein CPU-Instruktionssatz-
  Absturz (SIGILL, Exit-Code 132): Das vorgefertigte `appflowy_cloud`/`appflowy_worker`-Binary
  war mit CPU-Krypto-/AES-/SHA-Erweiterungen kompiliert, die der jeweilige ARM-Kern nicht
  unterstützt (siehe [Issue #1623](https://github.com/AppFlowy-IO/AppFlowy-Cloud/issues/1623)
  im AppFlowy-Cloud-Repo für einen identischen Fall bei Datei-Uploads). Seit `0.9.64-5` werden
  `appflowy_cloud`/`appflowy_worker` auf `aarch64` mit deaktivierten Krypto-Erweiterungen aus
  dem Quellcode gebaut statt das vorgefertigte Image zu verwenden (siehe CHANGELOG.md und
  "Systemanforderungen" oben zur dadurch spürbar längeren Build-Zeit auf `aarch64`).
  Postgres/Redis/appflowy_cloud sind trotzdem seit `0.9.64-3`/`0.9.64-4` zusätzlich
  speicherschonender konfiguriert – das war zwar nicht die eigentliche Ursache dieses
  konkreten Fehlers, schadet auf kleiner Hardware aber nicht.
