"""HTML of the panel pages. Every value from the database or from a device
goes through esc(): device reports are untrusted input."""

from __future__ import annotations

import json
import time
from html import escape
from urllib.parse import urlencode

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
