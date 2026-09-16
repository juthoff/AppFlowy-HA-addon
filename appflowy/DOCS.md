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

- Nur `amd64` und `aarch64` (kein 32-Bit-`armhf` – die Original-Images unterstützen das nicht).
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
