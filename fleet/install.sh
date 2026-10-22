#!/bin/bash
# Trota Fleet panel: install or update on a Trota OS (or Ubuntu) computer.
#
#   sudo fleet/install.sh
#
# Copies the panel to /opt/trota-fleet, runs it as the system user
# "trota-fleet" on http://127.0.0.1:8080 (service trota-fleet-panel), with a
# daily backup of the database. Optionally:
#   - publishes it on the Internet with a Cloudflare Tunnel (no port opened
#     on the router, HTTPS by Cloudflare);
#   - keeps a laptop awake while it is on mains power.
# Running it again updates the panel and keeps the data.
#
# Without questions (answers in the environment):
#   TROTA_FLEET_PUBLIC_URL=https://...  TROTA_FLEET_ADMIN=name  TROTA_FLEET_PASSWORD=...
#   TROTA_FLEET_TUNNEL_TOKEN=...  TROTA_FLEET_KEEP_AWAKE=yes|no
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP=/opt/trota-fleet
DATA=/var/lib/trota-fleet-panel
DEFAULTS=/etc/default/trota-fleet-panel
UNIT=/etc/systemd/system

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf 'Errore: %s\n' "$*" >&2; exit 1; }
# ask VAR "question": the answer, from the environment variable VAR if set.
ask() {
    local a
    if [ -n "${!1+x}" ]; then printf '%s' "${!1}"; return; fi
    read -r -p "$2 " a </dev/tty || true
    printf '%s' "$a"
}
yes_no() { local a; a="$(ask "$1" "$2 [S/n]")"; [[ -z "$a" || "$a" =~ ^[sSyY] ]]; }

[ "$(id -u)" = 0 ] || die "va avviato con sudo:  sudo $0"
[ -d "$HERE/trota_fleet" ] || die "non trovo $HERE/trota_fleet"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "serve Python 3.10 o più recente"
command -v systemctl >/dev/null || die "serve systemd"
OWNER="${SUDO_USER:-}"

say "1/5  Pannello"
id trota-fleet >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin trota-fleet
install -d -m 755 "$APP"
rm -rf "$APP/trota_fleet.new"
cp -r "$HERE/trota_fleet" "$APP/trota_fleet.new"
find "$APP/trota_fleet.new" -name __pycache__ -prune -exec rm -rf {} +
rm -rf "$APP/trota_fleet" && mv "$APP/trota_fleet.new" "$APP/trota_fleet"
chmod -R u=rwX,go=rX "$APP"
install -d -o trota-fleet -g trota-fleet -m 700 "$DATA"
install -m 644 "$HERE/trota-fleet-panel.service" "$UNIT/trota-fleet-panel.service"
cat > "$UNIT/trota-fleet-panel-backup.service" <<'EOF'
[Unit]
Description=Trota Fleet panel: copy of the database

[Service]
Type=oneshot
User=trota-fleet
Environment=PYTHONPATH=/opt/trota-fleet
ExecStart=/usr/bin/python3 -m trota_fleet --db /var/lib/trota-fleet-panel/fleet.db backup /var/lib/trota-fleet-panel/backups
EOF
cat > "$UNIT/trota-fleet-panel-backup.timer" <<'EOF'
[Unit]
Description=Trota Fleet panel: daily copy of the database

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=1h

[Install]
WantedBy=timers.target
EOF
echo "Installato in $APP, dati in $DATA."

