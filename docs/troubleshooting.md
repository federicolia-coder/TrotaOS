# Risoluzione dei problemi

Le soluzioni sono volutamente prudenti: nessuna richiede di disattivare
meccanismi di sicurezza. Prima di qualunque intervento sui dischi, fai un
backup dei dati.

Il primo strumento da usare è **Trota Diagnostics** (menu applicazioni →
*Diagnostica Trota*, oppure `trota-diagnostics --text` nel terminale): esegue
controlli in sola lettura e suggerisce cosa fare.

## Avvio del supporto di installazione

| Problema | Soluzione |
|---|---|
| Il PC non avvia dalla chiavetta | Scegli la chiavetta dal menu di avvio del firmware (F12, F11, Esc o F8 a seconda del produttore). Riscrivi la chiavetta in modalità immagine (vedi [installation.md](installation.md)): copiare il file ISO dentro una chiavetta non funziona |
| Errore *Secure Boot violation* | Trota OS usa il bootloader firmato da Canonical/Microsoft e funziona con Secure Boot. Se il firmware accetta solo Windows, abilita nel firmware la CA "Microsoft 3rd Party UEFI CA" (spesso chiamata *Other OS* o *Microsoft UEFI CA*). Disattivare Secure Boot non è necessario |
| Schermo nero o immagine distorta dopo il menu | Scegli **Trota OS (safe graphics)** nel menu: avvia con `nomodeset` |
| Menu senza grafica, solo testo | Normale su alcuni firmware: il tema grafico di GRUB è facoltativo, il menu funziona comunque |
| Avvio molto lento dal DVD | Usa una chiavetta USB 3: la sessione live legge continuamente dal supporto |

## Installazione

| Problema | Soluzione |
|---|---|
| Il disco non compare nell'installer | Su alcuni portatili Intel il controller è in modalità RAID/RST: nel firmware imposta il disco su AHCI (solo se non ospita già Windows con RST, altrimenti Windows non si avvierà) |
| Installazione accanto a Windows | Disattiva l'*avvio rapido* di Windows e sospendi BitLocker prima di ridimensionare la partizione |
| Errore nell'installazione di GRUB | Verifica che il firmware sia nella stessa modalità (UEFI o BIOS) con cui hai avviato la chiavetta e che esista una partizione EFI |

## Dopo l'installazione

| Problema | Soluzione |
|---|---|
| Wi-Fi o scheda video non funzionano bene | Apri *Driver aggiuntivi* (Benvenuto → Primi passi) per i driver proprietari, ad es. NVIDIA |
| *Aggiornamenti software* segnala errori | `sudo apt update` nel terminale mostra quale repository non risponde; disattiva i PPA non più mantenuti in *Software e aggiornamenti → Altro software* |
| Spazio su disco esaurito | *Analizzatore di utilizzo del disco*; `sudo apt autoremove` e `sudo apt clean` liberano pacchetti e cache non più necessari; `snap list --all` mostra vecchie revisioni degli snap |
| Una applicazione snap non si avvia | `snap changes` mostra se l'installazione iniziale è ancora in corso (al primo avvio può richiedere qualche minuto) |
| Audio assente | *Impostazioni → Audio*: scegli il dispositivo di uscita corretto; `systemctl --user status pipewire wireplumber` mostra lo stato del server audio |
| Non compare la finestra di benvenuto | È stata disattivata: riaprila dal menu delle applicazioni (*Benvenuto in Trota OS*) |
| Errori nel registro di sistema | Molti sono innocui. Apri *Registri* e allega i messaggi rilevanti a una segnalazione |

## Raccogliere informazioni per una segnalazione

```sh
trota-system-info --text      # versione, hardware, dischi, rete (nessun file personale)
trota-diagnostics --text      # esito dei controlli
journalctl -b -p err --no-pager | tail -50   # errori dall'ultimo avvio
```

Apri una segnalazione su https://github.com/federicolia-coder/TrotaOS/issues
(per le vulnerabilità segui invece [security.md](security.md)).
