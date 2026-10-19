#!/usr/bin/env bash
# Install (or update) the T5DR lobby server on a plain Linux VPS (Debian 12 / Ubuntu 22.04+,
# any systemd distribution with Python 3.10+). Run from a checkout of the repository:
#
#   sudo lobby/deploy/linux/install.sh --domain lobby.example.org --email you@example.org --agree-tos --firewall ufw
#   sudo lobby/deploy/linux/install.sh --self-signed --firewall ufw        (no domain: pinned certificate)
#   sudo lobby/deploy/linux/install.sh --relay-only --relay-id usw --firewall ufw   (a relay node, below)
#
# Options
#   --domain NAME      Let's Encrypt certificate via certbot (standalone: needs TCP 80 reachable
#                      during issue/renewal; nothing else uses port 80). Renewals are automatic.
#   --email ADDR       for Let's Encrypt expiry mails (else registered without an address)
#   --agree-tos        you accept the Let's Encrypt Subscriber Agreement (certbot asks otherwise)
#   --self-signed      a 10-year self-signed certificate; players pin its fingerprint (the default
#                      when no --domain is given)
#   --no-tls           plain TCP; accounts are then switched off (guests only)
#   --force-relay      relay every match (players never see each other's IP address; before 1.1.2 this
#                      option was called --relay-only)
#   --relay-only       a relay-only node for a central lobby elsewhere (docs/HOSTING.md "Adding a relay
#                      server"): only the UDP relay (port 7781), no accounts, no database, no TLS. Makes
#                      /etc/t5lobby/relay.secret (keep it; the central server needs the same file)
#   --relay-id ID      with --relay-only: the node's id in the central's relays.json (e.g. usw)
#   --central ADDR     with --relay-only: the central server's address(es), comma separated; control
#                      packets from anywhere else are dropped (optional: the secret is checked anyway)
#   --firewall ufw|nft|none   open the lobby ports (and SSH) in the host firewall; default none
#   --prefix DIR       where the code goes (default /opt/t5lobby)
#   --dry-run          print what would be done, change nothing
#   --root DIR         install into DIR as if it were / (staging, tests): no user, no systemd,
#                      no certbot, no firewall
#   --uninstall        stop and remove the service, the code and the hooks (keeps the database in
#                      /var/lib/t5lobby and the settings in /etc/t5lobby)
# Environment: PYTHON=/path/to/python3 to use another interpreter.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/../.." && pwd)"          # the lobby/ folder of the checkout
PREFIX=/opt/t5lobby
DOMAIN="" EMAIL="" AGREE=0 TLS=auto FIREWALL=none FORCE_RELAY=0 RELAY_ONLY=0 RELAY_ID="" CENTRAL="" DRY=0 ROOT="" UNINSTALL=0
PY="${PYTHON:-python3}"
SVC_USER=t5lobby

die() { echo "install.sh: $*" >&2; exit 1; }
while [ $# -gt 0 ]; do
    case "$1" in
        --domain) DOMAIN="${2:?}"; TLS=letsencrypt; shift ;;
        --email) EMAIL="${2:?}"; shift ;;
        --agree-tos) AGREE=1 ;;
        --self-signed) TLS=selfsigned ;;
        --no-tls) TLS=none ;;
        --force-relay) FORCE_RELAY=1 ;;
        --relay-only) RELAY_ONLY=1 ;;
        --relay-id) RELAY_ID="${2:?}"; shift ;;
        --central) CENTRAL="${2:?}"; shift ;;
        --firewall) FIREWALL="${2:?}"; shift ;;
        --prefix) PREFIX="${2:?}"; shift ;;
        --dry-run) DRY=1 ;;
        --root) ROOT="${2:?}"; shift ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help) sed -n '2,36p' "$0"; exit 0 ;;
        *) die "unknown option $1 (see --help)" ;;
    esac
    shift
