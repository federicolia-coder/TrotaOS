# Note di rilascio — Trota OS 1.0 "Fario"

Prima versione di Trota OS, sviluppata e pubblicata da TestardStudios.
Base: Ubuntu 24.04 LTS (noble), kernel HWE `linux-generic-hwe-24.04`
(serie 7.0 alla data della build), GNOME 46.

## Contenuto

- Immagine ISO ibrida amd64 (DVD/USB), avvio BIOS e UEFI con Secure Boot
  tramite shim e GRUB firmati da Canonical; menu di avvio con tema Trota OS.
- Sessione live e installazione con ubiquity, con slideshow Trota OS
  (inglese/italiano); i pacchetti della sessione live vengono rimossi dal
  sistema installato.
- Desktop GNOME 46 (sessione Ubuntu) con tema scuro Yaru, font Inter, sfondi
  *Forge*, *Steel*, *Ingot*, dock grafite, splash Plymouth e logo nella
  schermata di accesso, profilo del terminale "Trota".
- Applicazioni originali (GTK 4/libadwaita, inglese e italiano):
  Trota Welcome, Trota System Info, Trota Diagnostics, Trota Package Helper.
- **Nessuno snap**: Firefox `.deb` ufficiale dal repository APT di Mozilla
  (aggiornato con APT), GNOME Software con Flatpak e Flathub al posto di App
  Center, `snapd` bloccato da un pin APT; niente pubblicità di Ubuntu Pro in
  `apt` e nel banner di login.
- Software: LibreOffice
  (Writer, Calc, Impress), strumenti GNOME, strumenti per sviluppatori
  (git, build-essential, gdb, cmake, Python), di rete e di sistema, Vulkan e
  GameMode.
- Sicurezza e privacy: aggiornamenti di sicurezza automatici, AppArmor,
  nessuna telemetria, nessun servizio di rete in ascolto, APT news di
  Canonical disattivate.

## Artefatti

