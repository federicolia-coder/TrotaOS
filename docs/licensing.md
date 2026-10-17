# Licenze, componenti e marchi

> Questo documento descrive le scelte del progetto; non è una consulenza
> legale. Prima di una distribuzione pubblica o commerciale, TestardStudios
> dovrebbe farlo verificare da un professionista.

## Componenti e licenze

| Componente | Origine | Licenza | Note |
|---|---|---|---|
| Applicazioni Trota OS (`applications/`), script (`scripts/`, `branding/*.py`, `branding/render.sh`), packaging (`packaging/`), test | TestardStudios | **GPL-3.0-or-later** ([LICENSE](https://github.com/federicolia-coder/TrotaOS/blob/main/LICENSE)) | Codice originale |
| Asset grafici (`branding/`: logo, sfondi, icone, temi) | TestardStudios | **CC BY-SA 4.0** ([branding/LICENSE.md](https://github.com/federicolia-coder/TrotaOS/blob/main/branding/LICENSE.md)) | Nome e logo sono anche segni distintivi: vedi sotto |
| Documentazione (`docs/`) | TestardStudios | **CC BY-SA 4.0** | |
| Traduzioni (`po/`) | TestardStudios | GPL-3.0-or-later | Come il codice |
| Sistema base Ubuntu 24.04 (kernel, GNOME, systemd, APT…) | Canonical e progetti a monte | Licenze dei singoli pacchetti (GPL-2.0, GPL-3.0, LGPL, MIT, BSD, MPL, Apache-2.0…) | Testo in `/usr/share/doc/<pacchetto>/copyright` di ogni pacchetto |
| Firmware (`linux-firmware`), microcode, driver `restricted` | Produttori hardware | Licenze proprietarie ridistribuibili | Inclusi come in Ubuntu |
| Pacchetti `multiverse` eventualmente installati | Vari | Non liberi | Nessuno è preinstallato da Trota OS |
| Firefox (`firefox`, `firefox-l10n-it`) | Mozilla | MPL-2.0; marchio Firefox di Mozilla Foundation | Pacchetti `.deb` ufficiali di packages.mozilla.org, scaricati al momento della build senza modifiche |
| Remote Flathub (`flathub.flatpakrepo`) | Flathub | File di configurazione pubblico | Nessuna applicazione Flatpak è preinstallata |
| Font (Inter, DejaVu, Noto, Liberation, Ubuntu) | Vari | SIL OFL 1.1, licenza Bitstream/DejaVu, Ubuntu Font Licence | Dall'archivio Ubuntu |
| Tema Yaru (GTK, icone, suoni) | Ubuntu community | GPL-3.0 / CC BY-SA 4.0 / LGPL | Usato senza modifiche |

L'elenco completo e preciso dei pacchetti di ogni ISO è nel *manifest*
pubblicato accanto all'immagine (`dist/trota-os-<versione>-amd64.manifest`).

## Obblighi di distribuzione

- **Codice sorgente**: per i pacchetti con licenza copyleft (GPL, LGPL…)
  chi distribuisce i binari deve rendere disponibile il sorgente
  corrispondente. Trota OS usa esclusivamente pacchetti binari non modificati
  dell'archivio Ubuntu, i cui sorgenti sono pubblicati da Ubuntu
  (`apt source <pacchetto>`, archive.ubuntu.com). Per prudenza, ad ogni
  release TestardStudios deve conservare l'elenco esatto delle versioni (il
  manifest) e, se distribuisce le ISO in modo indipendente dall'archivio
  Ubuntu per un periodo prolungato, predisporre un archivio dei sorgenti
  corrispondenti (ad es. con `apt-get source` sulle versioni del manifest),
  come previsto dalla GPL-2.0 §3 e dalla GPL-3.0 §6.
- Il sorgente dei pacchetti Trota OS è questo repository.
- Gli avvisi di copyright dei pacchetti restano installati in
  `/usr/share/doc/*/copyright` e non vengono rimossi dall'immagine.

## Marchi

- **Trota OS** è il nome del sistema operativo; **TestardStudios** è lo
  sviluppatore e l'editore. TestardStudios non è il nome del sistema.
- Trota OS **non è** un prodotto di Canonical Ltd. né del progetto Ubuntu e
  non è approvato da essi. "Ubuntu" e i loghi correlati sono marchi di
  Canonical Ltd.; Trota OS li cita solo per indicare la base tecnica
  ("basato su Ubuntu"), non li usa come marchio proprio e non usa l'artwork di
  Ubuntu come identità. L'identità tecnica `ID=ubuntu` in os-release è un
  identificatore di compatibilità, motivato in [architecture.md](architecture.md)
  (ADR-005), e non compare all'utente come nome del sistema.
- Alcuni pacchetti Ubuntu contengono elementi grafici o testi con il marchio
  Ubuntu (ad es. `ubuntu-wallpapers`, richiesto da `gnome-shell`; la guida
  `ubuntu-docs`; l'artwork di `ubiquity`). Sono ridistribuiti invariati, come
  parte del software Ubuntu, e non sono usati come identità di Trota OS.
  Prima della pubblicazione è opportuno leggere la
  [politica sui marchi di Canonical](https://ubuntu.com/legal/intellectual-property-policy)
  per le distribuzioni derivate e, se necessario, chiedere chiarimenti.
- Firefox è un marchio di Mozilla Foundation; il pacchetto `.deb` ufficiale di
  Mozilla è distribuito senza modifiche, come previsto dalla
  [politica sui marchi di Mozilla](https://www.mozilla.org/foundation/trademarks/policy/)
  per le build ufficiali non modificate.

## Verifiche da completare prima della pubblicazione

| Verifica | Stato |
|---|---|
| Disponibilità del nome "Trota OS" (registri marchi EUIPO, UIBM, WIPO) | **Da fare** |
| Somiglianze con marchi esistenti nel settore software | **Da fare** |
| Disponibilità di domini (es. trota-os.org / .it) e account social | **Da fare** |
| Revisione della politica Canonical sui derivati | **Da fare** |
| Indirizzo e-mail reale del maintainer nei pacchetti (ora segnaposto `maintainers@testardstudios.invalid`) | **Da fare** |

## Politica d'uso del nome e del logo

- Chiunque può ridistribuire Trota OS **non modificato** con nome e logo.
- Le versioni modificate (immagini o pacchetti alterati) devono usare un nome
  e un logo diversi, pur potendo dichiarare di essere "basate su Trota OS".
- Il logo può essere usato per articoli, recensioni e materiali che parlano
  di Trota OS, senza suggerire un'approvazione di TestardStudios.
