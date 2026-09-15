# AppFlowy Home Assistant Add-on Repository

Ein vollständig selbst-gehostetes [AppFlowy](https://github.com/AppFlowy-IO/AppFlowy) als
Home-Assistant-Add-on – inklusive aller benötigten Datenbanken (PostgreSQL + pgvector, Redis,
MinIO). Es wird **kein weiteres Add-on** benötigt.

## Hintergrund: warum nicht einfach die neueste AppFlowy-Cloud-Version?

Der Server hinter AppFlowy ("AppFlowy-Cloud") wurde am 11.09.2026 archiviert und durch ein
**kommerziell lizenziertes** Repository ersetzt, dessen Lizenz Kopieren/Verändern/Weiterverteilen
verbietet und einen maschinengebundenen Lizenzschlüssel voraussetzt. Ein selbstgebautes,
weiterverteilbares Add-on lässt sich darauf nicht rechtmäßig stützen.

Dieses Add-on verwendet deshalb bewusst die **letzte AGPL-3.0-Version** (Git-Tag `0.9.64`,
veröffentlicht am 04.07.2025) – die letzte, die man legal selbst bauen, verändern und
weitergeben darf. Genauere Herkunfts- und Lizenzangaben jeder einzelnen Komponente stehen in
[`appflowy/NOTICE.md`](appflowy/NOTICE.md). Diese Version erhält **keine Updates oder
Sicherheitspatches** mehr vom Hersteller.

## Installation

1. In Home Assistant: **Einstellungen → Add-ons → Add-on-Store → ⋮ (oben rechts) →
   Repositories** und die URL dieses Repositories eintragen.
2. Das Add-on **AppFlowy** erscheint im Store → installieren.
3. Vor dem ersten Start: unter "Konfiguration" mindestens `admin_password` setzen.
4. Add-on starten (erster Start dauert länger, siehe [`appflowy/DOCS.md`](appflowy/DOCS.md)).

Alle Details zu Konfiguration, Ersteinrichtung und bekannten Einschränkungen stehen in
[`appflowy/DOCS.md`](appflowy/DOCS.md) (wird auch im Add-on selbst als "Dokumentation" angezeigt).

## Enthaltene Dienste (alle in einem Container)

- PostgreSQL 16 + pgvector (Datenhaltung, Vektorsuche)
- Redis (Cache/Pub-Sub)
- MinIO (S3-kompatibler Objektspeicher für Dateien/Anhänge)
- GoTrue (Login/Auth, aus Quellcode gebaut)
- appflowy_cloud (API, Echtzeit-Synchronisation)
- appflowy_worker (Hintergrundjobs, z. B. Importe)
- admin_frontend (Admin-Konsole unter `/console`)
- AppFlowy Web (Browser-Client, aus Quellcode gebaut)

Bewusst nicht enthalten: die optionale KI-Chat-Funktion (siehe `appflowy/DOCS.md` für die
Begründung).

## Hinweis

Dies ist ein inoffizielles, community-erstelltes Add-on und steht in keiner Verbindung zu
AppFlowy IO. Es kann nicht getestet werden, ohne es tatsächlich auf einer Home-Assistant-
Installation zu bauen und zu starten – bitte nach der Installation die Logs prüfen und
Rückmeldung geben, falls etwas nicht funktioniert.
