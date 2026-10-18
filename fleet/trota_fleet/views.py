"""HTML of the panel pages. Every value from the database or from a device
goes through esc(): device reports are untrusted input."""

from __future__ import annotations

import json
import time
from html import escape
from urllib.parse import urlencode

from trota_fleet.legal import company

COMPANY = company()

SYMBOL = (
    '<svg viewBox="0 0 256 256" aria-hidden="true"><g fill="currentColor">'
    '<path d="M52 128 L16 98 L28 128 L16 158 Z"/><path d="M60 128 L102 94 L198 94 L238 128 L198 162 L102 162 Z"/>'
    '<path d="M124 94 L142 76 L174 76 L164 94 Z"/></g>'
    '<path d="M88 123 L214 123 L219 128 L214 133 L88 133 L83 128 Z" fill="#FF6A2A"/></svg>'
)
EDITIONS = {"server": "Server", "cloud": "Cloud", "kiosk": "Kiosk", "desktop": "Desktop"}


def esc(value) -> str:
    return escape("" if value is None else str(value), quote=True)


def size(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return ""


def ago(ts) -> str:
    if not ts:
        return "mai"
    s = int(time.time() - ts)
    if s < 60:
        return "adesso"
    if s < 3600:
        return f"{s // 60} min fa"
    if s < 86400:
        return f"{s // 3600} h fa"
    return f"{s // 86400} g fa"


def when(ts) -> str:
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(ts)) if ts else ""


def duration(seconds) -> str:
    s = int(seconds or 0)
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    return f"{d} g {h} h" if d else f"{h} h {m} min"


def status_of(device) -> dict:
    try:
        data = json.loads(device["status"] or "{}")
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def state_label(online: bool) -> str:
    return (f'<span class="state {"on" if online else "off"}">'
            f'{"In linea" if online else "Non in linea"}</span>')


def page(title: str, body: str, session=None, active: str = "", msg: str = "") -> str:
    nav = ""
    if session:
        links = [("/", "Dispositivi", "devices"), ("/enroll", "Aggiungi dispositivi", "enroll")]
        nav = '<nav aria-label="Sezioni">' + "".join(
            f'<a href="{href}"{" aria-current=page" if key == active else ""}>{label}</a>'
            for href, label, key in links) + "</nav>"
        nav += (f'<form method="post" action="/logout" class="who"><span>{esc(session["name"])}</span>'
                f'<input type="hidden" name="csrf" value="{esc(session["csrf"])}">'
                '<button class="link">Esci</button></form>')
    note = f'<p class="msg" role="status">{esc(msg)}</p>' if msg else ""
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{esc(title)} · Trota Fleet</title>
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/fleet.css">
<script src="/static/fleet.js" defer></script>
</head>
<body>
<header class="top"><div class="wrap">
<a class="brand" href="/">{SYMBOL}<span>Trota Fleet</span></a>
{nav}
</div></header>
<main class="wrap">
{note}
{body}
</main>
<footer class="foot"><div class="wrap">
<p>Trota Fleet · {esc(COMPANY["ident"])}</p>
<p><a href="/privacy">Privacy</a> · <a href="/cookie">Cookie</a> · <a href="{esc(COMPANY["website"])}/note-legali.html">Note legali</a></p>
</div></footer>
</body>
</html>
"""


def csrf(session) -> str:
    return f'<input type="hidden" name="csrf" value="{esc(session["csrf"])}">'


def error_page(code: int, message: str) -> str:
    return page(f"Errore {code}", f'<h1>Errore {code}</h1><p class="lead">{esc(message)}</p>'
                                  '<p><a href="/">Torna ai dispositivi</a></p>')


def login_page(error: str, next_url: str) -> str:
    err = f'<p class="err" role="alert">{esc(error)}</p>' if error else ""
    body = f"""<section class="login">
