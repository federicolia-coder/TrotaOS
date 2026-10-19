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
| Immagine disco | `vmtest.py image --image dist/trota-os-<edizione>-1.0-amd64.qcow2 --firmware …` | Primo avvio di un'immagine Server, Cloud o Kiosk su un disco da 25 GB (cloud: con data source NoCloud; server e kiosk: senza, con cambio password al primo accesso), `tests/vm/checks-image.sh` |

Gli script di controllo vengono passati alla VM tramite una cartella condivisa
virtio-9p; ogni controllo stampa `RESULT <nome> PASS|FAIL|SKIP <nota>`.
Il preseed di test abilita la console seriale sul solo sistema di test.

## 4. Misure su PC reali

`scripts/verify/measure-pc.py` misura un PC con Trota OS installato, con lo
stesso criterio delle macchine virtuali (memoria «usata» di `free`), e
rifiuta la misura se le condizioni non sono rispettate:

1. sistema installato sul disco interno e aggiornato, non la sessione live;
2. alimentatore collegato;
3. accensione a freddo, accesso, nessuna applicazione aperta, misura dopo
   almeno 60 secondi (`--wait` aspetta da solo);
4. tre accensioni: lo script salva ogni misura in `~/trota-misure.jsonl` e
   dopo la terza stampa la mediana.

L'avvio pubblicato è *kernel + userspace fino a `graphical.target`* di
`systemd-analyze`; il tempo del firmware dipende dal produttore del PC ed è
riportato a parte. La mediana va aggiunta a `website/benchmarks.json`: il
sito mostra la tabella dei PC reali al posto della descrizione del metodo.
Lo script legge solo `/proc`, `/sys` e l'output di `systemd-analyze`,
`lsblk`, `lspci` e `free`, e non invia nulla.

## 5. Risultati della versione 1.0

Ambiente: host Ubuntu 24.04 senza KVM, QEMU 8.2 in emulazione TCG
multi-thread, 4 vCPU, 4–6 GB RAM, disco virtio 25 GB, OVMF 2024.02
(Secure Boot con chiavi Microsoft), rete NAT. In emulazione i tempi sono
10–20 volte superiori a quelli su hardware reale.

### Ciclo A — UEFI con Secure Boot (build intermedie)

| Scenario | Esito | Dettagli |
|---|---|---|
| Verifica ISO (`verify-iso.sh`) | Superato | Checksum, El Torito BIOS+UEFI, GPT ibrida, file attesi, archivio APT, firma Microsoft UEFI CA di shim |
| Avvio ISO con Secure Boot (firmware → shim → GRUB → kernel) | Superato | Splash Plymouth Trota OS dopo ~40 s; finestra iniziale di ubiquity raggiunta |
| Sessione live (UEFI), prima build | 30/33 superati | I 3 fallimenti (`aptsources`, `casper-md5check`, timeout della ricerca pacchetti) sono stati corretti: difetti 2–4 |
| Installazione automatica (UEFI + Secure Boot), tentativi 1–3 | Falliti | Difetti 5 e 6 (slideshow, archivio APT sul supporto), corretti |
| Installazione automatica (UEFI + Secure Boot), tentativo 4 | **Superato** | Completata senza interventi in 113 minuti (emulazione) |
| Primo avvio del sistema installato (Secure Boot) | 34/39 | Avvio da voce NVRAM "Trota OS" (`\EFI\trota\shimx64.efi`), `SecureBoot enabled`; i fallimenti erano 2 errori del test (`grub.cfg` leggibile solo da root), 2 dovuti al seeding snap ancora in corso, 1 a `gnome-shell` (vedi sotto) |
| Secondo avvio | 38/40 | Seeding completato in ~7 min al primo avvio, `systemd` *running*, **Firefox 158 avviato**; `gnome-shell` della schermata di login in crash |
| Terzo avvio con CPU emulata `Nehalem` | 39/40 | Nessun crash della sessione GNOME; Firefox: errore dell'helper di snap (*Broken pipe*), da riverificare |

