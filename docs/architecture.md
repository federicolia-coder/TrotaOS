# Architettura di Trota OS

Trota OS non riscrive il sistema operativo: è Ubuntu 24.04 LTS con un insieme
curato di pacchetti, una configurazione desktop propria, un'identità grafica
originale e quattro applicazioni sviluppate da TestardStudios. Tutto il valore
aggiunto è distribuito come normali pacchetti `.deb`, quindi si aggiorna con
APT come il resto del sistema.

```
┌───────────────────────────── ISO ibrida (BIOS + UEFI, DVD/USB) ──────────────────────────────┐
│ shim + GRUB firmati da Canonical → GRUB con tema Trota → kernel HWE + initrd (casper, Plymouth) │
│ casper/filesystem.squashfs                                                                      │
│ ┌─────────────────────────────── sistema Ubuntu 24.04 LTS ─────────────────────────────────┐   │
│ │ archivio Ubuntu: main/restricted/universe/multiverse + noble-updates + noble-security    │   │
│ │ GNOME 46 (sessione Ubuntu, GDM, Wayland), NetworkManager, PipeWire, AppArmor, systemd    │   │
│ │ snap seeded: Firefox, App Center (+ basi e runtime)                                       │   │
│ │ ┌──────────────────────────── pacchetti Trota OS (trota-os) ─────────────────────────┐   │   │
│ │ │ trota-release          os-release (dpkg-divert), identità del sistema              │   │   │
│ │ │ trota-artwork          logo, sfondi, icone, tema Plymouth, tema GRUB               │   │   │
│ │ │ trota-desktop-settings override GSettings, profilo dconf, terminale, GDM           │   │   │
│ │ │ trota-common           libreria Python condivisa (back-end + UI)                   │   │   │
│ │ │ trota-welcome / trota-system-info / trota-diagnostics / trota-package-helper       │   │   │
│ │ │ trota-docs             documentazione HTML offline                                  │   │   │
│ │ │ trota-desktop          metapacchetto                                               │   │   │
│ │ └────────────────────────────────────────────────────────────────────────────────────┘   │   │
│ └──────────────────────────────────────────────────────────────────────────────────────────┘   │
│ installer: ubiquity (rimosso dal sistema installato con filesystem.manifest-remove)            │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Struttura del repository

| Percorso | Contenuto |
|---|---|
| `applications/` | Codice Python delle applicazioni; `trota-common` è la libreria condivisa |
| `branding/` | Generatore degli asset (`generate.py`), SVG generati, temi Plymouth e GRUB, `render.sh` |
| `packages/manifest/` | Elenchi dei pacchetti dell'immagine, uno per ruolo, più le esclusioni motivate |
| `packages/config/iso/` | Menu GRUB del supporto di installazione |
| `packaging/` | Pacchetto sorgente Debian (`debian/`) e file installati (`files/`) |
| `po/` | Modello delle traduzioni e traduzione italiana |
| `scripts/build/` | Build dei pacchetti, della ISO, della documentazione, delle traduzioni |
| `scripts/verify/` | Verifica di una ISO senza avviarla |
| `tests/` | Test automatici (pytest), test GUI sotto Xvfb, test in macchina virtuale (`tests/vm/`) |
| `build/`, `dist/`, `logs/`, `checksums/` | Prodotti della build, ignorati da Git |

## Registro delle decisioni (ADR)

### ADR-001 — Base: Ubuntu 24.04 LTS "noble"

**Contesto.** Al momento della scelta (ottobre 2026) le LTS supportate sono
22.04, 24.04 (point release 24.04.5) e 26.04 (point release 26.04.1).

**Decisione.** Ubuntu 24.04 LTS, architettura amd64, con il kernel HWE
(`linux-generic-hwe-24.04`, serie 7.0 al momento della build), lo stesso dei
supporti desktop 24.04.x.

**Motivazioni.**
- Strumenti di creazione maturi e verificati: `casper` e `ubiquity` sono usati
  dai flavour ufficiali 24.04; l'host di build è anch'esso 24.04.
- Supporto standard di sicurezza fino ad aprile 2029.
- 26.04 introduce cambiamenti profondi (GNOME 50 solo Wayland, `sudo-rs`,
  coreutils in Rust, kernel 7.0 come base) che richiedono una validazione
  dedicata prima di essere adottati: la priorità del progetto è la stabilità.

**Conseguenze.** La versione base è un parametro (`TROTA_BASE_SUITE` in
`scripts/build/config.env`): la migrazione a 26.04 è prevista per Trota OS 2.0,
dopo i test descritti in [testing.md](testing.md).

### ADR-002 — Metodo di build: debootstrap + chroot + casper + xorriso

**Alternative valutate.**
1. *Remaster dell'ISO ufficiale* (estrarre e modificare la squashfs): la ISO
   desktop 24.04 usa squashfs a livelli e l'installer `ubuntu-desktop-bootstrap`
   (snap) legato alla pipeline Launchpad/livecd-rootfs; la modifica è fragile e
   poco riproducibile.
2. *livecd-rootfs/live-build* come Canonical: richiede l'infrastruttura
   Launchpad e una configurazione molto più ampia.
3. **Build da zero** con `debootstrap`, installazione dei pacchetti in chroot,
   `casper` per la sessione live, `mksquashfs` e `xorriso`.

**Decisione.** Opzione 3: ogni passaggio è uno script leggibile e ripetibile
(`scripts/build/build-iso.sh`, a stadi), tutti i pacchetti provengono
dall'archivio Ubuntu firmato, i pacchetti Trota sono compilati in un chroot
pulito (`build-packages.sh`).

### ADR-003 — Installer: ubiquity

Ubuntu Desktop 24.04 usa `ubuntu-desktop-bootstrap` (snap Flutter + subiquity)
che dipende dal formato di immagine della pipeline Canonical. `ubiquity`
(installer storico di Ubuntu, pacchetto deb nella versione 24.04.5) è ancora
mantenuto in noble ed è stato usato dai flavour 24.04; si integra direttamente
con `casper`, supporta installazioni non presidiate con preseed (fondamentale
per i test automatici) e rimuove da solo i pacchetti live
(`casper/filesystem.manifest-remove`).
È quindi l'installer *della base Ubuntu* più adatto a una build riproducibile.

Requisiti di ubiquity emersi dai test in VM (vedi [testing.md](testing.md)):
- deve essere installato uno slideshow (`ubiquity-slideshow-trota`), altrimenti
  ubiquity perde i privilegi all'avvio della copia e va in crash;
- il supporto deve contenere un archivio APT (`dists/`, `pool/`), perché il
  passo `apt-setup` esegue sempre `apt-cdrom add`; Trota OS vi inserisce i
  propri pacchetti.

### ADR-004 — Catena di avvio: shim e GRUB firmati da Canonical

Il supporto UEFI usa `shimx64.efi.signed` (firmato con la Microsoft UEFI CA) e
`gcdx64.efi.signed` (GRUB firmato da Canonical): **Secure Boot resta attivo**.
Nessun binario di avvio è ricompilato o firmato da Trota OS. Il BIOS legacy usa
l'immagine El Torito di GRUB `i386-pc`. Il sistema installato usa i pacchetti
`shim-signed` e `grub-efi-amd64-signed` di Ubuntu, già presenti nella squashfs
così che l'installer non debba scaricarli (l'installazione
completamente senza rete non è ancora stata verificata).

### ADR-005 — Identificazione del sistema (os-release)

`/usr/lib/os-release` è sostituito tramite `dpkg-divert` dal pacchetto
`trota-release`; il file originale resta in `/usr/lib/os-release.ubuntu` ed è
aggiornato da `base-files`. I campi leggibili (`NAME`, `PRETTY_NAME`, `LOGO`,
URL) identificano Trota OS; i campi tecnici `ID=ubuntu`, `VERSION_ID=24.04`,
`VERSION_CODENAME=noble` restano quelli della base perché:
- `lsb_release` (usato da `aptsources`, *Software e aggiornamenti*,
  `add-apt-repository`, `ubuntu-drivers`) deriva l'ID della distribuzione da
  `ID`; con `ID=trota` il sistema non verrebbe più riconosciuto come Ubuntu e
  PPA e repository di terze parti smetterebbero di funzionare;
- molti installer di terze parti costruiscono gli URL dei repository da
  `ID`/`VERSION_ID`/`VERSION_CODENAME`.
La versione di Trota OS è nei campi `TROTA_VERSION` e `TROTA_CODENAME`, come
consentito da os-release(5). Questo non presenta Trota OS come Ubuntu ufficiale:
il nome mostrato all'utente, il marchio e la documentazione sono quelli di
Trota OS (vedi [licensing.md](licensing.md)).

### ADR-006 — Snap: Firefox e App Center "seeded"

Su Ubuntu 24.04 Firefox è distribuito da Mozilla come snap; il pacchetto deb
`firefox` è solo una transizione che esegue `snap install` (impossibile in un
chroot). Trota OS esegue `snap prepare-image` come l'immagine ufficiale: gli
snap e le loro dipendenze (basi `core24`, runtime `gnome-46-2404`,
`mesa-2404`, `gtk-common-themes`) sono risolti leggendo i loro `snap.yaml` e
installati da `snapd` al primo avvio, senza rete. Snap non è rimosso: è parte
dell'ecosistema Ubuntu.

### ADR-007 — Aggiornamenti

- Gli aggiornamenti di sicurezza e correttivi arrivano dall'archivio Ubuntu
  (`noble-security`, `noble-updates`), con `unattended-upgrades` attivo come
  in Ubuntu.
- I pacchetti Trota OS sono normali `.deb`: un repository APT firmato di
  Trota OS (gratuito, ad es. GitHub Pages) è previsto ma **non ancora
  pubblicato**; finché non esiste, gli aggiornamenti di Trota OS si
  distribuiscono come nuove ISO (vedi [release-notes.md](release-notes.md)).
- L'aggiornamento automatico di release verso la LTS successiva di Ubuntu è
  impostato su `Prompt=never` (`/etc/update-manager/release-upgrades`):
  passare a 26.04 senza una versione di Trota OS validata potrebbe rompere il
  sistema. L'amministratore può riattivarlo consapevolmente.

### ADR-008 — Selezione dei pacchetti e telemetria

L'elenco desktop parte dalle *Recommends* di `ubuntu-desktop-minimal` e ne
esclude, con motivazione in `packages/manifest/excluded.list`, telemetria e
segnalazione automatica (`ubuntu-report`, `whoopsie`, `apport`, `kerneloops`,
`popularity-contest`), servizi di accesso remoto (`gnome-remote-desktop`,
`openssh-server`), `cloud-init` e l'onboarding Ubuntu (sostituito da Trota
Welcome). Durante la build questi pacchetti hanno priorità APT −1, così nessuna
dipendenza "Recommends" può reintrodurli; la build fallisce se uno risulta
installato. Sono aggiunti strumenti per sviluppatori, rete, sistema, LibreOffice
e componenti Vulkan/gamemode per il gaming. `ubuntu-wallpapers` non può essere
escluso perché `gnome-shell` di Ubuntu ne dipende.

### ADR-009 — Configurazione del desktop

Nessun componente di GNOME è sostituito o modificato. Le impostazioni
predefinite sono in `90_trota-os.gschema.override`, che ripete le chiavi anche
nelle sezioni specifiche di sessione usate da Ubuntu (`:ubuntu`,
`:GNOME-Greeter`) per avere precedenza. Il profilo del terminale è un database
dconf di sistema (`/etc/dconf/db/trota.d`). Tema Yaru scuro (accento arancione
di Yaru, il più vicino alla palette Trota), font Inter, sfondi Trota, dock
grafite. Tutto resta modificabile dall'utente.

### ADR-010 — Applicazioni originali

Python 3.12 + PyGObject + GTK 4.14 + libadwaita 1.5 (versioni di noble).
Ogni applicazione separa un back-end in sola libreria standard (testabile senza
display, con un *runner* di comandi iniettabile) dall'interfaccia. Regole:
nessun comando tramite shell, nessun privilegio amministrativo, nessuna rete
tranne il test DNS esplicito di Diagnostics, nessuna password memorizzata,
nessuna modifica automatica del sistema. Le versioni a riga di comando
(`--text`, `--json`) non caricano GTK.

### ADR-011 — Sessione live e preseed di test

Il preseed per l'installazione automatica è un file di **test**
(`tests/vm/install.seed`): viene inserito nell'initrd della sola VM di test,
con una password casuale generata a ogni esecuzione. L'ISO pubblicata non
contiene preseed né password.