say "2/5  Indirizzo pubblico"
current="$(sed -n 's/^TROTA_FLEET_PUBLIC_URL=//p' "$DEFAULTS" 2>/dev/null || true)"
url="$(ask TROTA_FLEET_PUBLIC_URL "Indirizzo del pannello su Internet, es. https://fleet.testardstudios.it [${current:-nessuno}]:")"
url="${url:-$current}"
if [ -n "$url" ]; then
    [[ "$url" =~ ^https://[A-Za-z0-9.-]+$ ]] || die "l'indirizzo deve essere del tipo https://nome.dominio"
fi
printf 'TROTA_FLEET_PUBLIC_URL=%s\n' "$url" > "$DEFAULTS"

say "3/5  Amministratore"
fleet() { runuser -u trota-fleet -- env PYTHONPATH="$APP" python3 -m trota_fleet --db "$DATA/fleet.db" "$@"; }
if [ -n "$(fleet users)" ]; then
    echo "Amministratori: $(fleet users | paste -sd ' ')"
    echo "Per aggiungerne uno o cambiare una password:"
    echo "  sudo runuser -u trota-fleet -- env PYTHONPATH=$APP python3 -m trota_fleet --db $DATA/fleet.db adduser NOME"
else
    name="$(ask TROTA_FLEET_ADMIN "Nome dell'amministratore [${OWNER:-admin}]:")"
    name="${name:-${OWNER:-admin}}"
    if [ -n "${TROTA_FLEET_PASSWORD:-}" ]; then
        fleet adduser "$name"
    else
        until fleet adduser "$name" </dev/tty; do
            echo "Riprova."
        done
    fi
fi

systemctl daemon-reload
systemctl enable -q trota-fleet-panel.service trota-fleet-panel-backup.timer
systemctl restart trota-fleet-panel.service
systemctl start trota-fleet-panel-backup.timer
for _ in $(seq 20); do
    curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1 && break
    sleep 0.5
done
curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1 || {
    journalctl -u trota-fleet-panel -n 20 --no-pager; die "il pannello non è partito"; }
echo "Pannello attivo su http://localhost:8080"

say "4/5  Cloudflare Tunnel"
if systemctl is-active -q cloudflared 2>/dev/null; then
    echo "Il tunnel è già attivo (servizio cloudflared)."
else
    echo "Serve il token del tunnel: Cloudflare → Zero Trust → Networks → Tunnels → Create a tunnel"
    echo "(tipo Cloudflared), poi in Public Hostname: il tuo indirizzo → servizio HTTP, localhost:8080."
    token="$(ask TROTA_FLEET_TUNNEL_TOKEN "Incolla il token (invio per saltare):")"
    if [ -n "$token" ]; then
        if ! command -v cloudflared >/dev/null; then
            install -d -m 755 /usr/share/keyrings
            curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
            echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' \
                > /etc/apt/sources.list.d/cloudflared.list
            apt-get update -q && apt-get install -y -q cloudflared
        fi
        cloudflared service install "$token"
        echo "Tunnel installato: parte da solo a ogni accensione."
    else
        echo "Saltato: il pannello resta raggiungibile solo da questo computer."
    fi
fi

say "5/5  Sospensione"
if [ -f /etc/systemd/logind.conf.d/60-trota-fleet.conf ]; then
    echo "Già impostato: con l'alimentatore collegato il computer resta acceso."
elif yes_no TROTA_FLEET_KEEP_AWAKE "Con l'alimentatore collegato, il computer non va in sospensione (neanche chiudendo il coperchio). Procedo?"; then
    install -d /etc/systemd/logind.conf.d
    cat > /etc/systemd/logind.conf.d/60-trota-fleet.conf <<'EOF'
# Trota Fleet panel: on mains power, closing the lid does not suspend.
# On battery the usual behaviour stays. Remove this file to undo.
[Login]
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
EOF
    if [ -n "$OWNER" ] && uid="$(id -u "$OWNER")" && [ -S "/run/user/$uid/bus" ]; then
        runuser -u "$OWNER" -- env DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
            gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' || true
    fi
    echo "Fatto. Il coperchio vale dal prossimo riavvio. Tieni il portatile collegato alla corrente:"
    echo "a batteria va in sospensione come sempre, e il pannello smette di rispondere."
fi

say "Fatto."
echo "  Pannello:   http://localhost:8080${url:+   e   $url}"
echo "  Stato:      systemctl status trota-fleet-panel"
echo "  Copie:      $DATA/backups (una al giorno, ultime 14)"
echo "  Aggiornare: scarica la nuova versione e rilancia  sudo fleet/install.sh"
