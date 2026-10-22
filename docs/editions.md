# Edizioni di Trota OS

Trota OS 1.0 esiste in quattro edizioni, costruite dallo stesso repository con
la stessa base, gli stessi aggiornamenti di sicurezza e la stessa identità.
La Desktop ha anche una variante **VR** per la realtà virtuale (sotto).

| Edizione | Per cosa | Formato | Come si costruisce |
|---|---|---|---|
| **Desktop** | Uso personale, ufficio, scuola, sviluppo, gaming | ISO live con installer (BIOS/UEFI, Secure Boot) | `build-iso.sh` |
| **Server / Edge** | Server fisici e virtuali, mini PC e gateway edge, laboratori | Immagine disco pronta (`.img.xz`, `.qcow2`) | `build-image.sh server` |
| **Cloud** | Cloud pubblici e privati (OpenStack, Proxmox, KVM, …) | Immagine disco (`.qcow2`, `.img.xz`) con cloud-init | `build-image.sh cloud` |
| **Kiosk / Signage** | Chioschi, totem, schermi informativi, dashboard, menu | Immagine disco pronta (`.img.xz`, `.qcow2`) | `build-image.sh kiosk` |
| **Desktop VR** (variante) | Realtà virtuale su PC e con visori autonomi | ISO live con installer | `TROTA_FLAVOR=vr build-iso.sh` |

Le immagini disco non hanno un installer: si scrivono su un disco (o si
importano in una piattaforma di virtualizzazione) e al primo avvio
**cloud-init** completa la configurazione: allarga la partizione al disco
intero, genera le chiavi SSH, crea l'utente, configura la rete.

## Server / Edge

- Nessuna interfaccia grafica: circa 380 pacchetti e 270 MB di RAM in uso
  dopo l'avvio, kernel generico con i
  firmware per l'hardware reale (esclusi quelli da data center, vedi
  [architecture.md](architecture.md)).
- **SSH solo con chiave**, root senza accesso remoto, firewall (`ufw`) attivo
  con la sola porta 22 aperta.
- **Hardening di base** del kernel (`/usr/lib/sysctl.d/60-trota-hardening.conf`):
  puntatori e log del kernel riservati, `ptrace` e BPF non privilegiato
  limitati, protezione di link e FIFO, niente redirect ICMP o source routing,
  SYN cookies. AppArmor attivo, aggiornamenti di sicurezza automatici, journal
  di sistema limitato (500 MB) anche sui dispositivi piccoli.