<h1>Accedi</h1>
{err}
<form method="post" action="/login">
<input type="hidden" name="next" value="{esc(next_url)}">
<label>Nome <input name="name" autocomplete="username" required autofocus></label>
<label>Password <input name="password" type="password" autocomplete="current-password" required></label>
<button class="btn">Accedi</button>
</form>
</section>"""
    return page("Accedi", body)


def command_fields(commands: dict, url_label: str = "Nuova pagina") -> str:
    options = "".join(f'<option value="{k}">{esc(label)}</option>' for k, label in commands.items())
    return (f'<label>Comando <select name="type" data-command>{options}</select></label>'
            f'<label data-url>{esc(url_label)} <input name="url" type="url" placeholder="https://"></label>')


def devices_page(session, rows, customers, customer, query, online, commands, msg) -> str:
    n_on = sum(1 for d in rows if online(d))
    n_upd = sum(1 for d in rows if (status_of(d).get("updates") or 0) > 0)
    filt = ['<form class="filters" method="get" action="/">',
            '<label>Cliente <select name="cliente"><option value="">Tutti</option>']
    for c in customers:
        sel = " selected" if customer == c else ""
        filt.append(f'<option value="{esc(c or "-")}"{sel}>{esc(c or "Senza cliente")}</option>')
    filt.append(f'</select></label><label>Cerca <input name="q" value="{esc(query)}" '
                'placeholder="nome, indirizzo, note"></label><button class="btn ghost">Filtra</button></form>')
    if not rows:
        empty = ("Nessun dispositivo corrisponde al filtro." if (customer is not None or query) else
                 'Nessun dispositivo ancora. Crea un codice in <a href="/enroll">Aggiungi dispositivi</a> '
                 "e usalo sul dispositivo.")
        return page("Dispositivi", f'<h1>Dispositivi</h1>{"".join(filt)}<p class="empty">{empty}</p>',
                    session, "devices", msg)

    trs = []
    for d in rows:
        st = status_of(d)
        upd = st.get("updates")
        upd_txt = "—" if upd is None else ("nessuno" if upd == 0 else f"{int(upd)}")
        if st.get("reboot_required"):
            upd_txt += " · riavvio richiesto"
        addr = ", ".join(st.get("addresses") or []) or d["last_ip"]
        trs.append(f"""<tr>
<td><input type="checkbox" name="device" value="{esc(d['id'])}" form="bulk" aria-label="Seleziona {esc(d['name'])}"></td>
<td>{state_label(online(d))}</td>
<td><a href="/devices/{esc(d['id'])}">{esc(d['name'] or d['hostname'] or d['id'])}</a></td>
<td>{esc(d['customer'] or '—')}</td>
<td>{esc(EDITIONS.get(st.get('edition'), st.get('edition') or '—'))}</td>
<td class="addr">{esc(addr)}</td>
<td>{esc(upd_txt)}</td>
<td title="{esc(when(d['last_seen']))}">{esc(ago(d['last_seen']))}</td>
</tr>""")
    params = {"cliente": "-" if customer == "" else customer, "q": query}
    back = "/?" + urlencode({k: x for k, x in params.items() if x})
    body = f"""<h1>Dispositivi</h1>