**Crash di gnome-shell in emulazione.** Con `-cpu max` (TCG) `gnome-shell`
terminava per segfault in codice generato dal JIT di `llvmpipe` (l'indirizzo
non appartiene ad alcuna libreria). Con un modello di CPU conservativo
(`Nehalem`, senza AVX) la sessione è stabile: si tratta di un limite
dell'emulazione, non di Trota OS. Il driver di test usa ora `Nehalem` in TCG
(modificabile con `TROTA_VM_CPU`). Su hardware reale o con KVM si usa la CPU
dell'host. **Non verificato su hardware reale.**

**Misure nel sistema installato** (VM, dopo il login): memoria usata
736–1441 MiB su 3,9 GB; spazio occupato nel filesystem radice 9,5 GB, di cui
2 GB sono il file di swap (`/swapfile`) creato dall'installer; avvio completo 1 min 47 s –
3 min 30 s in emulazione (kernel ~20 s). Sessione live: 1235 MiB di memoria
usata.

**Comportamenti di Ubuntu osservati, non modificati.**
- Con Secure Boot GRUB mostra brevemente `error: prohibited by secure boot
  policy`: è la riga `hwmatch` del `grub.cfg` standard di Ubuntu, che tenta di
  caricare un modulo non firmato; l'avvio prosegue normalmente.
- La voce del menu GRUB del sistema installato si chiama "Trota OS GNU/Linux"
  (regola di `10_linux` per le distribuzioni diverse da "Ubuntu").
- Nella VM di test HTTPS non è raggiungibile direttamente, quindi la
  registrazione del dispositivo presso lo Snap Store fallisce
  (`Initialize device`): limite dell'ambiente di test.

### Ciclo B — verifica finale (BIOS legacy e UEFI), CPU emulata `Nehalem`

ISO verificata: `trota-os-1.0-amd64.iso`, SHA-256
`e62586b3af98590e1a77036a4a0fdb3c254b90e6b0dda37b230a9383e29921ab`.

| Scenario | Esito | Dettagli |
|---|---|---|
| Avvio ISO in BIOS (SeaBIOS → GRUB `i386-pc` → kernel) | Superato | Menu GRUB con tema Trota OS e conto alla rovescia, poi splash Plymouth ([immagine](images/grub-menu-bios.png)) |
| Sessione live (UEFI) | 33/34 controlli superati, **ma** sessione grafica fallita | Superati: identità, `aptsources`, AppArmor, app Trota (riga di comando e GUI avviate), seeding snap completo (Firefox, App Center, runtime), audio, rete, nessuna porta aperta, nessuna telemetria. Fallito `systemd`: `snapd.seeded`/`snapd.hold` falliscono al primo tentativo e riescono al successivo. Lo screenshot finale mostrava la schermata GNOME *Oh no! Something has gone wrong* (sessione X11), non rilevata dal controllo automatico: vedi sotto |
| Sessione live durante l'installazione BIOS | Superato (visivo) | Desktop GNOME live con wallpaper Trota OS e installer in esecuzione ([immagine](images/installer-live-desktop.png)) |
| Installazione automatica (BIOS legacy) | **Superato** | Completata senza interventi in 146 minuti, con lo slideshow Trota OS visibile ([immagine](images/installer-slideshow.png)) |
| Primo avvio del sistema installato (BIOS) | 36/37 superati, 1 non applicabile (EFI) | GNOME su Wayland con login automatico e Trota Welcome ([immagine](images/desktop-welcome.png)), Firefox 158 avviato, `apt update`, `unattended-upgrade --dry-run`, AppArmor, nessuna porta aperta, nessuna telemetria, APT news disattivate, `Prompt=never`. Fallito `systemd` per lo stesso primo tentativo di `snapd.seeded` (poi attivo) |

Durante questo ciclo sono emersi due ulteriori difetti, corretti nella build
successiva (tabella sotto, righe 8–9).

### Ciclo C — build di rilascio

ISO: `trota-os-1.0-amd64.iso`, SHA-256
`db324d581614912d9df2628464c1b30b24f4ad9dc19bde3b5aa5d20ec7fa03c7`.
Rispetto al ciclo B cambiano solo `md5sum.txt` e la posizione degli elementi
nei wallpaper (pacchetto `trota-artwork`).

