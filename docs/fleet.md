# Gestione remota con Trota Fleet

Le immagini **Server**, **Cloud** e **Kiosk** contengono `trota-fleet-agent`,
il programma che collega il dispositivo a un pannello Trota Fleet. Il
pannello è un servizio di TestardStudios per le aziende (piani *Kiosk e IoT
gestiti* ed *Enterprise*); l'agente è software libero (GPL-3.0-or-later) come
il resto di Trota OS.

Finché non viene configurato, l'agente **non fa niente**: il servizio
`trota-fleet-agent` è abilitato ma viene saltato all'avvio e non si collega a
nessun indirizzo. Il desktop non lo installa.

## Cosa manda e cosa può ricevere

Una volta al minuto il dispositivo chiama il pannello via HTTPS e manda:
nome host, sistema ed edizione, kernel, da quanto è acceso, carico,
memoria, spazio sul disco di sistema, indirizzi IP, numero di aggiornamenti
da installare, se serve un riavvio e, sul kiosk, la pagina mostrata. Non
manda file, nomi utente, log o altro. Il rapporto esatto si vede con:

```sh
trota-fleet-agent status
```

Dal pannello può ricevere solo questi comandi:

| Comando | Cosa fa sul dispositivo |
|---|---|
| Cambia la pagina del kiosk | scrive `TROTA_KIOSK_URL` in `/etc/trota-kiosk.conf` e riavvia il kiosk |
| Riavvia il kiosk | `systemctl restart trota-kiosk` |
| Installa gli aggiornamenti | `apt-get update` e `apt-get full-upgrade`, mantenendo i file di configurazione locali |
| Riavvia il dispositivo | `systemctl reboot`, dopo aver mandato il risultato |

Ogni altro comando viene rifiutato: il pannello non può eseguire programmi o
righe di shell. Sul dispositivo non si apre nessuna porta.

## Collegare un dispositivo

Il codice di registrazione si crea nel pannello (**Aggiungi dispositivi**).

```sh
sudo trota-fleet-agent enroll https://fleet.example.com TF-xxxxxxxx
sudo systemctl enable --now trota-fleet-agent
```

Con cloud-init, prima della prima accensione (anche per molti dispositivi
con lo stesso codice):

```yaml
#cloud-config
write_files:
  - path: /etc/trota-fleet.conf
    content: |
      TROTA_FLEET_URL=https://fleet.example.com
      TROTA_FLEET_TOKEN=TF-xxxxxxxx
```

Il codice viene usato una volta e poi cancellato da `/etc/trota-fleet.conf`;
il segreto ricevuto dal pannello è in `/var/lib/trota-fleet/device.json`,
leggibile solo da root.

## Scollegare un dispositivo

```sh
sudo systemctl disable --now trota-fleet-agent
sudo trota-fleet-agent leave
```

e rimuoverlo anche dal pannello. Se viene rimosso solo dal pannello,
l'agente se ne accorge al contatto successivo e si ferma.

## Problemi

- `journalctl -u trota-fleet-agent` mostra gli errori di collegamento; se il
  pannello non risponde l'agente riprova sempre più di rado, fino a ogni 15
  minuti.
- Il pannello deve essere in HTTPS. Solo per reti di prova:
  `TROTA_FLEET_INSECURE=yes` in `/etc/trota-fleet.conf`.