done
[ "$TLS" = auto ] && TLS=selfsigned
[ "$RELAY_ONLY" = 1 ] && TLS=none-relay       # a relay node has no TCP port: nothing to encrypt there
case "$FIREWALL" in ufw|nft|none) ;; *) die "--firewall is ufw, nft or none" ;; esac
if [ -n "$RELAY_ID" ] && ! printf '%s' "$RELAY_ID" | grep -Eq '^[a-z0-9][a-z0-9_-]{0,15}$'; then
    die "--relay-id: a-z, 0-9, - and _, at most 16 characters"
fi
{ [ -n "$RELAY_ID" ] || [ -n "$CENTRAL" ]; } && [ "$RELAY_ONLY" = 0 ] && die "--relay-id and --central go with --relay-only"
# (pwd -W: Git Bash on Windows, so that a staged layout can be tried with Windows' Python)
[ -n "$ROOT" ] && { ROOT="$(mkdir -p "$ROOT" && cd "$ROOT" && (pwd -W 2>/dev/null || pwd))"; FIREWALL=none; }
SYSTEM=1; [ -n "$ROOT" ] && SYSTEM=0

ETC="$ROOT/etc/t5lobby"
STATE="$ROOT/var/lib/t5lobby"
CODE="$ROOT$PREFIX"
UNIT="$ROOT/etc/systemd/system/t5lobby.service"
ADMIN="$ROOT/usr/local/bin/t5lobby-admin"
HOOKS="$ROOT/etc/letsencrypt/renewal-hooks"

run() {   # run a command, or show it in a dry run
    if [ "$DRY" = 1 ]; then printf '+ %s\n' "$*"; else "$@"; fi
}
write() { # write stdin to a file (mode), or show it in a dry run
    local dest="$1" mode="$2"
    if [ "$DRY" = 1 ]; then printf '+ write %s (mode %s):\n' "$dest" "$mode"; sed 's/^/|   /'; return; fi
    mkdir -p "$(dirname "$dest")"
    cat > "$dest.tmp"; chmod "$mode" "$dest.tmp"; mv -f "$dest.tmp" "$dest"
}
own() {   # chown only on a real system install
    [ "$SYSTEM" = 1 ] && run chown "$@" || true
}
step() { printf '\n== %s\n' "$*"; }

# ---------------------------------------------------------------------------- uninstall
if [ "$UNINSTALL" = 1 ]; then
    step "removing the service (database and settings are kept)"
    [ "$SYSTEM" = 1 ] && run systemctl disable --now t5lobby || true
    run rm -f "$UNIT" "$ADMIN" "$HOOKS/deploy/t5lobby.sh" "$HOOKS/pre/t5lobby.sh" "$HOOKS/post/t5lobby.sh"
    run rm -rf "$CODE"
    [ "$SYSTEM" = 1 ] && run systemctl daemon-reload || true
    echo "Kept: $STATE (database, backups) and $ETC (settings, certificates). Delete them by hand if wanted."
    exit 0
fi

# ---------------------------------------------------------------------------- checks
step "checks"
[ -f "$SRC/t5lobby/server/lobby.py" ] || die "run me from the repository (no $SRC/t5lobby/server)"
if [ "$SYSTEM" = 1 ] && [ "$DRY" = 0 ] && [ "$(id -u)" != 0 ]; then die "run as root (sudo)"; fi
"$PY" - <<'EOF' || die "Python 3.10 or newer is needed (apt install python3)"
import sys
assert sys.version_info >= (3, 10), sys.version
import asyncio, sqlite3, ssl, hashlib
hashlib.scrypt(b"x", salt=b"y", n=16, r=8, p=1)
print("python", sys.version.split()[0], "| sqlite", sqlite3.sqlite_version, "|", ssl.OPENSSL_VERSION)
EOF
if [ "$SYSTEM" = 1 ] && ! command -v systemctl >/dev/null; then
    [ "$DRY" = 1 ] && echo "(no systemd here; fine for a dry run)" || die "systemd is needed (or use Docker: lobby/compose.yaml)"
