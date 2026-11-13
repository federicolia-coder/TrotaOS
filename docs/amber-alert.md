# Allerte AMBER (Stati Uniti)

Le allerte AMBER segnalano negli Stati Uniti il rapimento di un minore. Trota OS
può mostrarle come notifiche, ma **non sono attive di serie**: le attiva chi le
vuole, scaricando uno script dal sito.

## Attivarle

1. Scarica `attiva-allerte-amber.sh` dalla sezione *Allerte AMBER* del sito
   (controlla, se vuoi, il file `.sha256` accanto: `sha256sum -c attiva-allerte-amber.sh.sha256`).
2. Nella cartella dove l'hai scaricato, come utente normale (senza `sudo`):

   ```sh
   bash attiva-allerte-amber.sh --prova
   ```

   `--prova` mostra subito una notifica di prova («no child is missing»).
   Senza `--prova` le allerte si attivano senza notifica di prova.

Lo script installa tutto nella cartella personale: il comando
`~/.local/bin/trota-amber-alert`, il suo modulo in
`~/.local/share/trota-amber-alert/`, il timer utente
`~/.config/systemd/user/trota-amber-alert.timer` e la configurazione
`~/.config/trota-amber-alert.conf`. Serve Trota OS 1.0 o successiva.

## Come funziona

- Ogni 5 minuti, solo mentre sei collegato, il timer controlla il feed pubblico
  **IPAWS** della FEMA (`apps.fema.gov`), il sistema di allerta ufficiale degli
  Stati Uniti, e cerca le allerte con codice `CAE` (Child Abduction Emergency).
- Il paese e gli stati si ricavano **solo dal fuso orario** del sistema: se
  *Impostazioni → Sistema → Data e ora → Fuso orario automatico* è attivo, GNOME
  lo cambia quando arrivi negli Stati Uniti. Nessuna posizione viene cercata o
  inviata.
- **Fuori dagli Stati Uniti non viene scaricato nulla.**
- Ogni allerta compare una volta sola, come notifica urgente che resta finché
  non la chiudi. Le allerte già scadute non vengono mostrate.

## Configurazione

In `~/.config/trota-amber-alert.conf` (oppure, per tutti gli utenti, in
`/etc/trota-amber-alert.conf`):

| Chiave | Valori |
|---|---|
| `AMBER_ALERTS` | `auto` (predefinito: solo negli Stati Uniti) oppure `off` |
| `AMBER_STATES` | stati da seguire al posto di quelli del fuso orario, per esempio `ID,OR` |

`trota-amber-alert --status` mostra gli stati seguiti; `trota-amber-alert --test`
mostra una notifica di prova.

## Disattivarle

```sh
bash attiva-allerte-amber.sh --disattiva
```

Rimuove comando, modulo e timer; resta solo il file di configurazione, che
puoi cancellare.

## Per chi sviluppa

Lo script è generato da `scripts/build/make-amber-installer.py` a partire da
`applications/trota-common/trota_common/amber.py` e `packaging/files/amber/`,
e pubblicato dal sito (`website/root/`). Dopo una modifica a quei file va
rigenerato: `tests/test_amber.py` controlla che sia aggiornato.
