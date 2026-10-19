<p align="center"><img src="docs/images/trota-logo-dark.png" alt="Trota OS" width="420"></p>

# Trota OS

**Trota OS** è un sistema operativo desktop leggero, con un'identità visiva
industriale e minimale, pensato per sviluppo software, amministrazione di
sistemi, gaming, studio e uso quotidiano.

Sviluppato e pubblicato da **TestardStudios**.

- Leggero: nessuno snap, nessun indicizzatore o negozio di app in background,
  nessuna telemetria, ISO da circa 2 GB
- GNOME su Wayland, Firefox aggiornato direttamente da Mozilla, applicazioni
  da Flathub, pacchetti APT/DEB, systemd, PipeWire, AppArmor
- Avvio BIOS e UEFI, **Secure Boot supportato**
- Nessun account obbligatorio, nessun servizio di rete in ascolto,
  aggiornamenti di sicurezza automatici
- Quattro applicazioni originali (GTK 4 / libadwaita), in inglese e italiano:
  - **Trota Welcome** – guida di primo avvio
  - **Trota System Info** – informazioni sul sistema raccolte localmente
  - **Trota Diagnostics** – controlli di salute in sola lettura
  - **Trota Package Helper** – ricerca nel catalogo APT e istruzioni di installazione

### Compatibilità

Trota OS usa come base i pacchetti di Ubuntu 24.04 LTS (codename `noble`) e ne
riceve gli aggiornamenti di sicurezza fino ad aprile 2029: i pacchetti `.deb`,
i PPA e i repository pensati per Ubuntu 24.04 funzionano anche su Trota OS.
Trota OS non è un prodotto di Canonical né del progetto Ubuntu; Ubuntu è un
marchio registrato di Canonical Ltd. Dettagli in
[docs/architecture.md](docs/architecture.md) e [docs/licensing.md](docs/licensing.md).

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