<p class="lead">{len(rows)} dispositivi: {n_on} in linea, {len(rows) - n_on} non in linea, {n_upd} con aggiornamenti da installare.</p>
{''.join(filt)}
<div class="table"><table class="list">
<thead><tr><th><input type="checkbox" data-all aria-label="Seleziona tutti"></th><th>Stato</th><th>Nome</th><th>Cliente</th>
<th>Edizione</th><th>Indirizzo</th><th>Aggiornamenti</th><th>Ultimo contatto</th></tr></thead>
<tbody>{''.join(trs)}</tbody>
</table></div>
<form id="bulk" class="bulk" method="post" action="/bulk">
{csrf(session)}<input type="hidden" name="back" value="{esc(back)}">
<p class="label">Ai dispositivi selezionati</p>
{command_fields(commands)}
<button class="btn" data-confirm="Inviare il comando ai dispositivi selezionati?">Invia</button>
</form>"""
    return page("Dispositivi", body, session, "devices", msg)


def device_page(session, d, cmds, online, commands, msg) -> str:
    st = status_of(d)
    mem, disk_ = st.get("memory") or {}, st.get("disk") or {}
    kiosk = st.get("kiosk")
    facts = [
        ("Stato", state_label(online) + f' <span class="muted">· ultimo contatto {esc(ago(d["last_seen"]))}'
                                        f'{" · " + esc(when(d["last_seen"])) if d["last_seen"] else ""}</span>'),
        ("Sistema", esc(st.get("os", "—")) + (f' · {esc(EDITIONS.get(st.get("edition"), st.get("edition")))}'
                                             if st.get("edition") else "")),
        ("Nome host", esc(d["hostname"] or "—")),
        ("Kernel", esc(st.get("kernel", "—"))),
        ("Acceso da", esc(duration(st.get("uptime"))) if st.get("uptime") else "—"),
        ("Carico", esc(f'{st.get("load", 0):.2f}'.replace(".", ",")) if "load" in st else "—"),
        ("Memoria", f'{esc(size(mem.get("total", 0) - mem.get("available", 0)))} usati su {esc(size(mem.get("total")))}'
         if mem.get("total") else "—"),
        ("Disco", f'{esc(size(disk_.get("used")))} usati su {esc(size(disk_.get("total")))}' if disk_.get("total") else "—"),
        ("Indirizzi", esc(", ".join(st.get("addresses") or []) or "—") +
         f' <span class="muted">· visto da {esc(d["last_ip"])}</span>'),
        ("Aggiornamenti", "—" if st.get("updates") is None else
         ("nessuno" if st["updates"] == 0 else f'{int(st["updates"])} da installare') +
         (" · riavvio richiesto" if st.get("reboot_required") else "")),
        ("Agente", esc(st.get("agent", "—"))),
        ("Registrato il", esc(when(d["enrolled"]))),
    ]
    if kiosk:
        facts.insert(2, ("Pagina del kiosk", f'<span class="addr">{esc(kiosk.get("url"))}</span>'
                         + ("" if kiosk.get("active") else ' <strong class="warn">kiosk fermo</strong>')))
    dl = "".join(f"<div><dt>{k}</dt><dd>{val}</dd></div>" for k, val in facts)

    actions = []
    if kiosk:
        actions.append(f"""<form method="post" action="/devices/{esc(d['id'])}/command" class="action">
{csrf(session)}<input type="hidden" name="type" value="kiosk-url">
<label>Pagina da mostrare <input name="url" type="url" required value="{esc(kiosk.get('url', '') if str(kiosk.get('url', '')).startswith('http') else '')}" placeholder="https://"></label>
<button class="btn">Cambia pagina</button></form>
<form method="post" action="/devices/{esc(d['id'])}/command" class="action">
{csrf(session)}<input type="hidden" name="type" value="kiosk-restart"><button class="btn ghost">Riavvia il kiosk</button></form>""")
    actions.append(f"""<form method="post" action="/devices/{esc(d['id'])}/command" class="action">
{csrf(session)}<input type="hidden" name="type" value="update">
<button class="btn ghost" data-confirm="Installare tutti gli aggiornamenti disponibili?">Installa gli aggiornamenti</button></form>
<form method="post" action="/devices/{esc(d['id'])}/command" class="action">
{csrf(session)}<input type="hidden" name="type" value="reboot">
<button class="btn ghost" data-confirm="Riavviare il dispositivo?">Riavvia il dispositivo</button></form>""")

    hist = []
    for c in cmds:
        if c["done"]:
            state = '<span class="state on">Riuscito</span>' if c["ok"] else '<span class="state bad">Non riuscito</span>'
        elif c["sent"]:
            state = '<span class="state wait">Inviato</span>'
        else:
            state = (f'<span class="state wait">In coda</span> <form method="post" action="/devices/{esc(d["id"])}/cancel" '
                     f'class="inline">{csrf(session)}<input type="hidden" name="command" value="{c["id"]}">'
                     '<button class="link">Annulla</button></form>')
        try:
            args = json.loads(c["args"] or "{}")
        except ValueError:
            args = {}
        label = esc(commands.get(c["type"], c["type"])) + (f' <span class="addr">{esc(args["url"])}</span>'
                                                           if args.get("url") else "")
        out = (f'<details><summary>Risultato</summary><pre>{esc(c["output"])}</pre></details>'
               if c["output"] else "")
        hist.append(f'<tr><td title="{esc(when(c["created"]))}">{esc(when(c["created"]))}</td><td>{label}{out}</td>'
                    f'<td>{esc(c["created_by"])}</td><td>{state}</td></tr>')
    history = (f'<div class="table"><table><thead><tr><th>Quando</th><th>Comando</th><th>Da</th><th>Esito</th></tr></thead>'
               f'<tbody>{"".join(hist)}</tbody></table></div>' if hist else '<p class="empty">Nessun comando inviato.</p>')
    waiting = "" if online else ('<p class="muted">Il dispositivo non è in linea: i comandi partono '
                                 "al prossimo collegamento.</p>")

    body = f"""<p class="crumbs"><a href="/">Dispositivi</a></p>
