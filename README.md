<p align="center"><img src="docs/images/trota-logo-dark.png" alt="Trota OS" width="420"></p>

# Trota OS

**Trota OS** è una distribuzione Linux desktop basata su **Ubuntu 24.04 LTS**,
con un'identità visiva industriale e minimale, pensata per sviluppo software,
amministrazione di sistemi, gaming, studio e uso quotidiano.

Sviluppata e pubblicata da **TestardStudios**.

- Base Ubuntu 24.04 LTS (kernel HWE), GNOME su Wayland, APT/DEB, systemd,
  GRUB, NetworkManager, ext4, PipeWire, AppArmor
- Avvio BIOS e UEFI, **Secure Boot supportato** (shim e GRUB firmati da Canonical)
- Nessun account obbligatorio, **nessuna telemetria**, nessun servizio di rete
  in ascolto, aggiornamenti di sicurezza automatici
- Quattro applicazioni originali (GTK 4 / libadwaita), in inglese e italiano:
  - **Trota Welcome** – guida di primo avvio
  - **Trota System Info** – informazioni sul sistema raccolte localmente
  - **Trota Diagnostics** – controlli di salute in sola lettura
  - **Trota Package Helper** – ricerca nel catalogo APT e istruzioni di installazione

> Trota OS non è un prodotto di Canonical né del progetto Ubuntu.
> Ubuntu è un marchio registrato di Canonical Ltd.

## Stato del progetto

Versione **1.0 "Fario"** — vedi le [note di rilascio](docs/release-notes.md)
per l'elenco di ciò che è stato verificato e dei problemi noti, e
[docs/testing.md](docs/testing.md) per i risultati dei test.

## Avvio rapido

```sh
# Compilare i pacchetti e la ISO (Ubuntu 24.04, root, ~25 GB liberi)
sudo apt install debootstrap squashfs-tools xorriso mtools dosfstools rsync \
    grub-pc-bin grub-efi-amd64-bin dpkg-dev
sudo ./scripts/build/build-packages.sh
sudo ./scripts/build/build-iso.sh
./scripts/verify/verify-iso.sh dist/trota-os-1.0-amd64.iso

# Test automatici
python3 -m pytest tests

# Test in macchina virtuale (QEMU; KVM se disponibile)
sudo tests/vm/vmtest.py live --firmware uefi
sudo tests/vm/vmtest.py install --firmware secureboot
sudo tests/vm/vmtest.py installed --firmware secureboot
```

## Documentazione

| | |
|---|---|
| [Installazione](docs/installation.md) | Requisiti, chiavetta USB, installazione |
| [Generazione della ISO](docs/building.md) | Procedura di build riproducibile |
| [Architettura](docs/architecture.md) | Scelte tecniche (ADR) |
| [Test](docs/testing.md) | Test automatici e in VM, risultati |
| [Risoluzione dei problemi](docs/troubleshooting.md) | Problemi comuni |
| [Sicurezza](docs/security.md) · [Privacy](docs/privacy.md) | Modello di sicurezza, dati trattati |
| [Licenze e marchi](docs/licensing.md) | Componenti, licenze, obblighi |
| [Identità visiva](docs/brand.md) | Logo, palette, asset |

## Struttura del repository

```
applications/      codice delle applicazioni (trota-common = libreria condivisa)
branding/          generatore degli asset, logo, sfondi, icone, temi Plymouth/GRUB
packages/          manifest dei pacchetti dell'immagine e configurazione della ISO
packaging/         pacchetto sorgente Debian (debian/) e file installati
po/                traduzioni
scripts/build/     build di pacchetti, ISO, documentazione, traduzioni
scripts/verify/    verifica dell'immagine
tests/             test automatici; tests/vm/ = test in macchina virtuale
docs/              documentazione
```

`build/`, `dist/`, `logs/` e `checksums/` sono creati dagli script e non sono
versionati: le ISO non vanno mai aggiunte a Git.

## Licenza

Codice: [GPL-3.0-or-later](LICENSE). Grafica e documentazione:
[CC BY-SA 4.0](branding/LICENSE.md). Nome e logo: vedi
[docs/licensing.md](docs/licensing.md). Contributi: [CONTRIBUTING.md](CONTRIBUTING.md).
Vulnerabilità: [SECURITY.md](SECURITY.md).