| Scenario | Esito | Dettagli |
|---|---|---|
| `verify-iso.sh` | Superato | Incluso il nuovo controllo di coerenza di `md5sum.txt` |
| Avvio ISO con Secure Boot | Superato | Menu GRUB in modalità testo (il GRUB firmato non carica font esterni), poi splash Trota OS ([immagine](images/grub-menu-secureboot.png)) |
| Sessione live (UEFI) | 31/34 controlli superati | Falliti: `systemd` e `snaps_seeded` (seeding non ancora concluso entro il test) e `gnome_session_healthy` |

**Analisi del fallimento della sessione live UEFI.** Il journal mostra
`org.gnome.Shell@x11.service: start operation timed out`: in emulazione
gnome-shell non completa l'avvio entro i 90 secondi concessi da systemd,
mentre la VM esegue contemporaneamente `casper-md5check` (oltre un minuto di
CPU) e il seeding degli snap; systemd lo termina e GNOME mostra *Oh no!
Something has gone wrong*. Nel sistema installato la shell parte in ~43 s e
nella sessione live del test BIOS il desktop era funzionante. Si tratta con
ogni probabilità di un effetto della lentezza dell'emulazione (10–20 volte
più lenta dell'hardware reale), **da confermare** con KVM o su hardware reale
prima della pubblicazione.

### Ciclo D — identità Trota OS, desktop alleggerito, edizioni

**Desktop** (ISO senza snap, `ID=trota`, desktop alleggerito): sessione live
UEFI **51/51** controlli superati, tra cui avvio di gnome-shell (fallito nel
ciclo C), identità (`lsb_release`, python-apt), origini degli aggiornamenti
automatici, nomi delle sessioni GDM, servizi tolti dall'accesso, Firefox di
Mozilla, Flathub. Memoria usata dopo l'accesso: 923 MB (ciclo C: circa
1,2 GB).

Ricostruita la ISO con le correzioni emerse dagli screenshot (icona del
dock, testo di Welcome, icona e presentazione dell'installer; SHA-256
`92eefcfbc6e046d50c26c215d209964b2d4490a5fbe5292d3f731be4a4380c1e`):

| Scenario | Esito | Dettagli |
|---|---|---|
| Sessione live (UEFI) | **54/54** | Icona Trota nel dock e sull'installer, 935 MB di RAM dopo l'accesso |
| Installazione (UEFI + Secure Boot) | Superata | 136 minuti in emulazione |
| Primo avvio (UEFI + Secure Boot) | **57/58** | SecureBoot attivo, sessioni GDM "Trota OS", origini di sicurezza degli aggiornamenti automatici, Firefox di Mozilla, Flathub; 860 MB di RAM dopo l'accesso, avvio in 2 min 25 s (emulato). Unico non superato `ppa_add`: la rete delle VM di test intercetta l'HTTPS verso Launchpad (*self-signed certificate in certificate chain*, anche con `curl`); `add-apt-repository` arriva a contattare Launchpad e il PPA usa il codename `noble`. Il controllo ora risulta *saltato* quando Launchpad non è raggiungibile; da riverificare su una rete normale |

**Immagini disco** (primo avvio, 2 GB di RAM, disco da 25 GB):