<h1>{esc(d['name'] or d['hostname'] or d['id'])}</h1>
<p class="lead">{esc(d['customer'] or 'Senza cliente')}</p>
<div class="cols">
<section><h2>Stato</h2><dl class="facts">{dl}</dl></section>
<section><h2>Azioni</h2>{waiting}{''.join(actions)}</section>
</div>
<section><h2>Comandi</h2>{history}</section>
<section class="cols">
<form method="post" action="/devices/{esc(d['id'])}" class="edit">
<h2>Dati</h2>{csrf(session)}
<label>Nome <input name="name" value="{esc(d['name'])}" maxlength="100"></label>
<label>Cliente <input name="customer" value="{esc(d['customer'])}" maxlength="100"></label>
<label>Note <textarea name="notes" rows="4" maxlength="2000">{esc(d['notes'])}</textarea></label>
<button class="btn ghost">Salva</button>
</form>
<form method="post" action="/devices/{esc(d['id'])}/delete" class="edit">
<h2>Rimuovi</h2>{csrf(session)}
<p class="muted">Il dispositivo esce dal pannello e il suo agente smette di collegarsi. Per riportarlo qui
serve un nuovo codice di registrazione.</p>
<button class="btn danger" data-confirm="Rimuovere il dispositivo dal pannello?">Rimuovi dal pannello</button>
</form>
</section>"""
    return page(d["name"] or d["id"], body, session, "devices", msg)


def enroll_page(session, codes, base, created, customer, customers) -> str:
    shown = ""
    if created:
        shown = f"""<section class="created" aria-live="polite">
<h2>Codice creato</h2>
<p>Copialo adesso: il pannello non lo mostra più.</p>
<pre class="code" data-copy>{esc(created)}</pre>
<h3>Su un dispositivo già acceso</h3>
<pre class="term">sudo trota-fleet-agent enroll {esc(base)} {esc(created)}
sudo systemctl enable --now trota-fleet-agent</pre>
<h3>Con cloud-init, per molti dispositivi</h3>
<pre class="term">#cloud-config
write_files:
  - path: /etc/trota-fleet.conf
    content: |
      TROTA_FLEET_URL={esc(base)}
      TROTA_FLEET_TOKEN={esc(created)}</pre>
</section>"""
    rows = []
    now = time.time()
    for c in codes:
        if c["revoked"]:
            state = "Revocato"
        elif c["uses_left"] <= 0:
            state = "Esaurito"
        elif c["expires"] <= now:
            state = "Scaduto"
        else:
            state = "Valido"
        revoke = ""
        if state == "Valido":
            revoke = (f'<form method="post" action="/enroll/{c["id"]}/revoke" class="inline">{csrf(session)}'
                      '<button class="link">Revoca</button></form>')
        rows.append(f'<tr><td>{esc(c["customer"] or "—")}</td><td>{esc(c["note"])}</td>'
                    f'<td>{c["used"]} su {c["used"] + max(c["uses_left"], 0)}</td><td>{esc(when(c["expires"]))}</td>'
                    f'<td>{state} {revoke}</td><td>{esc(c["created_by"])}</td></tr>')
    table = (f'<div class="table"><table class="list"><thead><tr><th>Cliente</th><th>Nota</th><th>Usi</th><th>Scade</th>'
             f'<th>Stato</th><th>Creato da</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
             if rows else '<p class="empty">Nessun codice creato.</p>')
    options = "".join(f'<option value="{esc(c)}">' for c in customers if c)
    body = f"""<h1>Aggiungi dispositivi</h1>
