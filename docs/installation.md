# Installazione

## Requisiti hardware

I valori **misurati** provengono dai test in macchina virtuale descritti in
[testing.md](testing.md); gli altri sono **stime** basate sui requisiti di
Ubuntu 24.04 Desktop e non sono ancora stati verificati su hardware reale.

| Risorsa | Minimo | Consigliato | Tipo di dato |
|---|---|---|---|
| Processore | x86-64 a 64 bit, 2 core, 2 GHz | 4+ core recenti | Stima |
| Memoria RAM | 4 GB | 8 GB (16 GB per sviluppo/gaming) | Minimo stimato; **misurato** a riposo dopo il login: 0,7–1,4 GB (sessione live: 1,2 GB) |
| Spazio su disco | 25 GB | 60 GB+ su SSD | **Misurato** subito dopo l'installazione: 9,5 GB (di cui 2 GB di swapfile) |
| Grafica | 1024×768, qualsiasi scheda supportata da Linux | GPU con driver Vulkan (Intel, AMD, NVIDIA con driver proprietario) | Stima |
| Firmware | UEFI (anche con Secure Boot) o BIOS legacy | UEFI | UEFI + Secure Boot verificato in VM; BIOS: vedi [testing.md](testing.md) |
| Supporto di installazione | Chiavetta USB da 4 GB o DVD | Chiavetta USB 3 | ISO misurata: 2,37 GB |
| Rete | Facoltativa per l'installazione (prevista) | Necessaria per aggiornamenti e per installare applicazioni (GNOME Software, Flathub) | Installazione verificata in VM **con** rete; senza rete non ancora verificata |

Le misure provengono da una VM QEMU (4 vCPU emulate, 4 GB RAM, disco virtio da
25 GB); dettagli in [testing.md](testing.md). I requisiti di CPU e grafica non
sono stati misurati: su hardware reale vanno ancora verificati.

## Scaricare e verificare l'immagine

Accanto a ogni ISO è pubblicato il file `.sha256`. Verifica sempre l'immagine
prima di usarla:

```sh
sha256sum -c trota-os-1.0-amd64.iso.sha256
```

Deve comparire `trota-os-1.0-amd64.iso: OK`.

## Creare la chiavetta USB

> Tutti i dati sulla chiavetta verranno cancellati. Controlla due volte di
> aver scelto il dispositivo giusto.

- **Da Ubuntu/Trota OS**: *Dischi* → seleziona la chiavetta → menu ⋮ →
  *Ripristina immagine disco…* → scegli la ISO.
- **Da Windows o macOS**: [balenaEtcher](https://etcher.balena.io/) o
  [Rufus](https://rufus.ie/) (in Rufus scegli la modalità *immagine DD*).
- **Da riga di comando** (Linux), sostituendo `/dev/sdX` con il dispositivo
  della chiavetta (verificato con `lsblk`):
  ```sh
  sudo dd if=trota-os-1.0-amd64.iso of=/dev/sdX bs=4M status=progress conv=fsync
  ```

## Avvio

1. Inserisci la chiavetta e accendi il computer premendo il tasto del menu di
   avvio (spesso F12, F11, F8 o Esc).
2. Scegli la voce della chiavetta (con la dicitura *UEFI* se presente).
3. Nel menu di Trota OS:
   - **Try or Install Trota OS** — sessione live con installer;
   - **Trota OS (safe graphics)** — se lo schermo resta nero;
   - **Install Trota OS (no live session)** — avvia direttamente l'installer.

Secure Boot può restare attivo.

## Installazione

1. Nella prima finestra scegli la lingua e poi **Install Trota OS** (oppure
   *Try* per provare il sistema senza modificare il disco; l'installer resta
   disponibile come icona).
2. Tastiera, rete (facoltativa), tipo di installazione (*normale*) e, se vuoi,
   driver di terze parti per grafica e Wi-Fi.
3. Tipo di installazione:
   - *Cancella il disco e installa* — usa tutto il disco (ext4);
   - *Installa accanto a…* — se è presente un altro sistema operativo;
   - *Altro* — partizionamento manuale.
   Puoi scegliere la cifratura del disco (LVM + LUKS) dalle *Funzioni avanzate*.
4. Fuso orario, nome, nome del computer e password. Il primo utente è
   amministratore (`sudo`).
5. Al termine riavvia e rimuovi la chiavetta.

## Primo avvio

- Al primo accesso si apre **Benvenuto in Trota OS**: da lì trovi
  impostazioni, aggiornamenti, driver aggiuntivi, gli strumenti Trota e la
  documentazione. Puoi disattivarne l'apertura automatica.
- Firefox è già installato (pacchetto `.deb` di Mozilla, aggiornato con gli
  altri pacchetti). Per altre applicazioni apri **Software**: trovi i
  pacchetti Ubuntu e le applicazioni Flatpak di Flathub. Trota OS non usa
  gli snap.
- Connettiti a Internet e apri **Aggiornamenti software** per installare gli
  aggiornamenti usciti dopo la data della ISO.
- **Diagnostica Trota** verifica in un clic spazio su disco, rete, kernel,
  sicurezza, servizi, errori e aggiornamenti.