| Edizione | Firmware | Esito | Avvio fino alla console* | RAM usata | Pacchetti |
|---|---|---|---|---|---|
| Server / Edge | UEFI, e UEFI con Secure Boot | 37/37 (1 saltato) | circa 4 min | 271 MB | 380 |
| Cloud (NoCloud) | BIOS | tutti i controlli salvo `podman_run` (difetto del test, corretto e riverificato sull'immagine Server) | circa 5 min | 294 MB | 361 |
| Kiosk | UEFI | tutti i controlli salvo `podman_run` (difetto del test, corretto e riverificato sull'immagine Server) | circa 4 min | 309 MB | 556 |

\* In emulazione TCG; il primo avvio comprende cloud-init (chiavi SSH,
allargamento del disco).

Verificati tra l'altro: avvio con shim e GRUB firmati, partizione radice
allargata al disco intero, chiavi SSH generate al primo avvio, SSH solo con
chiave, firewall attivo con la sola porta 22, parametri sysctl di hardening,
AppArmor, origini degli aggiornamenti automatici, container Podman rootless;
per il Kiosk: servizio attivo, cage e Firefox in esecuzione come utente
`kiosk`, policy di Firefox, riavvio automatico dopo l'uccisione del browser.
Il download di un'immagine da Docker Hub non è verificabile dalla rete delle
VM di test (controllo `podman_pull` saltato).

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
| 6 | Test di installazione (Secure Boot) | *apt configuration problem*: il wrapper `apt-setup` di ubiquity forza `OVERRIDE_BASE_INSTALLABLE=1` ed esegue sempre `apt-cdrom add` sul supporto; senza indici di pacchetti l'installazione veniva interrotta. Un primo tentativo (non creare `.disk/base_installable`) si è rivelato insufficiente al test successivo | La ISO contiene un piccolo archivio APT (`dists/`, `pool/` con i pacchetti Trota OS), verificato con il vero `apt-cdrom` | `verify-iso.sh` |
| 7 | Build | Eseguendo il solo stadio `iso` lo script terminava senza messaggi (`grep` senza risultati con `pipefail`) | `chroot_umount` tollera l'assenza di mount; trap `ERR` che mostra il comando fallito | `test_build_scripts.py` |
| 8 | Test live (journal) | `md5sum.txt` conteneva il checksum di `eltorito.img` prima che `xorriso` vi scrivesse la boot-info-table: `casper-md5check` segnalava un falso errore | `eltorito.img` escluso da `md5sum.txt` | `verify-iso.sh` controlla la coerenza di `md5sum.txt` |
| 9 | Screenshot del desktop live | Su schermi 16:10 e 4:3 il marchio del wallpaper veniva tagliato | Posizione del marchio e della trota rivista | Anteprime 4:3, 16:10, 16:9 |
| 10 | Test di installazione e sessione live | Con `-cpu max` in emulazione TCG gnome-shell andava in segfault nel codice JIT di llvmpipe e lo slideshow non veniva disegnato | Non è un difetto di Trota OS: il driver di test usa `Nehalem` | `TROTA_VM_CPU` |
| 11 | Build (controllo di identità) | Con `ID=trota` python-apt non trovava il calendario delle versioni (`trota.csv`) e *Software e aggiornamenti* non avrebbe funzionato | Collegamenti `Trota.info`, `Trota.mirrors`, `trota.csv` in `trota-release` | La build fallisce se python-apt non gestisce la distribuzione |
| 12 | Screenshot del desktop live | Logo Ubuntu sul pulsante "Mostra applicazioni" del dock; "Based on Ubuntu" nell'app Welcome; icona dell'installer non attendibile ("ubiquity.desktop") nella sessione live | Icona Trota al posto di quella di Yaru (filtro dpkg), testi rivisti, icona dell'installer segnata come attendibile | Controlli VM `dock_icon_trota`, `installer_icon_trusted` |
| 13 | Test delle immagini | Il primo avvio si fermava nell'initramfs: senza udev `grub-mkconfig` scriveva `root=/dev/loop0p3` | `root=UUID=…` nel `grub.cfg` dell'immagine | La build fallisce se `grub.cfg` cita il dispositivo loop |
| 14 | Test delle immagini | Senza data source cloud-init veniva disattivato: niente DHCP, chiavi SSH né allargamento del disco | Policy di ds-identify `notfound=enabled` (data source *None*) | Controlli VM `network`, `ssh_host_keys`, `root_grown` |
| 15 | Build delle immagini | Il kernel dell'host di build non monta FAT; mancavano `initramfs-tools` e gli strumenti di partizionamento con `--no-install-recommends` | ESP scritta con mtools; pacchetti aggiunti al manifest | La build verifica `EFI/BOOT/BOOTX64.EFI` |