<p class="lead">Un codice di registrazione collega al pannello uno o più dispositivi Trota OS Server,
Cloud o Kiosk. I dispositivi entrano già assegnati al cliente indicato.</p>
{shown}
<form method="post" action="/enroll" class="newcode">
{csrf(session)}
<label>Cliente <input name="customer" list="customers" value="{esc(customer)}" maxlength="100"></label>
<datalist id="customers">{options}</datalist>
<label>Nota <input name="note" maxlength="200" placeholder="es. schermi del negozio di via Roma"></label>
<label>Dispositivi <input name="uses" type="number" min="1" max="10000" value="1"></label>
<label>Valido per giorni <input name="days" type="number" min="1" max="365" value="7"></label>
<button class="btn">Crea il codice</button>
</form>
<section><h2>Codici</h2>{table}</section>"""
    return page("Aggiungi dispositivi", body, session, "enroll")


def _legal(title: str, body: str, session) -> str:
    return page(title, f'<article class="legal"><h1>{esc(title)}</h1>'
                       f'<p class="muted">Aggiornata il {esc(COMPANY["updated"])}</p>{body}</article>', session)


def privacy_page(session, interval: int, retention_days: int) -> str:
    c = {k: esc(v) for k, v in COMPANY.items() if isinstance(v, str)}
    body = f"""
<p>Trota Fleet è il pannello con cui {c["name"]} gestisce a distanza i dispositivi Trota OS Server, Cloud e
Kiosk dei propri clienti. Questa pagina spiega quali dati personali passano dal pannello, come chiede il
Regolamento (UE) 2016/679 (GDPR).</p>

<h2>Chi è responsabile dei dati</h2>
<p>{c["ident"]} · <a href="mailto:{c["email"]}">{c["email"]}</a></p>
<ul>
<li><strong>Dati delle persone che usano il pannello</strong> (amministratori e tecnici):
{c["name"]} è <strong>titolare del trattamento</strong>.</li>
<li><strong>Dati dei dispositivi dei clienti</strong>: il titolare è il cliente proprietario del dispositivo;
{c["name"]} li tratta per suo conto come <strong>responsabile del trattamento</strong> (articolo 28 GDPR),
secondo il contratto e l'accordo sul trattamento dei dati firmati con il cliente.</li>
</ul>

<h2>Quali dati</h2>
<h3>Persone che usano il pannello</h3>
<ul>
<li>nome utente e password (salvata solo in forma cifrata non reversibile, PBKDF2);</li>
<li>una sessione di accesso (cookie tecnico, vedi la <a href="/cookie">pagina sui cookie</a>), che dura al massimo 7 giorni;</li>
<li>il nome di chi ha inviato ogni comando, nello storico del dispositivo;</li>
<li>l'indirizzo IP, tenuto solo in memoria e per al massimo 15 minuti, per bloccare chi tenta di indovinare le password.</li>
</ul>
<p>Base giuridica: il contratto di lavoro o di collaborazione e il legittimo interesse alla sicurezza del
servizio (articolo 6.1.b e 6.1.f).</p>

<h3>Dispositivi collegati</h3>
<p>Ogni dispositivo si collega solo dopo che un amministratore lo ha registrato con un codice. Ogni
{interval} secondi invia: nome del dispositivo, sistema ed edizione, versione del kernel, da quanto è acceso,
carico, memoria e disco usati, indirizzi IP di rete, numero di aggiornamenti da installare, se serve un
riavvio e, sui chioschi, l'indirizzo della pagina mostrata. Il pannello registra anche l'indirizzo IP da cui
arriva il collegamento.</p>
<p><strong>Non vengono raccolti</strong> file, contenuto dello schermo, tasti premuti, programmi in uso, siti
visitati, nomi o attività delle persone che usano il dispositivo. Il pannello può inviare solo quattro
comandi di manutenzione (cambiare la pagina del chiosco, riavviare il chiosco, installare gli aggiornamenti,
riavviare) e non può eseguire altri programmi.</p>
<p>Gli indirizzi IP sono dati personali; gli altri dati descrivono la macchina. Scopo: assistenza,
manutenzione e sicurezza dei dispositivi, come previsto dal contratto con il cliente.</p>

