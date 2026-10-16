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
- Software: Firefox e App Center (snap inclusi nell'immagine), LibreOffice
  (Writer, Calc, Impress), strumenti GNOME, strumenti per sviluppatori
  (git, build-essential, gdb, cmake, Python), di rete e di sistema, Vulkan e
  GameMode.
- Sicurezza e privacy: aggiornamenti di sicurezza automatici, AppArmor,
  nessuna telemetria, nessun servizio di rete in ascolto, APT news di
  Canonical disattivate.

## Artefatti

| File | Descrizione |
|---|---|
| `trota-os-1.0-amd64.iso` | Immagine ISO (circa 3,7 GB) |
| `trota-os-1.0-amd64.iso.sha256` | Checksum SHA-256 |
| `trota-os-1.0-amd64.manifest` | Elenco di pacchetti e versioni |

Le ISO non sono conservate nel repository Git: si generano con
[building.md](building.md) e si pubblicano come allegati di una release solo
dopo la verifica descritta in [testing.md](testing.md).

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
5. **Indirizzo del maintainer segnaposto** nei pacchetti
   (`maintainers@testardstudios.invalid`) e verifiche su nome/marchio/domini
   da completare prima della pubblicazione ([licensing.md](licensing.md)).