Release [v1.0.0](https://github.com/federicolia-coder/TrotaOS/releases/tag/v1.0.0)
(pre-release, costruita da GitHub Actions dal commit `e067ebc`): SHA-256
`001da64d80308e5d3a142c1c2bfdb02df3381c813f8f6fc08bc62ace268aa94b`, 2,37 GB
(la build precedente con gli snap era di 3,7 GB). Gli allegati scaricati dalla
release sono stati riverificati: checksum delle parti, della ISO ricomposta e
`verify-iso.sh` superati.

Ogni build ha un proprio SHA-256 (data di build e versioni dei pacchetti
cambiano): fa fede il file `.sha256` pubblicato accanto alla ISO.

| File | Descrizione |
|---|---|
| `trota-os-1.0-amd64.iso` | Immagine ISO (circa 2,4 GB) |
| `trota-os-1.0-amd64.iso.part1`, `.part2`… | La ISO divisa in parti (GitHub accetta allegati fino a 2 GiB) |
| `SHA256SUMS-parts` | Checksum delle singole parti |
| `trota-os-1.0-amd64.iso.sha256` | Checksum SHA-256 della ISO intera |
| `trota-os-1.0-amd64.manifest` | Elenco di pacchetti e versioni |

Ricomporre e verificare la ISO scaricata dalla release:

```sh
cat trota-os-1.0-amd64.iso.part* > trota-os-1.0-amd64.iso
sha256sum -c trota-os-1.0-amd64.iso.sha256
```

Su Windows: `copy /b trota-os-1.0-amd64.iso.part1 + trota-os-1.0-amd64.iso.part2 trota-os-1.0-amd64.iso`
(elencando tutte le parti presenti, in ordine)
e poi `certutil -hashfile trota-os-1.0-amd64.iso SHA256`.

Le ISO non sono conservate nel repository Git: si generano con
[building.md](building.md) oppure con il workflow *Build and release ISO* di
GitHub Actions, che le pubblica come release. La release 1.0 va pubblicata come
**anteprima** (pre-release) finché la build senza snap non ha completato i
test in VM descritti in [testing.md](testing.md).

## Stato rispetto ai criteri di completamento

| # | Criterio | Stato | Evidenza |
|---|---|---|---|
| 1 | Repository funzionante | Completato | Struttura, script, 170+ test automatici superati |
| 2 | Branding originale | Completato | `branding/`, [brand.md](brand.md) |
| 3 | Configurazione dei pacchetti | Completato | `packages/manifest/`, esclusioni motivate |
| 4 | Almeno un'applicazione originale funzionante | Completato | Quattro applicazioni, verificate anche nel sistema installato |
| 5 | Procedura di build documentata | Completato | [building.md](building.md) |
| 6 | ISO generata | Completato | `dist/trota-os-1.0-amd64.iso` + SHA-256 |
| 7 | Avvio live verificato | Completato in VM, con riserva | Avvio BIOS, UEFI e Secure Boot verificati; desktop live funzionante nel test BIOS; nei test live UEFI gnome-shell supera il timeout di avvio in emulazione (vedi [testing.md](testing.md)) |
| 8 | Installazione verificata in VM | Completato in VM | UEFI + Secure Boot e BIOS legacy, installazione automatica e primo avvio |
| 9 | Test delle utility | Completato | Test unitari, GUI sotto Xvfb, esecuzione nel sistema live e installato |
| 10 | Documentazione di sicurezza e licenze | Completato | [security.md](security.md), [privacy.md](privacy.md), [licensing.md](licensing.md) |
| 11 | Checksum | Completato | `checksums/`, `verify-iso.sh` |
| 12 | Elenco dei problemi noti | Completato | Sezione seguente |

Non eseguito: test su hardware reale e installazione completamente senza rete.

## Problemi noti

1. **Test su hardware reale non ancora eseguiti.** Tutti i test di avvio e
   installazione sono stati svolti in macchina virtuale (QEMU in
   emulazione, senza KVM).
2. **Repository APT di Trota OS non pubblicato.** I pacchetti `trota-*`
   ricevono correzioni solo con una nuova ISO; i pacchetti Ubuntu si
   aggiornano normalmente.
3. **Testi Ubuntu residui in modalità testo**: l'intestazione del messaggio
   del giorno (`Welcome to Ubuntu 24.04.5 LTS`, da `/etc/lsb-release`) e alcune
   parti dell'installer ubiquity e della *Guida del desktop* citano Ubuntu.
   Sono file di Ubuntu lasciati intatti per non creare conflitti con gli
   aggiornamenti.
4. **Aggiornamento automatico alla LTS successiva disattivato**
   (`Prompt=never`): Trota OS 2.0 su Ubuntu 26.04 sarà distribuito come
   nuova versione.
5. **Messaggio GRUB con Secure Boot**: all'avvio del sistema installato compare
   per un istante `error: prohibited by secure boot policy` (riga `hwmatch`
   del `grub.cfg` standard di Ubuntu); l'avvio prosegue normalmente.
6. **Menu della ISO**: in BIOS a 640×480 la voce "Install Trota OS 1.0 (no
   live session)" appare troncata; con Secure Boot il GRUB firmato non carica
   font e moduli grafici esterni e il menu appare in modalità testo (voci e
   funzionamento invariati).
7. **Icona "Mostra applicazioni" del dock**: è quella del tema Yaru di Ubuntu
   (il dock non permette un'icona personalizzata).
8. **Applicazioni solo snap**: non sono installabili finché non si rimuove il
   blocco (`/etc/apt/preferences.d/trota-no-snap.pref`); i pacchetti di
   transizione di Ubuntu che installano uno snap (es. `chromium-browser`)
   risultano non installabili. Le alternative sono su Flathub.
9. **Sessione live su macchine molto lente**: in emulazione gnome-shell può
   superare il timeout di avvio di systemd (90 s) e GNOME mostra "Oh no!
   Something has gone wrong"; da verificare su hardware reale/KVM.
10. **Menu contestuali del dock non disponibili**: manca il pacchetto
    `gir1.2-dbusmenu-glib-0.4` (da aggiungere al manifest nella 1.0.1).
11. **Indirizzo del maintainer segnaposto** nei pacchetti
   (`maintainers@testardstudios.invalid`) e verifiche su nome/marchio/domini
   da completare prima della pubblicazione ([licensing.md](licensing.md)).
