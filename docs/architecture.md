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
│ │ nessuno snap: Firefox .deb da packages.mozilla.org, GNOME Software + Flatpak (Flathub)    │   │
│ │ ┌──────────────────────────── pacchetti Trota OS (trota-os) ─────────────────────────┐   │   │
│ │ │ trota-release          os-release (dpkg-divert), identità del sistema              │   │   │
│ │ │ trota-artwork          logo, sfondi, icone, tema Plymouth, tema GRUB               │   │   │
│ │ │ trota-desktop-settings override GSettings, profilo dconf, terminale, GDM           │   │   │
│ │ │ trota-software-sources repository Mozilla, Flathub, blocco di snapd, niente Pro    │   │   │
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

### ADR-006 — Nessuno snap: Firefox da Mozilla, applicazioni da Flathub

**Contesto.** Su Ubuntu 24.04 Firefox e App Center sono snap; il pacchetto deb
`firefox` dell'archivio è solo una transizione che esegue `snap install`. Le
prime build di Trota OS includevano gli snap come l'immagine ufficiale: il seed
(Firefox, App Center, basi `core22`/`core24`, runtime GNOME e Mesa) occupava
**1,5 GB** nell'immagine, `snapd` altri 116 MB, e al primo avvio
`snapd.seeded.service` impiegava molti minuti (ed era fallito una volta nei
test in emulazione).

**Decisione.** Trota OS non include snap (come Linux Mint):
- `snapd` è escluso dall'immagine e bloccato da un pin APT
  (`/etc/apt/preferences.d/trota-no-snap.pref`), così non rientra come
  dipendenza dei pacchetti di transizione di Ubuntu (es. `chromium-browser`);
- **Firefox** è il pacchetto `.deb` ufficiale del repository APT di Mozilla
  (`packages.mozilla.org`, chiave `35BA A0B3 3E9E B396 F59C A838 C0BA 5CE6 DC63
  15A3` inclusa nel pacchetto), con un pin che preferisce la versione Mozilla e
  scarta la transizione di Ubuntu; gli aggiornamenti arrivano con APT
  direttamente da Mozilla, il giorno dell'uscita;
- **GNOME Software** sostituisce App Center: mostra i pacchetti dell'archivio
  Ubuntu e le applicazioni **Flatpak** di **Flathub** (configurato come remote
  di sistema dal pacchetto, anche senza rete).

Tutto è nel pacchetto `trota-software-sources`: rimuoverlo ripristina il
comportamento di Ubuntu (snap installabili).

**Conseguenze.** Le applicazioni distribuite solo come snap non sono
installabili senza rimuovere il blocco; quasi tutte esistono su Flathub. I
pacchetti Mozilla e Flathub sono fonti esterne all'archivio Ubuntu: la fiducia
è riposta in Mozilla (firma del repository) e in Flathub (firma del remote e
revisione delle applicazioni), vedi [security.md](security.md).

### ADR-006b — Niente pubblicità di Ubuntu Pro

`ubuntu-pro-client` resta installato (è una dipendenza di `ubuntu-minimal`, di
*Software e aggiornamenti* e di `update-manager-core`), ma:
- l'hook di `apt upgrade` che stampa gli annunci ESM/Ubuntu Pro è svuotato
  (`/etc/apt/apt.conf.d/99trota-no-pro-ads`);
- i servizi `esm-cache` e `apt-news`, che interrogano Canonical in background a
  ogni `apt update`, sono mascherati; gli APT news sono anche disattivati
  (`pro config set apt_news=false`);
- il banner di login non mostra i link a Landscape/Ubuntu Pro né lo stato ESM
  (`10-help-text`, `91-contract-ua-esm-status` non eseguibili).

Gli aggiornamenti di sicurezza di `noble-security` non cambiano; chi vuole
Ubuntu Pro può comunque attivarlo con `sudo pro attach`.

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

I firmware dell'hardware da data center (switch Mellanox Spectrum e Marvell
Prestera, SmartNIC Netronome, adattatori QLogic FastLinQ, circa 170 MB già
compressi) non vengono estratti grazie a un filtro di dpkg
(`/etc/dpkg/dpkg.cfg.d/trota-firmware-exclude`, pacchetto
`trota-desktop-settings`): i pacchetti restano installati, perché il
metapacchetto del kernel dipende da `linux-firmware`, e gli aggiornamenti
continuano a funzionare. La squashfs usa xz con blocchi da 1 MiB e filtro x86
(circa 5% in meno). Così la ISO sta sotto i 2 GiB e si pubblica su GitHub come
file unico.

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
