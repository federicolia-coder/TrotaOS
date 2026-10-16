# Installazione

## Requisiti hardware

I valori **misurati** provengono dai test in macchina virtuale descritti in
[testing.md](testing.md); gli altri sono **stime** basate sui requisiti di
Ubuntu 24.04 Desktop e non sono ancora stati verificati su hardware reale.

| Risorsa | Minimo | Consigliato | Tipo di dato |
|---|---|---|---|
| Processore | x86-64 a 64 bit, 2 core, 2 GHz | 4+ core recenti | Stima |
| Memoria RAM | 4 GB | 8 GB (16 GB per sviluppo/gaming) | Stima; uso misurato a riposo: vedi sotto |
| Spazio su disco | 25 GB | 60 GB+ su SSD | Sistema installato misurato: vedi sotto |
| Grafica | 1024×768, qualsiasi scheda supportata da Linux | GPU con driver Vulkan (Intel, AMD, NVIDIA con driver proprietario) | Stima |
| Firmware | UEFI (anche con Secure Boot) o BIOS legacy | UEFI | Entrambi verificati in VM |
| Supporto di installazione | Chiavetta USB da 8 GB o DVD dual layer | Chiavetta USB 3 | ISO misurata: 3,7 GB |
| Rete | Facoltativa per l'installazione | Necessaria per aggiornamenti e App Center | Installazione offline verificata in VM |

**Misure in VM** (QEMU, 4 vCPU, 4 GB RAM, disco virtio da 25 GB): i valori
sono riportati nella sezione "Risultati" di [testing.md](testing.md).

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
- Firefox e App Center vengono completati da snapd nei primi minuti dopo
  l'avvio (non serve la rete, sono inclusi nell'immagine).
- Connettiti a Internet e apri **Aggiornamenti software** per installare gli
  aggiornamenti usciti dopo la data della ISO.
- **Diagnostica Trota** verifica in un clic spazio su disco, rete, kernel,
  sicurezza, servizi, errori e aggiornamenti.
