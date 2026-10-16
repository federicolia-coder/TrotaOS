# Generazione della ISO

Procedura riproducibile per compilare i pacchetti Trota OS e generare l'immagine
ISO live e installabile. Tutto avviene in chroot sotto `build/`: il sistema host
non viene modificato, a parte l'installazione degli strumenti elencati sotto.

## Requisiti

| Requisito | Valore |
|---|---|
| Sistema host | Ubuntu 24.04 LTS (amd64), fisico, VM o container privilegiato |
| Privilegi | `root` (debootstrap, chroot, mount di proc/sys/dev) |
| Spazio su disco | ~25 GB liberi (chroot ~9 GB, ISO tree ~4 GB, cache, ISO ~3,5 GB) |
| RAM | 4 GB minimo, 8 GB consigliati (mksquashfs parallelo) |
| Rete | HTTP verso archive.ubuntu.com / security.ubuntu.com, HTTPS verso api.snapcraft.io |
| Tempo | ~45–60 minuti al primo avvio su 4 core (misure sotto) |

Strumenti dell'host:

```sh
sudo apt install debootstrap squashfs-tools xorriso mtools dosfstools rsync \
    grub-pc-bin grub-efi-amd64-bin dpkg-dev python3 \
    qemu-system-x86 qemu-utils ovmf          # solo per i test in VM
```

Gli strumenti per compilare i pacchetti (debhelper, dh-python, gettext,
librsvg2-bin, python3-markdown, python3-pytest) sono installati
automaticamente nel chroot di build, non sull'host.

## Procedura

```sh
git clone https://github.com/federicolia-coder/TrotaOS.git && cd TrotaOS
sudo ./scripts/build/build-packages.sh     # 1. pacchetti .deb in chroot pulito
sudo ./scripts/build/build-iso.sh          # 2. immagine completa
./scripts/verify/verify-iso.sh dist/trota-os-1.0-amd64.iso   # 3. verifica
```

Risultati:

| Percorso | Contenuto |
|---|---|
| `build/packages/` | Pacchetti `trota-*.deb`, `.buildinfo`, `.changes` |
| `dist/trota-os-1.0-amd64.iso` | Immagine ibrida (DVD/USB, BIOS e UEFI) |
| `dist/trota-os-1.0-amd64.manifest` | Elenco esatto dei pacchetti e versioni |
| `dist/*.sha256`, `checksums/*.sha256` | Checksum SHA-256 |
| `logs/build-*.log` | Log completi di ogni esecuzione |
| `build/` | Chroot, albero della ISO, cache del bootstrap (temporanei) |

Le ISO non vanno aggiunte a Git (`dist/` è ignorata).

## Stadi della build

`build-iso.sh` è diviso in stadi ripetibili singolarmente:
`sudo ./scripts/build/build-iso.sh <stadio> [<stadio>…]`.

| Stadio | Cosa fa | Durata misurata* |
|---|---|---|
| `bootstrap` | `debootstrap` di noble (con cache in `build/cache/`) | 170 s (primo), pochi s con cache |
| `packages` | Sorgenti APT ufficiali, pin temporaneo dei pacchetti esclusi, installazione dei manifest (`packages/manifest/*.list`) | 403 s |
| `trota` | Installa i pacchetti `build/packages/*.deb`; fallisce se un pacchetto escluso risulta installato | ~60 s |
| `snaps` | Risolve le dipendenze degli snap e li prepara con `snap prepare-image` (seed) | ~3 min |
| `customize` | casper.conf, locale, schemi GSettings, dconf, `Prompt=never` per i rilasci, APT news disattivate, initramfs con verifica di tema Plymouth e casper, pulizia (machine-id, log, cache) | ~1 min |
| `iso` | kernel/initrd, manifest, squashfs (xz), `.disk/info`, archivio APT del supporto (`dists/`, `pool/` con i pacchetti Trota, richiesto da ubiquity), `md5sum.txt`, GRUB BIOS ed EFI firmato, `efi.img`, `xorriso` | ~8 min (xz, 4 core) |
| `checksum` | SHA-256 e `verify-iso.sh` | ~30 s |
| `clean` | Rimuove chroot e albero ISO (mantiene cache e pacchetti) | — |

\* Misurate su 4 vCPU Xeon 2,8 GHz, 16 GB RAM, rete del data center. Con
`TROTA_SQUASHFS_COMP=zstd` lo stadio `iso` è molto più rapido ma l'immagine è
più grande.

## Parametri

Tutti in `scripts/build/config.env`, sovrascrivibili dall'ambiente:

```sh
sudo TROTA_MIRROR=http://it.archive.ubuntu.com/ubuntu ./scripts/build/build-iso.sh
sudo TROTA_SQUASHFS_COMP=zstd ./scripts/build/build-iso.sh iso checksum
```

Se l'host esce in HTTPS tramite un proxy che ispeziona TLS, passare il
certificato con `TROTA_BUILD_CA_BUNDLE=/percorso/ca.crt` (usato solo durante
la build, non entra nell'immagine). Le variabili `HTTP_PROXY`/`HTTPS_PROXY`
dell'host sono inoltrate al chroot.

## Come funziona l'avvio dell'immagine

- **BIOS**: El Torito → `boot/grub/i386-pc/eltorito.img` (GRUB `i386-pc`) →
  `boot/grub/grub.cfg`. Per le chiavette USB, MBR ibrido (`boot_hybrid.img`).
- **UEFI**: partizione EFI aggiunta (GPT) e voce El Torito EFI → `bootx64.efi`
  (shim firmato Microsoft) → `grubx64.efi` (GRUB firmato Canonical) →
  `boot/grub/grub.cfg`. Secure Boot resta attivo.
- GRUB carica `casper/vmlinuz` e `casper/initrd` con `boot=casper`; casper
  monta `filesystem.squashfs` in overlay e avvia la sessione live (utente
  `trota`, accesso automatico). L'icona dell'installer avvia `ubiquity`.

## Build in CI

Le risorse gratuite di CI (GitHub Actions: 14 GB di disco, limiti sugli
artefatti) non bastano in modo affidabile per costruire e conservare una ISO
da ~3,5 GB. La CI può eseguire i test e la compilazione dei pacchetti; la ISO
si costruisce in locale con la procedura sopra.

## Problemi di build comuni

| Sintomo | Causa e soluzione |
|---|---|
| `Temporary failure resolving` nel chroot | Il DNS dell'host non è raggiungibile: lo script copia `/etc/resolv.conf` dell'host in `/run` del chroot; verificare che l'host risolva i nomi |
| `held broken packages` | Un pacchetto escluso è richiesto come *Depends* (es. `ubuntu-wallpapers` da `gnome-shell`): toglierlo da `excluded.list` e documentarlo |
| `initrd is missing …two-step.so` | Manca `plymouth-theme-spinner`: il controllo blocca la build prima di produrre un'immagine senza splash |
| `refusing to touch path outside build/` | Protezione: gli script cancellano/montano solo sotto `build/` |
| Spazio esaurito | `sudo ./scripts/build/build-iso.sh clean` e rimuovere `build/pkg-chroot` |
