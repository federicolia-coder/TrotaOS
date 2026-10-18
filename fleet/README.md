# Trota Fleet

Pannello web per gestire da un'unica pagina i dispositivi Trota OS Server,
Cloud e Kiosk dei clienti. Software proprietario di TestardStudios (vedi
[LICENSE](LICENSE)): non fa parte di Trota OS e non entra nei suoi pacchetti.

## Cosa fa

- **Dispositivi**: elenco con stato (in linea / non in linea), cliente,
  edizione, indirizzo, aggiornamenti da installare, ultimo contatto. Si può
  filtrare per cliente e cercare per nome, indirizzo o note.
- **Scheda del dispositivo**: sistema, kernel, da quanto è acceso, carico,
  memoria, disco, indirizzi, pagina del kiosk, storico dei comandi con il
  loro risultato. Nome, cliente e note si possono modificare.
- **Comandi**, anche a più dispositivi insieme: cambiare la pagina del kiosk,
  riavviare il kiosk, installare gli aggiornamenti, riavviare il dispositivo.
  Se il dispositivo è spento il comando parte al collegamento successivo.
- **Aggiungi dispositivi**: codici di registrazione per cliente, con un
  numero massimo di dispositivi e una scadenza. Il pannello mostra il codice
  una sola volta, con il comando da dare sul dispositivo e la configurazione
  cloud-init per prepararne molti insieme.

## Come funziona

```
dispositivo (trota-fleet-agent)  ──HTTPS, ogni 60 s──▶  pannello  ◀── browser dell'amministratore
```

- È il dispositivo a chiamare il pannello, mai il contrario: funziona dietro
  NAT e firewall e sul dispositivo non si apre nessuna porta.
- A ogni contatto il dispositivo manda un breve rapporto sul suo stato e
  riceve i comandi in coda. I comandi possibili sono solo i quattro sopra:
  il pannello non può eseguire programmi o comandi di shell sul dispositivo,
  neanche se viene violato.
- Ogni dispositivo ha un segreto suo, dato alla registrazione. Rimuoverlo
  dal pannello lo scollega subito.
- Nel database ci sono solo hash: password (PBKDF2), segreti dei dispositivi,
  sessioni e codici di registrazione (SHA-256).
- Login con limite ai tentativi sbagliati, cookie `HttpOnly` e
  `SameSite=Strict`, token CSRF su ogni modulo, Content-Security-Policy
  senza script esterni o in linea.

Il pannello usa solo la libreria standard di Python 3.10+ e SQLite: nessuna
dipendenza da installare.

## Installazione

### Su un computer con Trota OS (anche un portatile)

```sh
sudo fleet/install.sh
```

Lo script fa cinque cose e si può rilanciare per aggiornare il pannello
senza perdere i dati:

1. copia il pannello in `/opt/trota-fleet` e lo avvia come servizio
   (`trota-fleet-panel`, utente di sistema `trota-fleet`) su
   http://localhost:8080, con una copia del database ogni giorno in
   `/var/lib/trota-fleet-panel/backups` (ultime 14);
2. chiede l'indirizzo pubblico del pannello, es. `https://fleet.testardstudios.it`;
3. crea il primo amministratore;
4. chiede il token di un **Cloudflare Tunnel** e installa `cloudflared`: il
   pannello diventa raggiungibile da Internet in HTTPS senza aprire porte
   sul router. Il token si crea nella dashboard di Cloudflare: Zero Trust →
   Networks → Tunnels → *Create a tunnel* (Cloudflared); nella scheda
   *Public Hostname* si indica il nome (es. `fleet.testardstudios.it`) e il
   servizio `HTTP` → `localhost:8080`. Serve che il dominio sia gestito da
   Cloudflare;
5. su un portatile, con l'alimentatore collegato, toglie la sospensione
   (anche a coperchio chiuso). A batteria il comportamento resta quello
   normale.

Se il computer è spento o in sospensione il pannello non risponde; i
dispositivi continuano a funzionare e si ricollegano da soli.

### Con Podman su Trota OS Server

```sh
podman build -t trota-fleet fleet/
podman volume create trota-fleet
podman run --rm -it -v trota-fleet:/data trota-fleet adduser federico
podman run -d --name trota-fleet --restart=always -p 127.0.0.1:8080:8080 -v trota-fleet:/data \
    -e TROTA_FLEET_PUBLIC_URL=https://fleet.testardstudios.it trota-fleet
```

### Con systemd

```sh
sudo useradd --system --home /var/lib/trota-fleet-panel trota-fleet
sudo install -d /opt/trota-fleet && sudo cp -r fleet/trota_fleet /opt/trota-fleet/
sudo cp fleet/trota-fleet-panel.service /etc/systemd/system/
echo 'TROTA_FLEET_PUBLIC_URL=https://fleet.testardstudios.it' | sudo tee /etc/default/trota-fleet-panel
sudo install -d -o trota-fleet -g trota-fleet -m 700 /var/lib/trota-fleet-panel
sudo systemctl daemon-reload
sudo -u trota-fleet env PYTHONPATH=/opt/trota-fleet TROTA_FLEET_DB=/var/lib/trota-fleet-panel/fleet.db \
    python3 -m trota_fleet adduser federico
sudo systemctl enable --now trota-fleet-panel
```

### HTTPS con Caddy

```sh
sudo apt install caddy
sudo cp fleet/Caddyfile.example /etc/caddy/Caddyfile   # cambiare il nome di dominio
sudo systemctl reload caddy
sudo ufw allow 80,443/tcp
```

### Impostazioni

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `TROTA_FLEET_DB` | `/var/lib/trota-fleet-panel/fleet.db` | database SQLite |
| `TROTA_FLEET_LISTEN` | `127.0.0.1:8080` | indirizzo e porta (IPv4) |
| `TROTA_FLEET_PUBLIC_URL` | indirizzo della richiesta | mostrato nei comandi di registrazione |
| `TROTA_FLEET_BEHIND_PROXY` | `0` | `1` = usa le intestazioni `X-Forwarded-*` del proxy |
| `TROTA_FLEET_INTERVAL` | `60` | secondi tra un contatto e l'altro dei dispositivi |

Altri amministratori o cambio password: `python3 -m trota_fleet adduser NOME`.
Backup: una copia del file del database (`sqlite3 fleet.db ".backup copia.db"`).

## Collegare un dispositivo

Nel pannello, **Aggiungi dispositivi** → cliente, numero di dispositivi,
validità → **Crea il codice**. Poi sul dispositivo:

```sh
sudo trota-fleet-agent enroll https://fleet.testardstudios.it TF-xxxxxxxx
sudo systemctl enable --now trota-fleet-agent
```

oppure, prima della prima accensione, con cloud-init (il pannello mostra il
testo pronto). L'agente è già installato nelle immagini Server, Cloud e Kiosk
di Trota OS e resta fermo finché non viene configurato. Dettagli:
[docs/fleet.md](../docs/fleet.md).

## Test

```sh
python3 -m pytest -q fleet/tests
```

Avviano un pannello vero su una porta locale e lo usano con l'agente vero e
un browser simulato: login, codici, registrazione, comandi, risultati,
escaping dei dati inviati dai dispositivi, CSRF, limiti.

## Prossimi passi possibili

- accesso per i clienti, ciascuno solo ai propri dispositivi;
- avvisi via email quando un dispositivo va fuori linea;
- pianificazione degli aggiornamenti in una fascia oraria;
- grafici di memoria, disco e temperatura nel tempo.