<h2>Per quanto tempo</h2>
<ul>
<li>stato del dispositivo e ultimo indirizzo IP: solo l'ultimo valore, finché il dispositivo resta nel pannello;
rimuovendolo si cancellano subito anche tutti i suoi comandi;</li>
<li>storico dei comandi e loro risultati: {retention_days} giorni, poi vengono cancellati automaticamente;</li>
<li>codici di registrazione scaduti, revocati o esauriti: {retention_days} giorni;</li>
<li>sessioni di accesso: al massimo 7 giorni; tentativi di accesso falliti: 15 minuti, solo in memoria;</li>
<li>alla fine del contratto, i dati del cliente vengono cancellati o restituiti come previsto dall'accordo
sul trattamento dei dati.</li>
</ul>

<h2>Dove sono i dati e chi li tratta</h2>
<table>
<tr><th>Fornitore</th><th>Cosa fa</th><th>Dove</th></tr>
<tr><td>Render Services, Inc.</td><td>esegue il pannello</td><td>server a Francoforte (Germania)</td></tr>
<tr><td>Cloudflare, Inc.</td><td>database (D1) e rete che protegge il collegamento</td><td>database nella regione scelta alla creazione (Europa occidentale), rete mondiale</td></tr>
</table>
<p>Sono responsabili (o sub-responsabili) del trattamento vincolati da contratto. Entrambe le società hanno
sede negli Stati Uniti: gli eventuali trasferimenti si basano sul EU-U.S. Data Privacy Framework e sulle
Clausole contrattuali standard della Commissione europea.</p>

<h2>Sicurezza</h2>
<ul>
<li>collegamenti solo cifrati (HTTPS), anche tra dispositivi e pannello;</li>
<li>password, segreti dei dispositivi, sessioni e codici salvati solo come impronta non reversibile;</li>
<li>ogni dispositivo ha un segreto suo; rimuoverlo dal pannello lo scollega subito;</li>
<li>protezione contro tentativi ripetuti di accesso, moduli protetti da CSRF, pagine senza script esterni.</li>
</ul>

<h2>Diritti</h2>
<p>Chi usa il pannello può chiedere a {c["name"]} di accedere ai propri dati, correggerli, cancellarli,
limitarne il trattamento, riceverli o opporsi (articoli 15–22): <a href="mailto:{c["email"]}">{c["email"]}</a>.
Per i dati dei dispositivi la richiesta va fatta al cliente titolare, che {c["name"]} aiuta a rispondere.
Resta il diritto di reclamo al Garante per la protezione dei dati personali
(<a href="https://www.garanteprivacy.it" rel="noopener">www.garanteprivacy.it</a>).</p>
"""
    return _legal("Informativa privacy del pannello", body, session)


def cookie_page(session) -> str:
    body = """
<p>Il pannello usa <strong>un solo cookie</strong>, tecnico, necessario per restare collegati dopo
l'accesso. Non ci sono cookie di statistica, profilazione o di terze parti, quindi non serve il consenso
(articolo 122 del Codice privacy e linee guida del Garante del 10 giugno 2021).</p>
<table>
<tr><th>Nome</th><th>A cosa serve</th><th>Durata</th></tr>
<tr><td><code>trota_fleet</code></td><td>tiene aperta la sessione dopo l'accesso. Contiene solo un codice casuale;
è inviato solo in HTTPS, non è leggibile da script e non viene inviato ad altri siti.</td>
<td>7 giorni, o fino a quando si esce</td></tr>
</table>
<p>Il pannello non usa altre tecnologie di memorizzazione nel browser (localStorage o simili) e non carica
risorse da altri siti.</p>
<p>Si può cancellare il cookie in qualsiasi momento dalle impostazioni del browser: si viene scollegati.</p>
<p>Vedi anche l'<a href="/privacy">informativa privacy</a>.</p>
"""
    return _legal("Cookie", body, session)
