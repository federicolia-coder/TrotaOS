# Privacy

Trota OS non raccoglie dati sugli utenti.

- **Nessun account obbligatorio** e nessuna registrazione.
- **Nessuna telemetria**: sono esclusi dall'immagine `ubuntu-report`
  (statistiche hardware), `whoopsie`/`apport`/`kerneloops` (invio di rapporti
  di crash), `popularity-contest` (statistiche d'uso dei pacchetti).
  In GNOME le impostazioni *Segnala problemi tecnici* e *Invia statistiche
  d'uso del software* sono disattivate per impostazione predefinita.
- **Applicazioni Trota OS**: tutte le informazioni (System Info, Diagnostics)
  sono lette localmente e mostrate solo all'utente. Si possono copiare o
  salvare in un file soltanto con un'azione esplicita.

## File locali dell'installer

L'installer ubiquity salva in `/var/log/installer/` i log dell'installazione e
un file `telemetry` con le scelte fatte (lingua, tipo di partizionamento,
durata delle fasi). Il file resta **solo sul computer**: il programma che in
Ubuntu potrebbe inviarlo (`ubuntu-report`) non è installato in Trota OS. Si può
cancellare in sicurezza con `sudo rm /var/log/installer/telemetry`.

## Connessioni di rete effettuate dal sistema

Sono quelle standard di Ubuntu, necessarie al funzionamento:

| Servizio | Destinazione | Scopo | Come disattivarlo |
|---|---|---|---|
| APT, aggiornamenti automatici | archive.ubuntu.com, security.ubuntu.com | Elenchi dei pacchetti e aggiornamenti di sicurezza | *Software e aggiornamenti → Aggiornamenti* |
| APT (Firefox) | packages.mozilla.org | Aggiornamenti di Firefox, insieme agli altri pacchetti | Rimuovere `/etc/apt/sources.list.d/mozilla.sources` (Firefox non sarà più aggiornato) |
| GNOME Software, Flatpak | dl.flathub.org | Catalogo e aggiornamenti delle applicazioni Flatpak, solo se si apre Software o si installano app | *Software → Preferenze* (aggiornamenti automatici) |
| NetworkManager | connectivity-check.ubuntu.com | Rilevamento di captive portal | *Impostazioni → Privacy → Connettività* |
| Sincronizzazione ora | ntp.ubuntu.com | Orologio di sistema | *Impostazioni → Sistema → Data e ora* |
| fwupd (`fwupd-refresh.timer`) | cdn.fwupd.org | Metadati degli aggiornamenti firmware (LVFS); i firmware si installano solo su richiesta | `sudo systemctl disable --now fwupd-refresh.timer` |
| Ubuntu Pro client (`ua-timer.timer`) | contracts.canonical.com | Solo se l'utente attiva Ubuntu Pro. In Trota OS gli "APT news" sono **disattivati** e i servizi `apt-news`/`esm-cache`, che Ubuntu avvia a ogni `apt update`, sono **mascherati** | `sudo systemctl unmask apt-news.service esm-cache.service` |
| Firefox | Mozilla | Funzioni del browser | Impostazioni di Firefox |

Il messaggio del giorno dinamico di Ubuntu (`motd-news`) è inattivo perché il
pacchetto di configurazione `motd-news-config` non è installato.

Trota Diagnostics esegue una risoluzione DNS di `archive.ubuntu.com` solo
quando l'utente avvia i controlli dall'interfaccia (opzione `--no-dns` nella
riga di comando).
