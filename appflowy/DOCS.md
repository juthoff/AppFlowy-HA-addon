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
3. Im Browser `http://<home-assistant-ip>:8099/` öffnen → AppFlowy Web. Login mit
   `admin_email`/`admin_password` über das Formular "E-Mail + Passwort" (Standardansicht der
   Login-Seite, seit `0.9.64-9`; der Link "Continue with email code" darunter wechselt zum
   ursprünglichen Einmal-Code-Login, der SMTP voraussetzt).
   Admin-Konsole: `http://<home-assistant-ip>:8099/console` (Login mit `admin_email`/`admin_password`).
4. Für die Desktop-/Mobil-Apps von AppFlowy: beim Einrichten "Self-hosted" wählen und als
   Server-URL `http://<home-assistant-ip>:8099` eintragen. **Wichtig:** Nur Apps der
   0.9.x-Generation (Desktop `0.9.4`/`0.9.5`, Juli 2025) sind mit diesem Add-on kompatibel –
   neuere Apps zeigen den Workspace leer bzw. nicht editierbar an, siehe "Bekannte Probleme".

## Konfigurationsoptionen

| Option | Beschreibung |
|---|---|
| `fqdn` | Domain/IP, unter der das Add-on von außen erreichbar ist (leer = `localhost:8099`). Nur den Host angeben, **ohne** `http(s)://`. |
| `scheme` | `http` oder `https` – **nur** relevant, wenn ein eigener Reverse Proxy mit TLS davorsteht. Das Add-on selbst spricht immer HTTP. |
| `admin_email` / `admin_password` | Erstes Admin-Konto (Login über AppFlowy Web, die Admin-Konsole oder die AppFlowy-App). |
| `enable_signup` | Ob sich neue Nutzer selbst registrieren können. |
| `smtp_*` | Optional – ohne SMTP funktioniert alles außer "Magic Link"/Einmal-Code-Login und E-Mail-Einladungen; der Login in AppFlowy Web geht dann über E-Mail + Passwort (Passwort für neue Nutzer in der Admin-Konsole setzen), Nutzer/Einladungen lassen sich nur über die Admin-Konsole verwalten. `smtp_host` ist bereits auf [Resend](https://resend.com) vorbelegt (kostenloser Plan, Signup nur mit E-Mail-Adresse, keine weiteren persönlichen Daten nötig); dort einen API-Key erzeugen und als `smtp_password` eintragen. **Wichtig:** `smtp_user` muss bei Resend wörtlich `resend` sein (keine E-Mail-Adresse) – die tatsächliche Absenderadresse wird über `smtp_admin_email` gesetzt, die zu einer in Resend verifizierten Domain gehören muss (ohne eigene Domain nur `onboarding@resend.dev`, sendet dann nur an die eigene Resend-Konto-Adresse). |
| `oauth_google_*` / `oauth_github_*` | Optionaler Login über Google/GitHub. |
| `log_level` | Rust-Log-Level der Kernel-Dienste. |
| `task_overview_enabled` | Schaltet die automatische Aufgabenübersicht ein oder aus (siehe "Aufgabenübersicht"). Standard: an. |
| `task_overview_statuses` | Status-Werte, deren Karten in der Übersicht erscheinen – in dieser Reihenfolge als Abschnitte. Standard: `Doing`, `To Do`. |
| `task_overview_status_field` | Name des Auswahlfelds, das auf den Boards den Status hält. Standard: `Status`. |
| `task_overview_page` | Name der Übersichtsseite. Standard: `Offene Aufgaben`. |
| `task_overview_exclude` | Boards, die ignoriert werden – als Pfad wie in der Seitenleiste, z. B. `General / To-dos`. Ein Ordnerpfad schließt alle Boards darunter aus. |

## Aufgabenübersicht

Das Add-on pflegt in **jedem Workspace, der mindestens ein Board hat**, eine eigene Seite
(Standard: "Offene Aufgaben"). Sie sammelt von allen Boards dieses Workspace die Karten, deren
Status in `task_overview_statuses` steht – gruppiert nach Status, darin nach Board, jeweils mit
Link zum Board und dessen Pfad in der Seitenleiste. Jedes Konto bekommt so die Übersicht über
seine eigenen Boards; alle Mitglieder eines Workspace sehen dessen Übersicht.

- **Keine Zugangsdaten nötig:** Der Dienst meldet sich als Besitzer des jeweiligen Workspace an,
  mit einem kurzlebigen Token, das er mit dem vom Add-on selbst erzeugten Schlüssel
  (`/data/secrets.env`) signiert. Es muss nichts eingetragen werden; `admin_email`/
  `admin_password` spielen dafür keine Rolle.
- **Aktualisierung:** Der Dienst prüft alle 10 Sekunden in der Datenbank, ob sich in einem
  Workspace ein Board, eine Karte oder die Seitenleiste geändert hat, und schreibt dann nur die
  Seite dieses Workspace neu. Eine Änderung erscheint, sobald AppFlowy sie gespeichert hat, plus
  höchstens 10 Sekunden.
- **Die Seite wird bei jedem Lauf komplett neu geschrieben** – eigene Notizen darauf gehen
  verloren. Sie darf in der Seitenleiste beliebig verschoben werden, gefunden wird sie über
  ihren Namen. Fehlt sie, legt der Dienst sie im ersten Space an.
- Boards ohne ein Feld mit dem Namen aus `task_overview_status_field` werden übersprungen und
  im Log genannt. Jeder Lauf schreibt Konto und Workspace ins Add-on-Log (Zeilen mit
  `[task_overview]`).
- Das Skript (`/opt/task-overview/task_overview.py`) läuft auch eigenständig gegen den Server,
  dann mit E-Mail + Passwort, z. B. zum Testen mit `--dry-run` (nur ausgeben, nichts schreiben).

## Verweise auf Seiten

In AppFlowy Web (Browser) lassen sich Seiten jetzt auch dort verlinken, wo AppFlowy nur
reinen Text speichert:

- **Seitentitel**, **Titel einer Board-Karte** und **Einträge einer Checkliste**: `[[` oder `@`
  tippen, dann Teil eines Seitennamens – es öffnet sich eine Seitenauswahl (Pfeiltasten + Enter
  oder Klick). Gespeichert wird der Verweis als `[[Name|Seiten-ID]]`; AppFlowy Web zeigt ihn als
  anklickbaren Link mit dem aktuellen Seitennamen, Seitenleiste, Brotkrumen und Browser-Tab
  zeigen nur den Namen. Einen Titel mit Verweis zum Bearbeiten neben den Link klicken.
- **Board-Karten** sind in AppFlowy Web jetzt bearbeitbar (vorher nur lesbar): Titel, das
  Dokument unter den Eigenschaften (mit dem normalen `@`-Verweismenü, auch in Überschriften und
  Listen) und die Checkliste (abhaken, hinzufügen, umbenennen, löschen).
- **Die Desktop- und Mobil-Apps zeigen `[[Name|Seiten-ID]]` als reinen Text** – sie können vom
  Add-on nicht verändert werden. Das Dokument einer Karte und Verweise darin sehen sie normal.
- In der Handy-Ansicht von AppFlowy Web bleibt alles schreibgeschützt (wie im Original).
- Änderungen an Karten werden erst nach einem Neuladen in anderen geöffneten Browser-Tabs
  sichtbar (AppFlowy Web lädt Board-Daten nicht live nach).

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

- **Erster Login eines Kontos schlägt fehl – Desktop-App "Something went wrong" / "Record not
  found", Admin-Konsole erst beim zweiten Versuch (behoben in `0.9.64-8`, Raspberry Pi 4 und
  andere ARM-CPUs ohne Krypto-Erweiterungen)**: `appflowy_cloud` stürzte bei jedem ersten
  Upload nach MinIO ab – beim Anlegen des Standard-"Getting Started"-Workspace für ein neues
  Konto (jeder Collab größer als 4 KB wandert nach MinIO), aber genauso bei jedem
  Datei-Upload oder Snapshot. Zu erkennen im Add-on-Log an `[appflowy_cloud] waiting for
  gotrue...` / `waiting for minio...` mitten im Betrieb, dem NICHT wie bei einem regulären
  Neustart ein `received graceful shutdown signal` vorausgeht, ganz ohne Rust-Panic-Trace,
  meist direkt nach einer Postgres-Zeile `unexpected EOF on client connection with an open
  transaction`. Seit `0.9.64-8` steht zusätzlich eine Zeile `[appflowy_cloud] exited with code
  256 (signal 4)` im Log (Signal 4 = SIGILL, "illegal instruction"). Ursache war **nicht**
  Speicherdruck, sondern ein CPU-Instruktionssatz-Absturz, identisch zu
  [Issue #1623](https://github.com/AppFlowy-IO/AppFlowy-Cloud/issues/1623) im
  AppFlowy-Cloud-Repo: Der S3-Client (`aws-sdk-s3`) berechnet für jeden Upload eine
  CRC32-Prüfsumme über die Rust-Bibliothek `crc-fast`, und die in AppFlowy-Cloud `0.9.64`
  festgepinnte Version `1.2.1` prüft auf `aarch64` **nicht zur Laufzeit**, ob die CPU die
  dafür genutzten PMULL-/AES-Instruktionen überhaupt hat – der BCM2711 des Raspberry Pi 4
  (Cortex-A72, CPU-Flags nur `fp asimd evtstrm crc32 cpuid`) hat sie nicht. Der in
  `0.9.64-5` eingebaute Versuch, das per `RUSTFLAGS="-C target-feature=-crypto,-aes,..."`
  abzuschalten, konnte prinzipiell nicht wirken (diese Features sind auf
  `aarch64-unknown-linux-gnu` ohnehin aus; die betroffenen Funktionen schalten sie per
  Attribut selbst wieder ein) und war nie mit einem echten Erst-Login getestet worden. Seit
  `0.9.64-8` wird beim Bauen für `aarch64` `crc-fast` auf `1.9.0` angehoben, das die
  CPU-Fähigkeiten zur Laufzeit erkennt und ohne AES/PMULL auf eine Tabellen-Implementierung
  ausweicht.
  **Nach dem Update von `0.9.64-7` oder älter:** Ein Konto, dessen erster Login auf einer
  betroffenen Version abgestürzt ist, bleibt dauerhaft kaputt (Benutzer und Workspace existieren
  in der Datenbank, die Startseiten des Workspace haben MinIO aber nie erreicht – der Server
  legt sie nicht nachträglich an; im Log wiederholt sich `failed to get collab ... from S3:
  Record not found`, die App meldet "Record not found"). Abhilfe: Add-on **deinstallieren und
  neu installieren** (löscht alle Add-on-Daten; bei einer frischen Installation ohne Inhalte
  der einfachste Weg) – oder das Konto in der Admin-Konsole löschen und sich mit einer
  **anderen** E-Mail-Adresse neu registrieren.
- **Desktop-/Mobil-App ab ca. 0.10: persönlicher Workspace leer bzw. nicht editierbar, `+` legt
  keine Seite an (kein Fix möglich)**: Beobachtet mit AppFlowy Desktop `0.14.3` auf macOS. Der
  Login klappt, der Workspace zeigt aber keine (oder nur alte) Seiten, Klick auf `+` scheint
  nichts zu tun, und der Workspace wirkt schreibgeschützt – während ein anonymes/lokales Konto in
  derselben App problemlos funktioniert. Das ist **kein Serverfehler**: Das Add-on-Log ist sauber;
  aufschlussreich ist nur das nginx-Zugriffslog im Container (`/var/log/nginx/access.log`), das
  voller `404` für Pfade wie `/api/workspace/<id>/view/<id>`, `.../view/<id>/navigation`,
  `.../collab/<id>/permission`, `/api/server-info`, `.../workspace-profile`, `.../usage-and-limit`
  oder `.../notifications` ist. Diese Endpunkte gibt es erst im **kommerziellen, nicht mehr
  quelloffenen** AppFlowy-Cloud nach `0.9.64` (siehe "Warum diese Version?" oben) – neuere Apps
  laden ihre Seitenleiste ausschließlich darüber. Das Anlegen einer Seite (`POST .../page-view`)
  gelingt serverseitig sogar, die App kann den Seitenbaum danach aber nicht mehr zurücklesen und
  zeigt die Seite deshalb nie an. Ein Nachbau der fehlenden Endpunkte in nginx ist nicht möglich
  (die Antwortformate sind nur im geschlossenen Server definiert), und die App hat keinen
  Fallback auf den alten Sync-Weg. **Abhilfe:** Entweder das mitgelieferte AppFlowy Web unter
  `http://<home-assistant-ip>:8099/` nutzen, oder eine Desktop-/Mobil-App aus der Zeit des
  `0.9.64`-Servers installieren – Desktop
  [`0.9.4`](https://github.com/AppFlowy-IO/AppFlowy/releases/tag/0.9.4) bzw.
  [`0.9.5`](https://github.com/AppFlowy-IO/AppFlowy/releases/tag/0.9.5) (Juli 2025) sind gegen
  genau den Server-Stand gebaut, der in `0.9.64` enthalten ist. Vor einem Downgrade den
  Datenordner der App für diesen Server wegräumen (macOS:
  `~/Library/Application Support/com.appflowy.appflowy.flutter/data_<host>`, Windows:
  `%APPDATA%\io.appflowy\AppFlowy\data_<host>`), weil die neuere App dort bereits ein
  neueres lokales Datenschema angelegt hat. In der App anschließend angebotene Updates
  **ablehnen** – der eingebaute Updater würde sonst wieder auf eine inkompatible Version
  aktualisieren.
  - **macOS**: `AppFlowy-0.9.5-macos-arm64.zip` (Apple Silicon) bzw. `...-x86_64.zip` (Intel) von
    der Release-Seite laden, entpacken und `AppFlowy.app` nach `/Applications` verschieben.
  - **Windows** (nur 64-Bit): `AppFlowy-0.9.5-windows-x86_64.exe` (Installer) oder `...-windows-x86_64.zip`
    (portabel) von der Release-Seite laden. Alternativ per winget, das die alten Versionen
    weiterhin führt – die zweite Zeile verhindert, dass `winget upgrade --all` wieder auf 0.14.x
    hochzieht:

    ```powershell
    winget install --id AppFlowy.AppFlowy --version 0.9.5 --exact
    winget pin add --id AppFlowy.AppFlowy --blocking
    ```
- **Desktop-App meldet "Record not found" bzw. "rocksdb dropped", obwohl der Server sauber
  läuft**: Tritt auf, wenn dieselbe App-Installation vorher bei einem *anderen* AppFlowy-Server
  angemeldet war (z. B. dem lokalen `docker-compose`-Test aus diesem Repository) und dessen
  Sitzung noch lokal gespeichert ist. Im Add-on-Log zeigt sich das an `fail to decode token,
  error:InvalidSignature` (Token vom anderen Server, anderes JWT-Secret), `Invalid Refresh
  Token: Refresh Token Not Found` und einem Postgres-Fehler `violates foreign key constraint
  "af_collab_temp_workspace_id_fkey"` mit einer Workspace-ID, die es auf diesem Server nicht
  gibt (die App versucht, den Workspace des alten Servers hierher zu synchronisieren);
  "rocksdb dropped" ist die lokale Datenbank der App, die während dieses Sitzungswechsels
  geschlossen wird. Abhilfe: App beenden, den oben genannten `data_<host>`-Ordner für diesen
  Server löschen, App starten und neu anmelden.
