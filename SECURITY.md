# Politica di sicurezza

## Versioni supportate

| Versione | Base | Supporto |
|---|---|---|
| Trota OS 1.0 "Fario" | Ubuntu 24.04 LTS | Sì: aggiornamenti Ubuntu fino ad aprile 2029; correzioni ai pacchetti Trota OS con nuove release |

## Segnalare una vulnerabilità

- **Componenti Trota OS** (applicazioni `trota-*`, script di build, configurazione
  predefinita, immagine ISO): usa la segnalazione privata di GitHub
  ("Security → Report a vulnerability") nel repository
  `federicolia-coder/TrotaOS`. Non aprire una issue pubblica.
  Indica la versione (`trota-system-info --text`), i passi per riprodurre il
  problema e l'impatto. TestardStudios conferma la ricezione entro 7 giorni e
  concorda una data di divulgazione.
- **Pacchetti Ubuntu** (kernel, GNOME, OpenSSL, …): segnala al progetto Ubuntu
  secondo https://ubuntu.com/security/disclosure-policy; la correzione arriverà
  a Trota OS con i normali aggiornamenti di `noble-security`.
- **Snap** (Firefox, App Center): segnala al rispettivo autore (Mozilla, Canonical).

Il modello di sicurezza è descritto in `docs/security.md`.