fi
PYBIN="$(command -v "$PY" || echo "$PY")"

# ---------------------------------------------------------------------------- user
if [ "$SYSTEM" = 1 ]; then
    step "service user"
    if id "$SVC_USER" >/dev/null 2>&1; then echo "user $SVC_USER exists"
    else run useradd --system --home-dir /var/lib/t5lobby --no-create-home --shell /usr/sbin/nologin "$SVC_USER"; fi
fi

# ---------------------------------------------------------------------------- code
step "code -> $CODE"
run rm -rf "$CODE/t5lobby"
run mkdir -p "$CODE/t5lobby/server" "$CODE/t5lobby/data"
for f in "$SRC"/t5lobby/*.py; do run install -m 0644 "$f" "$CODE/t5lobby/"; done
for f in "$SRC"/t5lobby/server/*.py; do run install -m 0644 "$f" "$CODE/t5lobby/server/"; done
for f in "$SRC"/t5lobby/data/*.json; do run install -m 0644 "$f" "$CODE/t5lobby/data/"; done
run install -m 0644 "$SRC/servers.json" "$SRC/run.py" "$CODE/"
own -R root:root "$CODE"
# import and construct the server once (catches a missing module or data file before systemd does)
if [ "$RELAY_ONLY" = 1 ]; then
    run "$PYBIN" -c "import sys; sys.path.insert(0, '$CODE'); import t5lobby.server.admin; from t5lobby.server import Config; from t5lobby.server.relaynode import RelayNode; RelayNode(Config(), b'x' * 32); print('code ok')"
else
    run "$PYBIN" -c "import sys; sys.path.insert(0, '$CODE'); import t5lobby.server.admin; from t5lobby.server import Config, LobbyServer; LobbyServer(Config(db=':memory:')).store.close(); print('code ok')"
fi

# ---------------------------------------------------------------------------- settings
step "settings -> $ETC/t5lobby.env"
run mkdir -p "$ETC/tls" "$STATE/backups"
own root:"$SVC_USER" "$ETC" "$ETC/tls"
run chmod 0750 "$ETC" "$ETC/tls"
own "$SVC_USER":"$SVC_USER" "$STATE" "$STATE/backups"
run chmod 0750 "$STATE"
if [ -f "$ETC/t5lobby.env" ] && [ "$DRY" = 0 ]; then
    echo "keeping the existing $ETC/t5lobby.env"
else
    write "$ETC/t5lobby.env" 0640 < "$SRC/deploy/t5lobby.env.example"
    own root:"$SVC_USER" "$ETC/t5lobby.env"
fi
setenv() {   # set KEY=value in the env file (replaces a commented or existing line)
    local key="$1" val="$2" f="$ETC/t5lobby.env"
    if [ "$DRY" = 1 ]; then printf '+ set %s=%s in %s\n' "$key" "$val" "$f"; return; fi
    if grep -qE "^#?${key}=" "$f"; then
        local tmp; tmp="$(mktemp)"
        awk -v k="$key" -v v="$val" 'BEGIN{d=0} $0 ~ "^#?"k"=" {if(!d){print k"="v; d=1}; next} {print}' "$f" > "$tmp"
        cat "$tmp" > "$f"; rm -f "$tmp"
    else
        printf '%s=%s\n' "$key" "$val" >> "$f"
    fi
}
[ "$FORCE_RELAY" = 1 ] && setenv T5L_FORCE_RELAY 1
if [ "$RELAY_ONLY" = 1 ]; then
    step "relay node: secret -> $ETC/relay.secret"
    # The central server needs the same file (docs/HOSTING.md "Adding a relay server"); an existing one is kept.
    if [ -f "$ETC/relay.secret" ] && [ "$DRY" = 0 ]; then
        echo "keeping the existing $ETC/relay.secret (the central server has a copy of it)"
    else
        run "$PYBIN" -c "import sys; sys.path.insert(0, '$CODE'); from t5lobby import relayctl; relayctl.write_secret('$ETC/relay.secret')"
    fi
    own root:"$SVC_USER" "$ETC/relay.secret"
    run chmod 0640 "$ETC/relay.secret"
    setenv T5L_RELAY_SECRET_FILE /etc/t5lobby/relay.secret
    setenv T5L_UDP_PORT2 0
    [ -n "$RELAY_ID" ] && setenv T5L_RELAY_ID "$RELAY_ID"
    [ -n "$CENTRAL" ] && setenv T5L_RELAY_CENTRAL "$CENTRAL"
fi

# ---------------------------------------------------------------------------- firewall
step "firewall: $FIREWALL"
case "$FIREWALL" in
    ufw)
        command -v ufw >/dev/null || run apt-get install -y ufw
        run ufw allow 22/tcp comment ssh
        if [ "$RELAY_ONLY" = 1 ]; then
            run ufw allow 7781/udp comment t5relay
        else
            run ufw allow 7781/tcp comment t5lobby
            run ufw allow 7781:7782/udp comment t5lobby
        fi
        run ufw --force enable
        ;;
    nft)
        NFT_RULES="$SRC/deploy/linux/nftables-t5lobby.conf"
        [ "$RELAY_ONLY" = 1 ] && NFT_RULES="$SRC/deploy/linux/nftables-t5relay.conf"
        write "$ROOT/etc/nftables.d/t5lobby.nft" 0644 < "$NFT_RULES"
        if ! grep -q 'nftables.d/t5lobby.nft' "$ROOT/etc/nftables.conf" 2>/dev/null; then
            if [ "$DRY" = 1 ]; then echo "+ append include \"/etc/nftables.d/t5lobby.nft\" to /etc/nftables.conf"
            else echo 'include "/etc/nftables.d/t5lobby.nft"' >> "$ROOT/etc/nftables.conf"; fi
        fi
        run nft -f "$ROOT/etc/nftables.d/t5lobby.nft"
        run systemctl enable nftables
        ;;
    none)
        echo "Open these inbound ports in your firewall / the provider's cloud firewall:"
        if [ "$RELAY_ONLY" = 1 ]; then
            echo "  UDP 7781   (players and the central server; nothing else -- a relay node has no TCP port)"
        else
            echo "  TCP 7781, UDP 7781, UDP 7782   (and TCP 80 if you use --domain: Let's Encrypt renewals)"
        fi
        ;;
esac

# ---------------------------------------------------------------------------- TLS
step "TLS: $TLS"
FINGERPRINT=""
case "$TLS" in
    letsencrypt)
        if [ "$SYSTEM" = 0 ]; then echo "(--root: skipping certbot)";
        else
            if ! command -v certbot >/dev/null; then
                if command -v apt-get >/dev/null || [ "$DRY" = 1 ]; then run apt-get install -y certbot
                else die "install certbot first (https://certbot.eff.org)"; fi
            fi
            write "$HOOKS/deploy/t5lobby.sh" 0755 < "$SRC/deploy/linux/certbot-deploy-hook.sh"
            # standalone issue/renewal needs TCP 80 for a minute: the host firewall opens it only then
            if [ "$FIREWALL" = ufw ]; then
                printf '#!/bin/sh\nufw allow 80/tcp >/dev/null\n' | write "$HOOKS/pre/t5lobby.sh" 0755
                printf '#!/bin/sh\nufw delete allow 80/tcp >/dev/null\n' | write "$HOOKS/post/t5lobby.sh" 0755
            elif [ "$FIREWALL" = nft ]; then
                printf '#!/bin/sh\nnft insert rule inet t5lobby input tcp dport 80 accept comment certbot\n' \
                    | write "$HOOKS/pre/t5lobby.sh" 0755
                printf '#!/bin/sh\nfor h in $(nft -a list chain inet t5lobby input | awk %s); do nft delete rule inet t5lobby input handle "$h"; done\n' \
                    "'/certbot/ {print \$NF}'" | write "$HOOKS/post/t5lobby.sh" 0755
            fi
            args=(certonly --standalone -d "$DOMAIN" --keep-until-expiring)
            if [ -n "$EMAIL" ]; then args+=(-m "$EMAIL"); else args+=(--register-unsafely-without-email); fi
            # without --agree-tos certbot shows the Let's Encrypt Subscriber Agreement and asks
            if [ "$AGREE" = 1 ]; then args+=(--non-interactive --agree-tos); fi
            if [ "$FIREWALL" != none ]; then run "$HOOKS/pre/t5lobby.sh"; fi
            run certbot "${args[@]}"
            if [ "$FIREWALL" != none ]; then run "$HOOKS/post/t5lobby.sh"; fi
            if [ "$DRY" = 1 ]; then run env RENEWED_LINEAGE="/etc/letsencrypt/live/$DOMAIN" "$HOOKS/deploy/t5lobby.sh"
            else RENEWED_LINEAGE="/etc/letsencrypt/live/$DOMAIN" "$HOOKS/deploy/t5lobby.sh"; fi
        fi
        setenv T5L_TLS_CERT /etc/t5lobby/tls/fullchain.pem
        setenv T5L_TLS_KEY /etc/t5lobby/tls/privkey.pem
        ;;
    selfsigned)
        if [ -f "$ETC/tls/cert.pem" ] && [ "$DRY" = 0 ]; then
            echo "keeping the existing certificate (players pinned its fingerprint)"
        else
            NAME="$(hostname -f 2>/dev/null || hostname)"
            run "$PYBIN" -c "import sys; sys.path.insert(0, '$CODE'); from t5lobby.server.admin import main; sys.exit(main(['gen-cert', '--dir', '$ETC/tls', '--name', '$NAME']))"
        fi
        own root:"$SVC_USER" "$ETC/tls/cert.pem" "$ETC/tls/key.pem"
        run chmod 0640 "$ETC/tls/key.pem"
        setenv T5L_TLS_CERT /etc/t5lobby/tls/cert.pem
        setenv T5L_TLS_KEY /etc/t5lobby/tls/key.pem
        [ "$DRY" = 0 ] && FINGERPRINT="$("$PYBIN" -c "import sys; sys.path.insert(0, '$CODE'); from t5lobby.server.selfsigned import fingerprint; print(fingerprint('$ETC/tls/cert.pem'))")"
        ;;
    none)
        echo "WARNING: no TLS. Accounts are switched off (guests only); passwords would be readable."
        setenv T5L_ACCOUNTS 0
        ;;
    none-relay)
        echo "(relay node: no TCP port, no TLS; the control channel is authenticated with relay.secret)"
        ;;
esac
if [ -n "$ROOT" ]; then      # staging: point the settings at the staged paths
    sed -i.bak -e "s#=/etc/t5lobby/#=$ETC/#" "$ETC/t5lobby.env" 2>/dev/null && rm -f "$ETC/t5lobby.env.bak" || true
fi

# ---------------------------------------------------------------------------- admin wrapper, unit
step "admin tool -> $ADMIN, service -> $UNIT"
write "$ADMIN" 0755 <<EOF
#!/bin/sh
# t5lobby-admin: the lobby's admin tool with the service's settings, as the service user.
#   sudo t5lobby-admin status | users | ban NAME --days 7 | backup | ...   (--help lists everything)
[ "\$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
while IFS= read -r line; do
    case "\$line" in T5L_*=*) export "\$line" ;; esac
done < "$ETC/t5lobby.env"
export T5L_DB="\${T5L_DB:-$STATE/t5lobby.db}" T5L_BACKUP_DIR="\${T5L_BACKUP_DIR:-$STATE/backups}"
cd "$CODE" || exit 1
if [ "$SYSTEM" = 1 ]; then exec runuser -u $SVC_USER -- "$PYBIN" -m t5lobby.server.admin "\$@"; fi
exec "$PYBIN" -m t5lobby.server.admin "\$@"
EOF
UNIT_EDIT=(-e "s#^WorkingDirectory=.*#WorkingDirectory=$PREFIX#" -e "s#^ExecStart=/usr/bin/python3 #ExecStart=$PYBIN #")
if [ "$RELAY_ONLY" = 1 ]; then
    UNIT_EDIT+=(-e "s#^Description=.*#Description=T5DR Online relay node#"
                -e "s#-m t5lobby.server\$#-m t5lobby.server.relaynode#")
fi
sed "${UNIT_EDIT[@]}" "$SRC/deploy/linux/t5lobby.service" | write "$UNIT" 0644

# ---------------------------------------------------------------------------- start
if [ "$SYSTEM" = 1 ]; then
    step "starting"
    run systemctl daemon-reload
    run systemctl enable t5lobby
    run systemctl restart t5lobby
    if [ "$DRY" = 0 ]; then
        for _ in 1 2 3 4 5 6 7 8 9 10; do "$ADMIN" health -q && break; sleep 1; done
        "$ADMIN" health || { journalctl -u t5lobby -n 30 --no-pager; die "the server did not come up"; }
    fi
fi

# ---------------------------------------------------------------------------- summary
step "done"
IP_GUESS="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
if [ "$RELAY_ONLY" = 1 ]; then
    [ -n "$IP_GUESS" ] || IP_GUESS="NODE-ADDRESS"
    echo "Relay node: UDP $IP_GUESS:7781  (id: ${RELAY_ID:-none -- pass --relay-id})"
    echo "On the CENTRAL server (docs/HOSTING.md \"Adding a relay server\"):"
    echo "  1. copy this node's secret there:  /etc/t5lobby/relay-${RELAY_ID:-ID}.secret  (owner root, group t5lobby, mode 0640)"
    echo "     it is the one line in $ETC/relay.secret on this machine"
    echo "  2. add this entry to /etc/t5lobby/relays.json (\"relays\": [...]):"
    echo "     {\"id\": \"${RELAY_ID:-ID}\", \"name\": \"REGION NAME\", \"host\": \"$IP_GUESS\", \"port\": 7781, \"secret_file\": \"relay-${RELAY_ID:-ID}.secret\"}"
    echo "  3. sudo t5lobby-admin status there: \"relay ${RELAY_ID:-ID} ...: up\" within seconds"
    echo "Admin: sudo t5lobby-admin status | health     Logs: journalctl -u t5lobby -f"
    exit 0
fi
HOSTNAME_GUESS="${DOMAIN:-$IP_GUESS}"
[ -n "$HOSTNAME_GUESS" ] || HOSTNAME_GUESS="SERVER-ADDRESS"
echo "Server: $HOSTNAME_GUESS:7781  (TLS: $TLS)"
[ -n "$FINGERPRINT" ] && echo "Certificate fingerprint (players pin it): $FINGERPRINT"
echo "servers.json entry for the launcher (lobby/servers.json in the next release):"
if [ "$DRY" = 1 ]; then echo "  (dry run)"
else
    case "$TLS" in
        letsencrypt) MODE=(--ca) ;; selfsigned) MODE=(--cert "$ETC/tls/cert.pem") ;; *) MODE=(--plain) ;;
    esac
    "$PYBIN" -c "import sys; sys.path.insert(0, '$CODE'); from t5lobby.server.admin import main; sys.exit(main(sys.argv[1:]))" \
        server-entry --name "T5DR Online" --host "$HOSTNAME_GUESS" "${MODE[@]}" | sed 's/^/  /'
fi
echo "Admin: sudo t5lobby-admin status | users | ban NAME | backup     Logs: journalctl -u t5lobby -f"
