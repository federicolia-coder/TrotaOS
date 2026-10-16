# Test

Trota OS distingue quattro esiti: **superato**, **fallito**, **non eseguito**,
**non applicabile**. Questa pagina riporta cosa viene verificato, come
eseguire i test e i risultati della versione 1.0.

## 1. Test automatici (pytest)

```sh
python3 -m pytest tests            # da Ubuntu 24.04, con le dipendenze di CONTRIBUTING.md
```

La stessa suite (esclusi i test GUI) è eseguita durante la compilazione dei
pacchetti, nel chroot pulito (`dh_auto_test`).

| File | Cosa verifica |
|---|---|
| `test_runner.py` | Esecuzione comandi: nessuna shell, timeout, comando mancante, locale fisso |
| `test_osinfo.py` | Parsing di os-release, riconoscimento della base Ubuntu, file mancanti |
| `test_release.py` | os-release di Trota OS: identificatori di compatibilità, nessun commento, parsing con il vero `aptsources` e con `/bin/sh` |
| `test_sysinfo.py` | CPU, memoria, dischi (pseudo-filesystem, mount con spazi, overlay live), rete, GPU, desktop; nessuna connessione di rete |
| `test_diagnostics.py` | Soglie disco, rete, kernel, sicurezza, servizi, log, aggiornamenti; un controllo in errore non blocca gli altri; **nessun comando privilegiato o distruttivo** |
| `test_packages.py` | Validazione nomi e query, escape delle regex, parsing di `apt-cache show`, stato installato, nessun comando privilegiato |
| `test_welcome_settings.py` | Preferenza "mostra al login", file corrotti, `--autostart` senza caricare GTK |
| `test_cli.py` | Modalità `--text`/`--json`, codici di uscita, nessun import di GTK |
| `test_ui_smoke.py` | Le quattro applicazioni si avviano sotto Xvfb, renderizzano senza errori GTK o di markup |
| `test_translations.py` | Traduzioni compilabili, complete, segnaposto coerenti, modello `.pot` aggiornato |
| `test_branding.py` | SVG aggiornati e ben formati, senza font o risorse esterne, palette, frame Plymouth, `render.sh` |
| `test_manifest.py` | Manifest validi, nessun duplicato, nessun pacchetto escluso installato, componenti essenziali presenti, telemetria esclusa |
| `test_build_scripts.py` | Sintassi e `shellcheck` degli script, configurazione, protezione `safe_rm` fuori da `build/` |

## 2. Verifica dell'immagine senza avvio

`scripts/verify/verify-iso.sh` controlla checksum SHA-256, record di avvio
BIOS e UEFI, GPT ibrida per USB, file attesi, manifest (pacchetti Trota
presenti, pacchetti esclusi assenti), `filesystem.size` e firma Microsoft UEFI
CA di shim (`sbverify`). Eseguito automaticamente dallo stadio `checksum`.

## 3. Test in macchina virtuale

`tests/vm/vmtest.py` avvia QEMU (KVM se disponibile, altrimenti emulazione
TCG) con dischi virtuali nuovi in `build/vm/`; non tocca dischi reali.

| Scenario | Comando | Cosa fa |
|---|---|---|
| Avvio ISO | `vmtest.py boot-iso --firmware bios\|uefi\|secureboot` | Avvio reale da firmware e GRUB, screenshot periodici |
| Sessione live | `vmtest.py live` | Avvio live con console seriale; login; esegue `tests/vm/checks-live.sh` |
| Installazione | `vmtest.py install --firmware secureboot` | Installazione automatica con ubiquity (preseed di test con password casuale) su disco virtuale vuoto |
| Primo avvio | `vmtest.py installed --firmware secureboot` | Avvio del disco installato, login seriale, `tests/vm/checks-installed.sh`, screenshot del desktop |

Gli script di controllo vengono passati alla VM tramite una cartella condivisa
virtio-9p; ogni controllo stampa `RESULT <nome> PASS|FAIL|SKIP <nota>`.
Il preseed di test abilita la console seriale sul solo sistema di test.

## 4. Risultati della versione 1.0

Ambiente: host Ubuntu 24.04 senza KVM, QEMU 8.2 in emulazione TCG
multi-thread, 4 vCPU, 4–6 GB RAM, disco virtio 25 GB, OVMF 2024.02
(Secure Boot con chiavi Microsoft), rete NAT. In emulazione i tempi sono
10–20 volte superiori a quelli su hardware reale.

I risultati dettagliati sono nella sezione seguente, aggiornata a ogni release.

### Difetti trovati dai test e corretti

Ogni difetto è stato riprodotto, corretto e coperto da un controllo automatico
che impedisce di ripresentarlo.

| # | Trovato da | Difetto | Correzione | Protezione |
|---|---|---|---|---|
| 1 | Build (log initramfs) | Il plugin Plymouth `two-step` (pacchetto `plymouth-theme-spinner`) mancava: lo splash Trota sarebbe stato ignorato | Dipendenza di `trota-artwork` e manifest | La build fallisce se l'initrd non contiene tema e plugin |
| 2 | Test live (`aptsources_ubuntu`) | Le righe di commento in os-release mandavano in errore `aptsources` (Software e aggiornamenti, `add-apt-repository`) | os-release senza commenti | `test_release.py` usa il vero parser di `aptsources` |
| 3 | Test live (`systemd`) | `casper-md5check.service` falliva: mancava `md5sum.txt` sul supporto | `md5sum.txt` generato nello stadio `iso` | — |
| 4 | Test live (`package_helper_backend`) | Timeout di 30 s della ricerca APT troppo stretto su macchine lente | Timeout 120 s e messaggio dedicato | `test_packages.py` |
| 5 | Test di installazione (Secure Boot) | Ubiquity andava in crash all'avvio della copia: senza slideshow `start_slideshow()` riduce i privilegi senza ripristinarli e `debconf-communicate` (Perl) rifiuta di partire (*Insecure $ENV{PATH} while running setuid*) | Nuovo pacchetto `ubiquity-slideshow-trota` | La build fallisce se lo slideshow manca; `test_manifest.py` |
| 6 | Test di installazione (Secure Boot) | *apt configuration problem*: `.disk/base_installable` faceva cercare un archivio APT inesistente sul supporto e l'installazione veniva interrotta | Il file non viene più creato | `verify-iso.sh` |
| 7 | Build | Eseguendo il solo stadio `iso` lo script terminava senza messaggi (`grep` senza risultati con `pipefail`) | `chroot_umount` tollera l'assenza di mount; trap `ERR` che mostra il comando fallito | `test_build_scripts.py` |
