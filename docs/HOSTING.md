# Hosting the lobby server

How to run the T5DR Online lobby for the public, or just for your friends, and what it costs.
The protocol, NAT traversal and relay are described in [ONLINE.md](ONLINE.md).

The server is standard-library Python 3.10+ (tested with 3.12.10) with no third-party
packages. It needs one TCP port and two UDP ports, about 35 MB of RAM, and very little CPU.

## Contents

- [Recommendation](#recommendation)
- [Options compared](#options-compared)
- [Step by step: a VPS from your phone in about 15 minutes](#step-by-step-a-vps-from-your-phone-in-about-15-minutes)
- [TLS and what the launcher needs](#tls-and-what-the-launcher-needs)
- [servers.json](#serversjson)
- [Docker](#docker)
- [Windows: host for friends, or always on](#windows-host-for-friends-or-always-on)
- [macOS: host on a Mac at home](#macos-host-on-a-mac-at-home)
- [Operations](#operations): admin tool, status and metrics, logs, backups, updates
- [Abuse protection: defaults for a public server](#abuse-protection-defaults-for-a-public-server)
- [Firewall rules](#firewall-rules)
- [Resource estimate (measured)](#resource-estimate-measured)
- [What the owner decides](#what-the-owner-decides)
- [What was verified, and what was not](#what-was-verified-and-what-was-not)

## Recommendation

**Rent a small Linux VPS (about 4–6 € a month), point a domain name at it, and run
`lobby/deploy/linux/install.sh --domain ...`.** That gives you:

- A Let's Encrypt certificate that renews itself, so players need no fingerprint.
- systemd hardening, journald logs, daily database backups, and the `t5lobby-admin` tool.
- An address that doesn't change, and ports that are always open.
- Plenty of headroom: the cheapest 2-vCPU plans handle several hundred players.

If you don't want a domain, use `--self-signed` instead. Players then pin the certificate's
fingerprint, which ships in `servers.json` with the release, so they don't type anything.

Then put the server into `lobby/servers.json`. From the next release on, players open the
launcher's Online tab, pick "T5DR Online" (preselected), and click **Play as guest** or **Log in**.
This is the same experience as Tekken 6 Native Online.

For a friend group without a server, one player clicks **Host for friends** in the launcher. See
[Windows](#windows-host-for-friends-or-always-on).

## Options compared

Prices are approximate list prices from 2025, including VAT where the provider shows it, for
the smallest plan that fits. Check them before you buy; nothing here was ordered or tested on
the providers' side.

| Option | Cost | UDP | Good | Bad |
|---|---|---|---|---|
| **Small VPS** (Hetzner Cloud CX22 / CAX11, Netcup VPS, OVH VPS, similar) | ~4–6 €/month | yes, no restrictions | Fixed public IPv4. 2 vCPU / 2–4 GB, 20 TB (Hetzner) or "unlimited" (OVH, Netcup) traffic. Cloud firewall in the web console. EU locations close to most players. | Costs money. You patch the OS (`unattended-upgrades` does it). |
| **Oracle Cloud Always Free** (Ampere A1, up to 4 OCPU / 24 GB, 10 TB/month egress) | 0 € (card needed to sign up) | yes, but two firewalls: VCN security list **and** the image's own iptables, which reject everything except SSH | More than enough machine for free. | Idle *Always Free* instances are reclaimed: Oracle counts below 20% CPU/network/memory over 7 days as idle, which a lobby always is. Upgrading the account to Pay-As-You-Go stops that but still needs a card. A1 capacity is often "out of host capacity" in popular regions. Sign-up is known to be picky. |
| **Google Cloud free tier** (1 e2-micro, US regions only) | 0 € | yes | Free for good, no reclamation. | 1 GB/month free egress: the lobby list alone for 20 players uses that in days, and the relay in hours. US-only adds latency for EU players. Not suitable. |
| **AWS / Azure free offers** | free for 6–12 months, then ~8–15 $/month | yes | Big providers. | Temporary (AWS moved new accounts to a credit-based free plan in 2025). Egress is billed per GB beyond small allowances, which is expensive for the relay. |
| **PaaS** (Render, Railway, Heroku, Vercel, Cloudflare Workers, ...) | – | **no inbound UDP** | – | Doesn't work: the relay, NAT probe and punching need UDP. Fly.io has UDP, but with its own binding rules and a paid dedicated IPv4 (untested, not recommended). |
| **A player's home PC** (Host for friends) | 0 € | yes, through port forwarding | Nothing to rent. One click in the launcher. Optional automatic port forwarding (UPnP/NAT-PMP). TLS by default. | Only up while that PC is on. Everyone learns the host's home IP (they would in direct matches anyway). Doesn't work behind carrier-grade NAT or DS-Lite: you need a public IPv4. The address changes unless you use DDNS. Relayed matches use the host's upload. |
| **Relay-only mode** (`T5L_FORCE_RELAY=1`, any of the above) | +~170 kbit/s per match each way | – | Players never learn each other's IP address. | Every match goes through the server: more bandwidth, and the detour adds latency (server location matters). |

**Why not a free tier for the public server:** Oracle is the only free option with enough
egress, and its reclamation policy is aimed at exactly this kind of mostly-idle service. A
4–6 € VPS has none of these problems. If you try Oracle anyway, use Pay-As-You-Go. Open UDP
7781–7782 and TCP 7781 in the VCN security list, then on the instance run:
`sudo iptables -I INPUT 5 -p udp --dport 7781:7782 -j ACCEPT; sudo iptables -I INPUT 5 -p tcp --dport 7781 -j ACCEPT; sudo netfilter-persistent save`
(and use `--firewall none` with install.sh).

**Home hosting and the public IP:** if the WAN address on your router's status page differs
from the address the lobby shows you as `ip` (your launcher's log), or starts with `100.64`–`100.127`,
you are behind carrier-grade NAT. Nobody can reach you, and port forwarding can't change that.
Use a VPS.

## Step by step: a VPS from your phone in about 15 minutes

This uses Hetzner Cloud as the example; any provider with Ubuntu 24.04 or Debian 12 works the
same. On a phone you need the provider's app or website and an SSH app (Termius, JuiceSSH,
Blink...). The SSH app can create a key for you.

1. **Create the server** (3 min). Pick Ubuntu 24.04, the smallest shared x86 or Arm plan with 2 vCPU,
   and a location near most players (e.g. Nuremberg/Falkenstein/Helsinki for Europe). Paste
   your SSH app's **public** key. Enable IPv4. Note the IPv4 address.
2. **Cloud firewall** (2 min). Allow inbound **TCP 22**, **TCP 7781**, **UDP 7781–7782**, plus
   **TCP 80** if you will use a domain (Let's Encrypt connects on port 80 for a moment at issue and
   renewal; nothing listens there otherwise). Attach it to the server.
3. **Domain (optional, 2 min).** At your DNS provider, add an `A` record such as
   `lobby.example.org` with the server's IPv4 address. Without a domain, skip this and use `--self-signed`.
4. **Log in and install** (5 min). In the SSH app, connect to `root@<ip>`, then:

   ```sh
   apt update && apt -y full-upgrade && apt -y install git python3 unattended-upgrades
   git clone --depth 1 https://github.com/TheWishin/T5DROnline /opt/src/T5DROnline
   cd /opt/src/T5DROnline
   # with a domain (you accept the Let's Encrypt Subscriber Agreement with --agree-tos):
   lobby/deploy/linux/install.sh --domain lobby.example.org --email you@example.org --agree-tos --firewall ufw
   # or without one:
   lobby/deploy/linux/install.sh --self-signed --firewall ufw
   ```

   The script creates the `t5lobby` user and copies the code to `/opt/t5lobby`. It writes
   `/etc/t5lobby/t5lobby.env` (public-server defaults) and sets up TLS. It opens SSH and the lobby
   ports in ufw, then installs, starts and health-checks the systemd service. At the end it prints
   the `servers.json` entry. `--dry-run` shows every step without changing anything.
5. **Check it** (1 min): `sudo t5lobby-admin status`. Then, on your PC, type the server into the
   launcher's Server field and log in: `tls://lobby.example.org` with a domain, or the
   `host:7781#fingerprint` line the script printed.
6. **Publish it** (2 min). Put the printed entry into `lobby/servers.json` in place of the
   placeholder, and commit. The next release then preselects it for every player.
7. **Optional:** set `T5L_MOTD`, accounts or guests, and relay-only in `/etc/t5lobby/t5lobby.env`.
   Apply with `systemctl restart t5lobby`.

**Updates:** `cd /opt/src/T5DROnline && git pull && lobby/deploy/linux/install.sh <same options>`.
It keeps the settings, certificate and database, and restarts the service. A restart drops
everybody from the lobby for a few seconds; the launchers reconnect when the player logs in
again. Direct (peer-to-peer) games keep running, but **relayed games break**, because relay
sessions live in the server's memory, and results of matches running at that moment are lost.
Update when the status shows few matches running.

**Uninstall:** `install.sh --uninstall`. It keeps `/var/lib/t5lobby` and `/etc/t5lobby`.

## TLS and what the launcher needs

The control channel carries account passwords. Without TLS they would cross the network in
clear: the launcher refuses to send a password to a server that is neither on the player's own
network nor encrypted, and `install.sh --no-tls` and `host --no-tls` turn accounts off. UDP game traffic isn't encrypted.
It carries only pad input.

Let's Encrypt can't be put in front of the lobby with a normal HTTPS reverse proxy (the lobby is
raw TCP, not HTTP), so the server terminates TLS itself. Two setups are supported:

| | Let's Encrypt (`install.sh --domain`) | Self-signed + pinning (`--self-signed`, Host for friends) |
|---|---|---|
| Needs | a domain name, TCP 80 reachable during issue/renewal | nothing |
| Players' client checks | the certificate chain (system CA store) and the hostname | the certificate's SHA-256 fingerprint, nothing else |
| servers.json | `"tls": "ca"` | `"tls": "pin", "fingerprint": "..."` |
| Typed address | `tls://lobby.example.org:7781` | `203.0.113.7:7781#<64 hex digits>` |
| Renewal | every ~60 days, automatic: certbot's timer → `/etc/letsencrypt/renewal-hooks/deploy/t5lobby.sh` copies the files to `/etc/t5lobby/tls/` → the server reloads them (it checks every 5 s; `systemctl reload` also works). No restart, no player action. | none: 10-year certificate. **Don't replace it**: every player would have to update the fingerprint (new `servers.json`). Keep `key.pem` in your backups. |
| Certificate expiry visible in | `t5lobby-admin status`, `/status` (`tls.days_left`), `/metrics` (`t5lobby_tls_cert_days_left`) | same |

**Don't pin a Let's Encrypt certificate.** It changes at every renewal. Use `"tls": "ca"`.

How the self-signed certificate is made: openssl isn't needed. `t5lobby/server/selfsigned.py`
creates an RSA-2048 key and an X.509 certificate with the standard library (in about 0.5 s). The
test suite cross-checks the result with openssl: it parses, the self-signature verifies, and
`openssl rsa -check` passes. You can make one with `t5lobby-admin gen-cert --dir DIR`, and read a
certificate's fingerprint with `t5lobby-admin fingerprint cert.pem`.

**What a launcher needs to connect:** host, TCP port (7781), and the TLS mode plus the
fingerprint for `pin`. The UDP ports aren't configured on the client: the server announces them
in its welcome message (`udp_port`, `udp_port2`).

## servers.json

The launcher's Server box lists the servers from two files, merged by name (later wins):

1. `lobby/servers.json` in the release: what the project publishes.
2. `servers.json` in the player's Online settings folder (`%APPDATA%\T5DROnline\`, next to
   `online.json`; `T5_ONLINE_DIR` overrides it): servers the player added.

```json
{
  "format": "t5dr-servers/1",
  "servers": [
    {
      "name": "T5DR Online",
      "host": "lobby.example.org",
      "port": 7781,
      "tls": "ca",
      "udp_ports": [7781, 7782],
      "region": "EU",
      "note": "official server",
      "default": true
    },
    {
      "name": "Friday group",
      "host": "203.0.113.7",
      "port": 7781,
      "tls": "pin",
      "fingerprint": "3f0c5e...64 hex digits...e1"
    }
  ]
}
```

| Field | | |
|---|---|---|
| `name` | required | shown in the launcher; unique |
| `host` | required | DNS name or IPv4. **Empty = placeholder, ignored**: the shipped file has one until the public server exists |
| `port` | 7781 | TCP control port |
| `tls` | `pin` if a fingerprint is given, else `off` | `ca`, `pin` or `off` |
| `fingerprint` | | SHA-256 of the certificate, hex (colons and case don't matter); required for `pin` |
| `udp_ports`, `region`, `note` | | informational |
| `default` | false | preselected |

Invalid entries are skipped and reported. Implementation and loader: `lobby/t5lobby/servers.py`.
To print an entry for a running server, use `t5lobby-admin server-entry --name ... --host ...`
with `--ca`, `--cert cert.pem` or `--plain`.

## Docker

For any Linux host with Docker (or Podman) instead of systemd:

```sh
cd lobby
cp deploy/t5lobby.env.example t5lobby.env          # edit it
mkdir -p tls && cp /path/to/fullchain.pem tls/cert.pem && cp /path/to/privkey.pem tls/key.pem
#   and in t5lobby.env: T5L_TLS_CERT=/tls/cert.pem  T5L_TLS_KEY=/tls/key.pem
docker compose up -d --build
docker compose exec lobby t5lobby-admin status
```

- Image: `python:3.12.10-slim-bookworm` (pinned; pin the digest too for reproducible builds,
  as the Dockerfile explains). Only `t5lobby/`, `servers.json` and `run.py` are copied in.
  Nothing is pip-installed.
- Runs as uid 10001. The container is read-only with a small `/tmp` tmpfs, all capabilities
  dropped, `no-new-privileges`, 256 MB memory limit and 64 pids.
- Data: the named volume `t5lobby-data` at `/data` (database, `backups/`). TLS: `./tls`
  mounted read-only. The server reloads the files when they change, so a renewal on the host only
  needs to copy them there.
- Health check: `t5lobby-admin health` against the status endpoint inside the container.
- Logs: `docker compose logs -f`; json-file driver rotated at 10 MB × 5.
- Ports published: TCP 7781, UDP 7781, UDP 7782. Docker keeps the clients' real source
  addresses on published UDP ports, which the NAT traversal needs. The compose file explains the
  `network_mode: host` alternative.
- Self-signed instead: `docker compose run --rm lobby t5lobby-admin gen-cert --dir /data/tls`.
  Then set `T5L_TLS_CERT=/data/tls/cert.pem` and `T5L_TLS_KEY=/data/tls/key.pem`.

Docker wasn't installed on the development PC, so the image hasn't been built yet. The same
files and commands were run natively (see [verified](#what-was-verified-and-what-was-not)).

## Windows: host for friends, or always on

**While you play: Host for friends.** The launcher's Online tab has a **Host for friends**
button. Without the launcher, use `lobby\deploy\windows\host-for-friends.cmd` from the release
folder, or `python lobby\run.py host`. It:

- Starts a lobby server on this PC with its data in `%LOCALAPPDATA%\T5DR Online\lobby-host`
  (database, certificate, rotated logs, daily backups).
- Makes a self-signed certificate on first start, so it serves TLS with no setup.
- Prints (and the launcher copies to the clipboard) the line your friends paste as their
  Server, e.g. `203.0.113.7:7781#3f0c…e1`, plus a line for friends on your own network.
- Points your own Server box at `127.0.0.1:7781#…`. Matches between you and a friend go
  through your own relay, which runs on your PC, so they add no detour.
- Stops with the button or Ctrl+C. When launched from the launcher, it also stops when the
  launcher closes.

**Port forwarding:** your router must forward TCP 7781 and UDP 7781–7782 to your PC. Do it in
the router's web page, or tick **Open router ports (UPnP)** (`--map-ports`). Only then does the
program talk to the router. It tries NAT-PMP first (RFC 6886), then UPnP IGD via SSDP, both
implemented with the standard library in `lobby/t5lobby/portmap.py`. Mappings get a one-hour
lease that is renewed while you host and removed when you stop, so a crash leaves nothing open
for more than an hour. On routers that only accept permanent UPnP mappings, they are removed on
a clean stop. The router's description URL is only accepted from the device that announced it,
on a private address, with size-capped replies. `--map-dry-run` logs what it would send and
sends nothing. Your public IP is shown when the router reports it. Otherwise read it from the
router's status page; no outside service is asked.

**Windows Firewall:** the first time, Windows asks whether Python may accept connections.
Allow it for private networks.

**Always on (a PC that stays on):** `lobby\deploy\windows\install-task.ps1`, from an
administrator PowerShell, registers the scheduled task "T5DR Lobby Server". It starts at boot,
whether you are logged on or not (S4U, so no password is stored), runs as you with normal
rights, has no time limit, and restarts every minute after a failure. It uses the release's
`python\pythonw.exe`, so no window. Options:

- `-OpenFirewall`: inbound rules for that python.exe and the ports, on private/domain networks only.
- `-MapPorts`: same as above.
- `-AtLogon`: start at your logon instead of at boot.
- `-DryRun`: shows everything and changes nothing.
- `-Uninstall`: removes the task and the rules, and keeps the data.

A true Windows service would need a service wrapper (pywin32 or NSSM, both third-party). The
scheduled task gives the same behaviour with Windows' own tools.

The release's bundled Python ignores `PYTHONPATH` and the current folder (its `._pth` file), so
`-m t5lobby.server` doesn't work there. `lobby\run.py server|host|admin` works with any Python.

## macOS: host on a Mac at home

For an old Mac at home that stays on. **This was not tested on a real Mac.** The server is the
same Python code as on Windows. The two shell scripts were only syntax-checked and run as dry
runs on Windows. The data-folder logic and the launchd job file have unit tests. Expect one or
two small things to need a fix, and tell us what broke.

### 1. Python 3.10 or newer

The `python3` that comes with macOS is too old. Install Python from python.org/downloads. Take
the newest release your macOS supports (each release page lists the macOS versions it needs).
The server uses only the standard library, so there is nothing else to install.

Open a new Terminal window and check `python3 --version`. It must say 3.10 or higher. If it
still shows an older number, use the full path, for example
`/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`.

### 2. Try it by hand

```sh
cd T5DROnline                       # the folder with lobby/ in it
python3 lobby/run.py host           # add --map-ports to ask the router for the ports
```

It prints the line your friends paste as their Server. Stop it with Ctrl+C.

The data goes to `~/Library/Application Support/T5DR Online/lobby-host`. That folder holds the
database (accounts and ratings), the certificate, the logs and the daily backups. Back it up.
An older run may have used `~/.local/share/t5lobby-host`. If that folder exists and the new one
does not, the old one stays in use, so nothing is left behind. `--data DIR` picks any folder.

### 3. The router

- **Give the Mac a fixed address on your network.** The easy way: in the router's DHCP
  settings, reserve the Mac's current address for the Mac. Or set an address by hand in System
  Settings, Network. The forwarding rules below point at that address, so it must not change.
- **Forward TCP 7781 and UDP 7781-7782** to that address, in the router's web page. Or start
  the host with `--map-ports` and let the router do it (UPnP / NAT-PMP), as on Windows.
- **Check for carrier-grade NAT first.** Find the router's Internet address (also called WAN
  address) on its status page. Then open any "what is my IP" page in a browser. If the two
  differ, or the router's address starts with 100.64 to 100.127, 10., 172.16 to 172.31 or
  192.168, your provider shares one public address between many homes. Forwarding cannot work
  then. Ask the provider for a public address, or rent a small VPS (see the top of this page).

### 4. The macOS firewall

The first time Python listens for connections, macOS may ask whether Python may accept incoming
connections. Click **Allow**. You do this at the Mac. We do not script it. If the firewall is off
(it is off by default), there is no question. If friends cannot connect after the ports are
forwarded, open System Settings, Network, Firewall, and make sure Python is allowed to accept
incoming connections. The menu names differ a little between macOS versions.

### 5. Keep the Mac awake

A sleeping Mac hosts nothing.

- The launchd job below runs the server inside `caffeinate -s`. The Mac does not go to sleep
  while the server runs. **This works on mains power only.** Keep the Mac plugged in. On a
  laptop, keep the lid open (a closed lid usually sleeps the Mac; this was not tried).
- By hand: `caffeinate -s python3 lobby/run.py host`.
- The screen may still turn off. In the energy settings, also turn on "Wake for network
  access", and "Start up automatically after a power failure" if your Mac has it.

### 6. Start at login, restart if it stops

```sh
bash lobby/deploy/macos/install.sh                      # add:  -- --map-ports   if you want that
bash lobby/deploy/macos/uninstall.sh                    # takes it away again
```

No sudo. Everything stays in your home folder.

- It copies the lobby code to `~/Library/Application Support/T5DR Online/lobby-app`. The job
  then does not depend on your checkout, and macOS does not ask for access to Documents or
  Desktop.
- It writes `~/Library/LaunchAgents/org.t5dronline.lobby-host.plist` from the template in
  `lobby/deploy/macos/`, and loads it. The server starts now, at every login, and again within
  15 seconds whenever it stops.
- `--python PATH` picks the Python. By default it looks for python.org's, then Homebrew's, then
  `python3` on the PATH. It never uses `/usr/bin/python3`.
- `--no-caffeinate` leaves out the `caffeinate` wrapper. `--data DIR` changes the data folder.
  `--dry-run` shows the steps and changes nothing.
- Run `install.sh` again after you update the code. Uninstalling keeps your data folder.

A LaunchAgent runs while the user is logged in. If the Mac should come back by itself after a
power cut, turn on automatic login for this user (System Settings, Users & Groups). That does
not work with FileVault, and it lets anyone who touches the Mac use that account. That is your
call.

**Logs.** `logs/launchd.log` in the data folder holds the start banner and any crash text. It is
not rotated, so delete it now and then. The server's own log is `logs/t5lobby.log` next to it,
rotated by the server.

**Admin.** Same tool as everywhere:

```sh
python3 lobby/run.py admin --db "$HOME/Library/Application Support/T5DR Online/lobby-host/t5lobby.db" status
launchctl print gui/$(id -u)/org.t5dronline.lobby-host      # what launchd thinks
```

## Operations

### Admin tool

`sudo t5lobby-admin ...` on a systemd install (a wrapper that loads `/etc/t5lobby/t5lobby.env`
and runs as the service user). Elsewhere, use `docker compose exec lobby t5lobby-admin ...`,
`python lobby/run.py admin ...`, or `python -m t5lobby.server.admin --db FILE ...`. It works on
the SQLite file directly, which is safe while the server runs. The server polls for bans every
5 s and kicks the player.

| Command | |
|---|---|
| `status [--json]` | players online (guests/accounts/playing/searching), rooms, queues, matches running and in the last 24 h by path, relay sessions and kbit/s, accounts, bans, certificate expiry, CPU/RSS |
| `health [-q]` | exit code 0 when the server answers (Docker health check, scripts) |
| `users [TEXT] [--banned]`, `user NAME`, `matches [--player NAME]` | look things up |
| `ban NAME [--days D \| --hours H] [--reason ...]`, `unban NAME` | accounts. Without a duration, the ban is permanent. The player is kicked and their remembered logins end. Later logins are refused with the reason, but only after the correct password, so a ban never reveals that an account exists |
| `ban-ip ADDR\|CIDR ...`, `unban-ip`, `bans` | guests have no account: ban the address or network |
| `reset-password NAME [--password-env VAR]` | a new password from an environment variable, or a random one that is printed once (there is no e-mail, by design); the account's remembered logins end. The player changes it in the launcher |
| `recovery-codes NAME`, `logout-all NAME` | a new set of recovery codes (printed once), or end every remembered login. The same account commands as `accounts_admin` |
| `reset-rating NAME` | back to 1500 / RD 350 and unranked (placement again); the win/loss record stays |
| `delete-user NAME --yes` | also removes the account's remembered logins and recovery codes |
| `purge-guests [--days 30]` | deletes records of guest-only matches older than this. Guests themselves are never stored |
| `purge-inactive --days N [--include-played] --yes` | deletes accounts not seen for N days (by default only accounts that never finished a game: name squatters) |
| `backup [DIR] [--keep N]`, `restore FILE --yes` | see Backups |
| `notice TEXT [--minutes N \| --hours H]`, `notice --clear`, `notices` | a message for every connected player, for example `notice "server restart in 20 min"`. It shows in the launcher's status bar until it ends (default 60 minutes) or is cleared. The server picks it up within 5 s. Players who log in while it shows get it too. At most 200 characters |
| `gen-cert`, `fingerprint`, `server-entry` | see TLS and servers.json |

### Status, health, metrics

The server serves `http://127.0.0.1:7780/` (`T5L_STATUS_HOST`, `T5L_STATUS_PORT`, `0` = off):

- `/health` returns `ok`.
- `/status` returns the JSON behind `t5lobby-admin status`.
- `/metrics` returns the same numbers in Prometheus format (`t5lobby_players_online`,
  `t5lobby_relay_kbit_per_second`, `t5lobby_matches_found_total`, `t5lobby_tls_cert_days_left`, ...).

It shows counts only, no names and no addresses. It stays on loopback. To watch it from
elsewhere, use an SSH tunnel (`ssh -L 7780:127.0.0.1:7780 root@server`), or bind it to a
private interface and allow only your monitor's address. Every 15 minutes the log gets a
one-line summary (`T5L_STATUS_LOG_MINUTES`).

For a simple outside uptime check, monitor TCP 7781 (any "TCP port" monitor works). A TLS
handshake on it proves the server is up.

### Logs

- systemd: the journal (`journalctl -u t5lobby -f`). journald rotates it. Cap it with
  `SystemMaxUse=200M` in `/etc/systemd/journald.conf`.
- Docker: json-file, 10 MB × 5 (compose.yaml).
- macOS (launchd job): `logs/launchd.log` in the data folder (start banner, crashes), and the
  server's own rotated log next to it, see the macOS section above.
- Windows / Host for friends: `T5L_LOG_FILE` (set automatically to
  `...\lobby-host\logs\t5lobby.log`), rotated by the server itself at `T5L_LOG_MAX_MB` (10) ×
  `T5L_LOG_BACKUPS` (5).

The log contains player names and IP addresses (logins, kicks). Treat it as personal data:
keep it short-lived, which the rotation above does.

### Backups

- The server takes an online backup every `T5L_BACKUP_HOURS` (24) into `T5L_BACKUP_DIR` and
  keeps `T5L_BACKUP_KEEP` (14). It uses SQLite's backup API, so it runs safely while the server
  writes. Each backup is integrity-checked and saved as a single self-contained `.db` file, mode
  0600 (it holds password hashes).
  Default locations: systemd `/var/lib/t5lobby/backups`, Docker `/data/backups`, Windows
  `...\lobby-host\backups`.
- On demand: `t5lobby-admin backup [DIR]`.
- **Copy them off the machine**, because a backup on the same disk doesn't survive losing the VPS.
  From your PC: `scp root@server:/var/lib/t5lobby/backups/t5lobby-*.db .` now and then. Or turn on
  your provider's automatic server backups (Hetzner charges 20% of the server price for them).
- Restore: `systemctl stop t5lobby`, then `t5lobby-admin restore FILE --yes`, then
  `systemctl start t5lobby`. Restoring refuses while the server answers, because it keeps ratings
  in memory and would write them back. The replaced database is first saved as
  `pre-restore-*.db` next to it.
- For a self-signed setup, also keep a copy of `/etc/t5lobby/tls/` (or `...\lobby-host\tls`).
  Losing the key means every player has to update the fingerprint.

### Moving to another server

Install on the new machine and stop both. Copy `t5lobby.db` (or restore a backup) and, for a
self-signed setup, the `tls/` folder, then start. Then update the DNS record, or `servers.json`
if you used an IP address.

## Abuse protection: defaults for a public server

All limits are per server process, in memory, and need no configuration. The table lists the
built-in defaults and what `deploy/t5lobby.env.example` (the file install.sh installs) uses for
a public server.

| Limit | Built-in | Public profile | Why |
|---|---|---|---|
| Concurrent connections | 500 (`T5L_MAX_CLIENTS`) | 500 | ~35 MB RAM at this size. The admin tool shows how close you are |
| Connections per address | 8 (`T5L_MAX_PER_IP`) | 8 | Mobile carriers put many players behind one address (CGNAT). 8 is a compromise. Raise it for LAN events |
| New connections per address | 0.5/s, burst 10 (`T5L_CONN_RATE`, `T5L_CONN_BURST`) | same | Also limited by nftables (20/s) when you use `--firewall nft` |
| Messages per connection | 20/s, burst 40. After 10 strikes, a 60 s address ban | same | |
| Unread output per connection | 1 MB (`T5L_MAX_PENDING_KB`) | same | A client that stops reading is dropped. Before this limit, one could pin ~12 MB of server memory |
| Login | 15 s to finish. 5 wrong passwords per address and per name, then 1/min. 3 new accounts per address, then 1 per 10 min | same | |
| Names | 2–16 safe characters. Reserved names refused (`admin…`, `moderator…`, `official…`, `t5lobby…`, `system`, `server`, `p1`, ... ignoring case and punctuation; see RANKED.md), plus any name containing a word from `T5L_NAME_BLOCKLIST` | add a word file | Impersonation, offensive names |
| Chat | 1 line/s, burst 5, 200 characters | same | |
| UDP control packets | 100/s per address **and 5000/s in total** (`T5L_UDP_CTL_PPS`) | same | The total stops spoofed-source ping floods from being reflected at many victims. Answers are never larger than requests |
| Relay per player | 512 kbit/s, 400 packets/s | **256 kbit/s, 240 packets/s** | The game needs ~85 kbit/s at ~60 packets/s. 3–4× headroom, and the relay can't be used as a traffic cannon |
| Relay sessions | 100 (`T5L_MAX_RELAYS`) | 100 | ~17 Mbit/s each way at the game's rate. A 2-vCPU VPS handles that |
| Accounts on a server without TLS | the server warns in its log; the launcher refuses to send a password to it unless it is on the player's own network | install.sh turns accounts off with `--no-tls` | Passwords would cross the network in clear |
| Bans | `t5lobby-admin ban / ban-ip`. Take effect within 5 s | | |

Not handled (and how to cope): results are self-reported, so two colluding accounts can trade
wins. Every match's reports, path and RTT are in the database, and you can use `matches` and
`user`, then `reset-rating` and `ban`. There is no captcha or e-mail verification on account
creation. To clean up, use `purge-inactive`. A determined attacker with many addresses can
still fill the lobby. Lower `T5L_MAX_CLIENTS` keeps the server itself healthy, and the
provider's DDoS filtering handles volumetric floods.

## Firewall rules

Inbound, to the lobby server:

| Port | Proto | What | Needed |
|---|---|---|---|
| 7781 | TCP | control channel (TLS) | always |
| 7781 | UDP | ping, registration, relay | always |
| 7782 | UDP | NAT type probe | recommended (`T5L_UDP_PORT2=0` turns it off; symmetric NATs are then found by failed punching, ~3 s slower) |
| 80 | TCP | Let's Encrypt HTTP-01, during issue/renewal only | only with `--domain` |
| 22 | TCP | SSH | for you |
| 7780 | TCP | status endpoint | **never from outside** (it listens on 127.0.0.1) |

Outbound: the server sends UDP from 7781 to players (relay, acknowledgements) and nothing else,
apart from DNS, package updates and certbot.

- **ufw** (`install.sh --firewall ufw`):
  `ufw allow 22/tcp; ufw allow 7781/tcp; ufw allow 7781:7782/udp; ufw --force enable`. Certbot's
  pre and post hooks open and close port 80 around renewals.
- **nftables** (`--firewall nft`): `lobby/deploy/linux/nftables-t5lobby.conf`. Policy drop, with
  per-address rate limits on new SSH and lobby connections.
- **Cloud firewall** (Hetzner, Oracle security list, ...): the same table. It applies before
  traffic reaches the VPS, so set it in both places.
- **Windows** (home host): allow Python when asked, or use `install-task.ps1 -OpenFirewall`.
  Router: forward TCP 7781 and UDP 7781–7782 to the PC.

## Resource estimate (measured)

Measured with `lobby/tools/load_test.py` on the development PC (Ryzen 9 7950X, Windows 11,
Python 3.12.10, server and clients on localhost, 2026-10-17; repeated after rebasing onto the
ranked lobby). A small VPS's vCPU is roughly 2–3×
slower per core than this desktop core, so multiply the CPU figures by 2–3.

**Lobby** (N players logged in. Each sends a keepalive and an RTT report every 30 s, as the real
client does, and changes status, by opening a room for 5 s, every 20–40 s):

| Players | Whole lists (the server before this work) | Deltas, same entries | **Deltas, current main** (ranked lobby: rank and character in every entry) | Server CPU | RSS |
|---|---|---|---|---|---|
| 50 | 8.8 Mbit/s | 0.42 Mbit/s | **0.62 Mbit/s** | 0.7% of a core | 31 MB |
| 100 | 46.1 Mbit/s | 1.76 Mbit/s | **2.45 Mbit/s** | 1.2% | 32 MB |
| 200 | 186.7 Mbit/s | 6.7 Mbit/s | **9.9 Mbit/s** | 2.3% | 34 MB |

The original server sent the whole player list to everybody on every change, which is
O(players²). At 100 players that is 46 Mbit/s, or about 15 TB a month, enough to use up a VPS's
included traffic (more now, since entries grew). The server now sends a full list once, then
only what changed (`lobby_delta`, negotiated in `hello` so older clients still get whole lists).
It also stops broadcasting every small fluctuation of a player's ping. That is 26–28× less
traffic for the same entries. It still grows with players², but stays at about 25 kbit/s per
player at 100 players with the ranked lobby's larger entries.

**Relay** (K matches forced through the relay, both players sending the game's 60 packets/s of
180 bytes):

| Relayed matches (players) | Traffic in = out | Server CPU | Delivered |
|---|---|---|---|
| 10 (20) | 1.7 Mbit/s each way | 4.8% of a core | 100.0% |
| 25 (50) | 4.3 Mbit/s | 11.2% | 99.95% |
| 50 (100) | 8.6 Mbit/s | 29.2% (20.2% in a repeat on current main) | 99.96% |

That's ~86 kbit/s per relayed player in each direction (it matches the ~85 kbit/s measured
with the real game in ONLINE.md), and ~0.3% of a fast core per relayed player.

**Per 100 concurrent players:**

| | Typical (direct where possible: ~10–20% of matches need the relay) | Worst case (relay-only mode, everybody in a match) |
|---|---|---|
| CPU | ~0.1 vCPU | ~0.3 fast core ≈ 0.6–0.9 VPS vCPU |
| RAM | ~35 MB | ~35 MB |
| Bandwidth out | ~2.5 Mbit/s lobby + ~1–2 Mbit/s relay | ~2.5 lobby + 8.6 relay ≈ 11 Mbit/s (8.6 in) |
| Traffic per month, if 100 players were online 24/7 | ~1.2 TB | ~3.6 TB out, 2.8 TB in |

A 2 vCPU / 2–4 GB VPS with 20 TB of traffic therefore holds several hundred players and the
default 100 relay sessions with room to spare. Real-world averages are far lower than "100
online all month". Over the internet, the relay's cost to players is the detour through the
server's location. Its processing adds 0.1–0.4 ms (ONLINE.md).

## What the owner decides

1. **Where it runs**: a VPS provider and location (recommended), Oracle's free tier (with the
   caveats above), or no public server for now (Host for friends only).
2. **Domain name or not**: `lobby.<your domain>` gives Let's Encrypt (`"tls": "ca"`). Without
   one, it's a self-signed certificate whose fingerprint ships in `servers.json`. Both are secure.
   The self-signed route ties players to that one key, so keep it backed up.
3. **Accounts and guests, or guests only**: accounts give ranked play and kept ratings, but they
   are personal data (a name, a scrypt hash, last-seen time, match history). Guests-only
   (`T5L_ACCOUNTS=0`) stores nothing about people except unranked match records, which
   `purge-guests` cleans. A privacy note for players should say what is stored and that the logs
   contain IP addresses for a short time.
4. **Relay-only (privacy) or direct**: direct is faster and cheaper, but players see each other's
   IP address. Relay-only hides it at ~170 kbit/s per match.
5. **Who moderates**: who gets SSH and `t5lobby-admin`, and where players report cheaters (the MOTD).
6. **Builds**: whether to pin accepted builds (`T5L_BUILDS`) per release, or pair any equal builds.

## What was verified, and what was not

Verified on the development PC (Windows 11), 2026-10-17:

- **The whole lobby test suite (139 tests)** passes on the branch rebased onto main with the
  ranked lobby, both from the source tree and from a staged install made by `install.sh --root`
  (the tests import the installed copy). The hosting tests (35) cover the admin tool, bans and
  kick (saved logins included), IP bans, password, recovery-code and rating resets, purges,
  status/health/metrics, online backup with a scheduled backup and restore, schema migration of
  an old database, delta merging versus the server's view, legacy clients, the pure-Python
  certificate checked by openssl, certificate reload, servers.json, Host for friends end to end,
  and UPnP/NAT-PMP against fake routers on 127.0.0.1. A new Tk test clicks Host for friends and
  logs in through it.
- **`install.sh --dry-run`** with `--domain/--email/--agree-tos/--firewall ufw` and with
  `--self-signed/--firewall nft/--relay-only` prints the expected steps. **`install.sh --root DIR
  --self-signed --relay-only`** (a real staged install) produced the right layout, certificate,
  settings and admin wrapper. The server was then run from that layout with TLS:
  - Pinned clients connect, and a wrong pin is refused.
  - A relay-only match passed the game's handshake through the relay, and the reports were
    reconciled. Before the rebase the result was confirmed; on current main it is `void`,
    because main's integrity rules ignore matches shorter than 30 s.
  - `status` showed the players, relay session and certificate expiry.
  - `ban` kicked the online player within a second, and their login was refused with the
    reason; `unban` lifted it.
  - An online `backup` ran while players were connected.
  - `restore` was refused while the server ran, then succeeded after stopping it, and the
    account created after the backup was gone.
  - Repeated after the rebase. It caught that main's new `t5lobby/data/fighters.json` was
    missing from the install. Fixed: install.sh copies `data/`, and it and the Dockerfile now
    construct the server once at install/build time.
- **Release layout with the bundled isolated Python** (`package_release.add_python`):
  `host-for-friends.cmd` made the certificate, served TLS, ran the port-mapping dry run (nothing
  sent to the router), took a backup and stopped cleanly on request. `install-task.ps1 -DryRun`
  (install and uninstall) printed the plan, refused to run without admin rights, and created no
  task. Its task objects (S4U principal, restart policy) were constructed and checked without
  registering.
- **Load measurements** above.

The macOS setup (docs above, "macOS: host on a Mac at home") was only checked as far as Windows
allows: the data-folder rule with `sys.platform` patched to darwin, the banner line, the
launchd job file (`plistlib`) and its template filling, `bash -n` on both scripts, and a dry run of
`install.sh` / `uninstall.sh` under Git Bash that touched nothing. Eight tests cover this
(`test_hosting.MacHostTest`).

Not verified (nothing was rented, installed or changed on this PC):

- **Anything on a real Mac.** Python from python.org, `launchctl`, `caffeinate -s` keeping the Mac
  awake, the firewall question, a restart after a crash, and starting at login are all untested.

- A real VPS, systemd, ufw/nftables and certbot. The scripts ran only as dry runs and staged
  installs on Git Bash.
- `docker build` and compose: Docker isn't installed here.
- UPnP/NAT-PMP against a real router: only against fakes, by design.
- Two real NATs on the internet (as before, see ONLINE.md).
- A release zip built with `tools/package_release.py` (it now also ships `lobby/t5lobby/server/`,
  `lobby/run.py`, `lobby/servers.json` and `lobby/deploy/windows/`); the layout was reproduced by
  hand with the bundled Python instead.
