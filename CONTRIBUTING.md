# Contribuire a Trota OS

Grazie per l'interesse! Trota OS è sviluppato da TestardStudios con un budget
pari a zero: ogni contributo deve essere sostenibile da un piccolo team.

## Principi

1. **Sicurezza e stabilità prima delle personalizzazioni.** Non disattivare
   AppArmor, aggiornamenti di sicurezza, Secure Boot o altri meccanismi di Ubuntu.
2. **Compatibilità con Ubuntu.** Preferire pacchetti ufficiali; APT resta il
   gestore dei pacchetti; nessun componente fondamentale sostituito senza una
   ragione tecnica documentata in `docs/architecture.md`.
3. **Nessuna telemetria, nessun account obbligatorio, nessun servizio di rete
   superfluo.**
4. **Niente funzionalità dichiarate senza verifica**: ogni modifica deve
   essere accompagnata da test o da un risultato di test documentato.

## Ambiente di sviluppo

Su Ubuntu 24.04:

```sh
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-pytest xvfb \
    librsvg2-bin gettext shellcheck
export PYTHONPATH=$(ls -d applications/*/ | tr '\n' ':')
python3 -m trota_welcome            # avvia un'app dal sorgente
python3 -m trota_system_info --text
python3 -m pytest tests             # tutta la suite (le prove GUI usano Xvfb)
```

## Regole per il codice

- Python 3.12, solo libreria standard nel back-end; PyGObject/GTK 4/libadwaita
  solo nei moduli `app.py` e `trota_common/ui.py`, `desktop.py`.
- Comandi esterni solo tramite `trota_common.runner.run` (lista di argomenti,
  timeout, nessuna shell).
- Testi visibili all'utente in inglese, marcati con `_()`; dopo averli
  modificati esegui `scripts/build/update-translations.sh` e aggiorna
  `po/it.po` (i test verificano che la traduzione sia completa).
- Gli asset grafici si modificano solo tramite `branding/generate.py`.
- Gli script shell devono superare `shellcheck`.

## Pacchetti e ISO

Vedi `docs/building.md`. Prima di proporre modifiche a manifest, pacchetti o
script di build, esegui almeno `scripts/build/build-packages.sh` e, per le
modifiche che toccano l'immagine, il test in VM (`docs/testing.md`).

## Commit e pull request

- Un argomento per commit, messaggio in inglese all'imperativo.
- Descrivi nella pull request cosa è stato verificato e come.
- I contributi sono accettati con la licenza del progetto (GPL-3.0-or-later per
  il codice, CC BY-SA 4.0 per grafica e documentazione).