- **Container**: Podman (CLI compatibile con Docker, rootless per l'utente),
  con `passt`/`slirp4netns` per la rete.

**Primo accesso senza cloud-init** (server fisico, mini PC): utente `trota`,
password `trota`, da cambiare obbligatoriamente al primo accesso **sulla
console** (schermo e tastiera, o porta seriale). Via SSH si entra solo con
una chiave.

**Primo accesso con cloud-init** (consigliato): una chiavetta o un'immagine
ISO con etichetta `CIDATA` che contiene `user-data` e `meta-data` (data source
*NoCloud*), oppure il servizio di metadati della piattaforma cloud:

```yaml
#cloud-config
hostname: edge-01
ssh_authorized_keys:
  - ssh-ed25519 AAAA... admin@example
```

Scrivere l'immagine su un disco (attenzione: cancella il disco indicato):

```sh
xzcat trota-os-server-1.0-amd64.img.xz | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync
```

oppure con un programma grafico come balenaEtcher o GNOME Disks.

## Cloud

Come Server, ma con il kernel *virtual* (più piccolo, solo hardware virtuale)
e il `qemu-guest-agent`; non esiste una password: utente `trota` con le
chiavi SSH fornite dalla piattaforma tramite cloud-init (EC2, Azure, GCE,
OpenStack, Oracle, ConfigDrive, NoCloud).

Esempi:
- **Proxmox/KVM/libvirt**: importare `trota-os-cloud-1.0-amd64.qcow2` come disco
  e aggiungere un drive cloud-init;
- **OpenStack**: `openstack image create --disk-format qcow2 --file trota-os-cloud-1.0-amd64.qcow2 trota-os-1.0`.

## Kiosk / Signage

Mostra una sola pagina web a tutto schermo sul primo monitor: Firefox in
modalità kiosk dentro il compositor Wayland **cage**, come utente senza
privilegi `kiosk`, con un profilo vuoto a ogni avvio. Se il browser si chiude
o va in crash riparte da solo; ogni giorno alle 04:00 viene riavviato.

- Pagina da mostrare: `/etc/trota-kiosk.conf` → `TROTA_KIOSK_URL=https://…`,
  poi `sudo systemctl restart trota-kiosk` (o riavvio).
- Policy di Firefox (`/etc/firefox/policies/policies.json`): nessuna richiesta
  di aggiornamento (Firefox si aggiorna con il sistema), nessuna telemetria,
  niente gestore password, strumenti per sviluppatori o pagine di benvenuto.
- Console di testo bloccate per impostazione predefinita
  (`TROTA_KIOSK_VT_SWITCH=no`); amministrazione via SSH con chiave o porta
  seriale.
- Per molti schermi: cloud-init con `write_files` per `/etc/trota-kiosk.conf`
  (esempio in `/usr/share/doc/trota-kiosk/README`).

Primo accesso come per Server (utente `trota`, password `trota` da cambiare,
solo sulla porta seriale o via SSH con chiave, perché lo schermo è occupato
dal kiosk).

## Desktop VR (Trota OS VR)

La stessa ISO desktop con in più lo stack per la realtà virtuale. Contiene
solo pacchetti dell'archivio Ubuntu (`packages/manifest/vr.list`):

- **Monado** (`monado-service`, `libopenxr1-monado`): runtime OpenXR libero,
  registrato come runtime predefinito (`/etc/xdg/openxr/1/active_runtime.json`);
- **regole udev** per visori e controller usabili senza root (`xr-hardware`,
  `steam-devices`: solo le regole, non Steam);
- l'app **Trota VR** (pacchetto `trota-vr`): controlla scheda video e driver,
  Vulkan, visori collegati, runtime OpenXR e permessi, e su richiesta installa
  da Flathub **WiVRn** (VR del PC su Meta Quest, Pico e altri visori autonomi
  via Wi-Fi) o **Steam** (SteamVR, giochi VR, visori da PC come Valve Index e
  HTC Vive). Steam è software proprietario di Valve: per questo non è
  preinstallato. Da terminale: `trota-vr --text`, `trota-vr --install wivrn`.

Il profilo firewall `WiVRn` (porte 9757 TCP e UDP) è installato ma non
attivo: `sudo ufw allow WiVRn` se il firewall è acceso.

Requisiti consigliati: scheda video AMD o NVIDIA recente (per NVIDIA il
driver proprietario da *Driver aggiuntivi*), 16 GB di RAM, Wi-Fi 6 o rete
via cavo per lo streaming con WiVRn. **Non ancora provata con visori reali.**

```sh
sudo TROTA_FLAVOR=vr ./scripts/build/build-iso.sh     # dist/trota-os-vr-1.0-amd64.iso
```

## Gestione remota

Le tre immagini contengono l'agente di **Trota Fleet**, fermo finché non viene
collegato a un pannello: stato dei dispositivi, cambio della pagina del kiosk,
aggiornamenti e riavvii da remoto. Vedi [fleet.md](fleet.md).

## Rispetto all'offerta "By solution / By industry" di Canonical

Molte voci di quella pagina sono **servizi commerciali** di Canonical
(consulenza, supporto, infrastruttura gestita, certificazioni) e non
funzioni del sistema operativo: Trota OS non li offre. Questa tabella dice
cosa copre Trota OS oggi.

| Area | Trota OS 1.0 | Note |
|---|---|---|
| Desktop, Education | **Desktop** | |
| Containers | **Server / Cloud** con Podman | Kubernetes (es. k3s) si installa sopra, non è incluso |
| Security, Compliance | **Server**: hardening di base, AppArmor, aggiornamenti automatici | Non è una certificazione (CIS, FIPS, DISA-STIG): per quella servono audit e strumenti dedicati |
| Edge computing | **Server / Edge** su x86-64 | |
| Public cloud, Private cloud | **Cloud** (immagine qcow2 con cloud-init) | Le immagini non sono pubblicate nei marketplace dei provider |
| Signage, Kiosk | **Kiosk** | |
| Automation | cloud-init al primo avvio; Ansible e simili funzionano via SSH; pannello Trota Fleet | |
| IoT, Robotics, Automotive, Industrial | Solo hardware x86-64 | Le schede ARM (Raspberry Pi, ecc.) richiederebbero una build dedicata, non ancora disponibile |
| AI/ML, HPC, Data, Storage | Server + container | Driver NVIDIA e CUDA si installano a parte; nessuno stack (Ceph, Spark, MLOps) è preconfigurato |
| Confidential computing, Telco, Managed infrastructure, Financial/Public sector | Non coperto | Richiedono hardware, certificazioni o servizi specifici |

## Verifica

Ogni immagine è provata in macchina virtuale con `tests/vm/vmtest.py image
--image dist/trota-os-<edizione>-1.0-amd64.qcow2 --firmware uefi|bios|secureboot`
(controlli in `tests/vm/checks-image.sh`); i risultati sono in
[testing.md](testing.md).
