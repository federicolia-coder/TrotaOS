# Sicurezza

La sicurezza ha la precedenza su ogni personalizzazione. Trota OS mantiene
intatti i meccanismi di sicurezza di Ubuntu 24.04 LTS e non ne aggiunge di
propri che possano indebolirli.

## Cosa è garantito dalla configurazione

| Area | Stato in Trota OS | Come è verificato |
|---|---|---|
| Aggiornamenti di sicurezza | Archivio `noble-security` attivo; `unattended-upgrades` installa automaticamente gli aggiornamenti di sicurezza (come Ubuntu) | Test VM `unattended_upgrades`, Trota Diagnostics |
| AppArmor | Attivo con i profili di Ubuntu; nessun profilo disattivato | Test VM `apparmor` |
| Secure Boot | Supportato con shim e GRUB firmati da Canonical; non viene disattivato | Test VM in modalità `secureboot` |
| Privilegi | Il primo utente è amministratore tramite `sudo` (gruppo `sudo`), come in Ubuntu; le applicazioni Trota non richiedono mai privilegi | Test automatici (`test_checks_never_run_privileged_or_destructive_commands`, `test_never_runs_privileged_commands`) |
| Servizi di rete | Nessun server SSH, nessun desktop remoto; nessuna porta TCP in ascolto su interfacce esterne | Test VM `no_open_tcp_ports` |
| Firewall | `ufw` installato (disattivato come in Ubuntu, perché nessun servizio è in ascolto); attivabile con `sudo ufw enable` | Trota Diagnostics |
| Telemetria | Assente: pacchetti di telemetria esclusi dalla build, che fallisce se vengono installati | Test VM `no_telemetry`, `test_manifest.py` |
| Password | Nessuna password nel codice o nell'immagine; l'utente della sessione live non ha password (standard di casper) e non esiste nel sistema installato | Revisione del codice, test VM |
| Accesso remoto nascosto | Nessuno | Elenco servizi, porte in ascolto |

## Mitigazioni nel processo di build

- Tutti i pacchetti provengono dall'archivio Ubuntu, verificato con la chiave
  `ubuntu-archive-keyring`; i pacchetti Trota OS sono compilati da sorgente in
  un chroot pulito.
- Lo script di build rifiuta di cancellare o montare percorsi esterni a
  `build/` (`assert_in_build`, `safe_rm`), non avvia servizi nel chroot
  (`policy-rc.d`) e rimuove dall'immagine machine-id, chiavi SSH dell'host,
  log e cache.
- DNS, proxy e certificati dell'host di build sono resi disponibili al chroot
  solo tramite `/run` (tmpfs) e non finiscono nell'immagine.
- Ogni ISO è accompagnata dal checksum SHA-256 (`checksums/`).

## Regole per le applicazioni Trota OS

1. I comandi esterni sono eseguiti solo come lista di argomenti, mai tramite
   shell, con timeout e locale fisso.
2. L'input utente (ricerca pacchetti) è validato e passato come espressione
   regolare *escaped*; i nomi dei pacchetti seguono la Debian Policy.
3. Nessuna operazione distruttiva: Diagnostics legge soltanto; Package Helper
   mostra il comando `sudo apt install …` ma non lo esegue.
4. Nessun dato inviato in rete. L'unica connessione possibile è la risoluzione
   DNS di `archive.ubuntu.com` avviata esplicitamente dall'utente in Trota
   Diagnostics (disattivabile con `--no-dns`).

## Segnalare una vulnerabilità

Vedi [SECURITY.md](https://github.com/federicolia-coder/TrotaOS/blob/main/SECURITY.md):
le vulnerabilità di componenti Ubuntu vanno segnalate a Ubuntu; quelle dei
componenti Trota OS a TestardStudios tramite una segnalazione privata
("Report a vulnerability" su GitHub), non tramite una issue pubblica.

## Limiti noti

- Il repository APT dei pacchetti Trota OS non è ancora pubblicato: le
  correzioni ai pacchetti `trota-*` arrivano con una nuova ISO (gli
  aggiornamenti Ubuntu invece arrivano normalmente).
- Le chiavi di firma di un futuro repository Trota OS dovranno essere generate
  e custodite offline; nessuna chiave privata è nel repository.
- La sessione live, come in Ubuntu, concede `sudo` senza password all'utente
  live: non usarla su reti non fidate per attività sensibili.
