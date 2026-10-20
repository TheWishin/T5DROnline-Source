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
- [Adding a relay server](#adding-a-relay-server): relay-only nodes in other regions (Hetzner, Ubuntu 26.04)
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
| **Relay every match** (`T5L_FORCE_RELAY=1`, `install.sh --force-relay`, any of the above) | +~170 kbit/s per match each way | – | Players never learn each other's IP address. | Every match goes through the server: more bandwidth, and the detour adds latency (server location matters). |

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
7. **Optional:** set `T5L_MOTD`, accounts or guests, and relaying every match in `/etc/t5lobby/t5lobby.env`.
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
button. Without the launcher, run `python\python.exe lobby\run.py host` in the release folder
(the release zip carries no script files: virus scanners flag scripts in game downloads). It:

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

**Always on (a PC that stays on):** `lobby\deploy\windows\install-task.ps1` (in the source
repository, not in the release zip), from an administrator PowerShell, registers the scheduled task "T5DR Lobby Server". It starts at boot,
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

## Adding a relay server

Two players whose routers cannot connect directly play through a relay. With only the central
server in Nuremberg, two players in California go California → Germany → California: 300–400 ms
instead of ~20. A **relay-only server** near them (for example Hetzner's Hillsboro, Oregon
location) brings that down to roughly the sum of their round trips to it, typically 30–80 ms.
The lobby, accounts and ranking stay on the one central server, so nobody's rating splits.

How it fits together (protocol: [ONLINE.md](ONLINE.md#regional-relays)):

- A **relay node** runs only the lobby's UDP relay (`python run.py relay`, installed by
  `install.sh --relay-only`): no accounts, no database, no TCP port, one UDP port (7781).
- The **central server** lists its nodes in `/etc/t5lobby/relays.json` (`T5L_RELAYS`). It checks
  every node every 5 s (`T5L_RELAY_CHECK_SECONDS`) and stops giving new matches to a node that
  has not answered for 20 s (`T5L_RELAY_DEAD_SECONDS`), or at once when a node does not answer a
  session request -- that match then takes the next best relay. Edits of `relays.json` are picked
  up within seconds; the players online get the new list at once.
- **Launchers from 1.1.1 on** measure their UDP round trip to every node at login (and every
  5 minutes between matches). When a match needs a relay, the central server takes the relay
  with the **smallest sum of both players' round trips** -- its own relay included -- opens a
  session there and gives each launcher a bind token for it that works for 60 s
  (`T5L_RELAY_BIND_SECONDS`). Older launchers (and a pair with one older launcher) get the
  central relay, as before. A relayed match between two 1.1.1 launchers still moves onto the
  direct path when it starts to work during the match, from a regional relay too.
- The **control channel** between the central server and a node: UDP datagrams on the node's
  relay port, each signed with HMAC-SHA256 under a secret both machines hold
  (`/etc/t5lobby/relay.secret` on the node, `/etc/t5lobby/relay-<id>.secret` on the central server),
  with a timestamp and a one-time id: nobody without the secret can open a session, and a recorded
  request cannot be played back (also not after a node restart: a node takes no request stamped before
  it started). The players' bind tokens in a session request are sealed under the secret (1.1.2 nodes
  and central servers; an older node still gets them readable, and the central server's log says so once:
  update it). The two clocks must agree within 2 minutes (NTP; Ubuntu does it), and within a few seconds
  right after a node restart.
- A node relays **only for sessions the central server opened**, with the central relay's limits:
  the game's packets and the lobby's peer packets only, at most 2048 bytes each, 256 kbit/s and 240
  packets/s per player (public profile), 100 sessions, 3 per internet address, 20 minutes a match
  (renewed for a rematch in the running games), closed after 2 minutes without a packet. It answers
  strangers' UDP pings (that is how launchers measure it; the answer is never larger than the ping)
  and nothing else. It cannot be used as a free proxy.

### Step by step: a relay node on Hetzner (Ubuntu 26.04), about 15 minutes

The central server must run a lobby version with regional relays (1.1.1 or newer) with
`T5L_RELAYS` set; step 5 does that once. Commands marked *node* run on the new server, *central*
on the lobby server, *PC* on the PC that holds the repository (the way the lobby server is updated).

1. **Create the server** (Hetzner Cloud console → Add Server). Location **Hillsboro, OR**, image
   **Ubuntu 26.04**, the smallest shared plan offered there (a relayed match costs about 0.3 % of
   a core: the smallest plan carries the default 100 sessions). IPv4 on. Paste your SSH public key.
   Name it, for example, `t5relay-usw`. Note its IPv4 address (*NODE-IP*). Look at the plan's
   included traffic: US locations include less than the EU ones, and a relayed match moves about
   80 MB per hour each way (two players at ~85 kbit/s).
2. **Cloud firewall** (Firewalls → Create Firewall), inbound rules only:

   | Port | Proto | For |
   |---|---|---|
   | 22 | TCP | SSH |
   | **7781** | **UDP** | the relay: players' pings, binds and game packets, and the central server's control requests |

   Nothing else: a relay node has no TCP 7781, no UDP 7782 and no port 80. Apply it to the server.
   The central server needs **no new inbound port**: it sends its requests from a random UDP port
   and the node's answers come back as replies, which stateful firewalls (ufw, the nftables rules
   below, Hetzner's cloud firewall) let in.
3. **Install** (5 min):

   ```sh
   # node (as root): updates, Python, automatic security updates; the clock must be synchronized
   apt update && apt -y full-upgrade && apt -y install python3 unattended-upgrades
   timedatectl | grep synchronized        # "System clock synchronized: yes"
   mkdir -p /opt/src/T5DROnline
   # PC: copy the lobby folder of the repository (same version as the central server)
   scp -r lobby root@NODE-IP:/opt/src/T5DROnline/
   # node: install the relay node; --relay-id is its name in the central's relays.json,
   # --central (optional) drops control packets that do not come from the central server
   bash /opt/src/T5DROnline/lobby/deploy/linux/install.sh --relay-only --relay-id usw \
        --central CENTRAL-IP --firewall ufw
   ```

   (Instead of `scp`: `apt -y install git && git clone --depth 1
   https://github.com/TheWishin/T5DROnline-Source /opt/src/T5DROnline` -- the public source mirror.)

   The script creates the `t5lobby` user, copies the code to `/opt/t5lobby`, writes
   `/etc/t5lobby/t5lobby.env` with `T5L_RELAY_SECRET_FILE`, `T5L_RELAY_ID` (and
   `T5L_RELAY_CENTRAL`), makes the secret `/etc/t5lobby/relay.secret` (mode 0640; an existing one is
   kept), opens SSH and UDP 7781 in ufw, and installs, starts and health-checks the systemd service
   `t5lobby` running `python3 -m t5lobby.server.relaynode`. At the end it prints the entry for the
   central server's `relays.json`. `--dry-run` shows every step first.
4. **Check the node**: `sudo t5lobby-admin status` shows `relay node usw`, `0/100 sessions` and
   `central   last request never` (until step 6).
5. **Central server, the first time only**: add the setting, then update the central server to
   this version as usual and restart it once, after a drain:

   ```sh
   # central
   echo 'T5L_RELAYS=/etc/t5lobby/relays.json' | sudo tee -a /etc/t5lobby/t5lobby.env
   sudo t5lobby-admin drain --wait 600
   # ... copy the new lobby/ code as for every update (install.sh with its usual options restarts
   # the service itself), or else:
   sudo systemctl restart t5lobby
   ```

   (A restart drops everybody for a few seconds and voids running matches -- hence the drain.
   Until step 6 the log says once that `relays.json` is missing; that is expected. Adding,
   changing or removing nodes later needs no restart.)
6. **Give the central server the node's secret and entry.** From a PC with SSH access to both
   (the secret never shows on screen and stays out of the shell history):

   ```sh
   # PC
   ssh root@NODE-IP cat /etc/t5lobby/relay.secret | \
     ssh root@CENTRAL-IP 'umask 027; cat > /etc/t5lobby/relay-usw.secret; chgrp t5lobby /etc/t5lobby/relay-usw.secret'
   ```

   From a phone: `sudo cat /etc/t5lobby/relay.secret` on the node, copy the line; on the central
   server `sudo sh -c 'umask 027; cat > /etc/t5lobby/relay-usw.secret'`, paste, Enter, Ctrl+D, then
   `sudo chgrp t5lobby /etc/t5lobby/relay-usw.secret`.

   Then, on the central server, `sudo nano /etc/t5lobby/relays.json` (the entry install.sh printed;
   `name` is what players see: "Relay (Oregon (US West))"):

   ```json
   {
     "format": "t5dr-relays/1",
     "relays": [
       {"id": "usw", "name": "Oregon (US West)", "host": "NODE-IP", "port": 7781,
        "secret_file": "relay-usw.secret"}
     ]
   }
   ```

   and `sudo chgrp t5lobby /etc/t5lobby/relays.json && sudo chmod 0640 /etc/t5lobby/relays.json`.
   The central server reads it within 5 seconds. A broken file is refused with a line in the log and
   in `status`; the last good list stays in use.
7. **Check it**: on the central server `sudo t5lobby-admin status` shows

   ```
   relay usw   Oregon (US West): up, 0/100 sessions, 0 kbit/s, last seen 2 s ago (control round trip 150 ms)
   ```

   and on the node `central   last request 3 s ago`. The log (`journalctl -u t5lobby`) says why each
   relayed match went where: `match m...: relay usw (punch failed; sum of round trips: usw 52 ms,
   main 304 ms)`. A second node is the same steps with another `--relay-id`, another secret file and
   another entry in `relays`.

### Running relay nodes

- **Status line per node** (`t5lobby-admin status` on the central server): up / DOWN (and why,
  e.g. `clock`), sessions open of the node's maximum, relay kbit/s over the last minute, when it
  last answered, the control channel's round trip, failed session requests. The same numbers are
  in `/status` (`"relays"`) and `/metrics` (`t5lobby_relay_node_up{relay="usw"}`,
  `t5lobby_relay_node_sessions`, `t5lobby_relay_node_kbit_per_second`,
  `t5lobby_relay_node_last_seen_seconds`); the 15-minute status line in the log has one line per
  node. On a node, `t5lobby-admin status` / `health` and `http://127.0.0.1:7780/` work as on the
  central server (`t5relay_*` metrics).
- **Maintenance**: set `"enabled": false` on the node's entry. New matches stop going there; running
  ones finish. When its status shows 0 sessions, update it (`scp` the new `lobby/`, run
  `install.sh --relay-only --relay-id usw ...` again: settings and secret are kept), then enable it
  again. A node restart ends the matches relayed by it, like a central restart does for its own.
- **A node that dies**: the central server marks it DOWN after 20 s without an answer (at once if a
  session request goes unanswered) and logs `relay usw (...) is down`; matches take the next best
  relay, at worst the central one. When it answers again: `is up`, and it is used again.
- **Limits on a node** are the central relay's settings in its `/etc/t5lobby/t5lobby.env`:
  `T5L_RELAY_KBPS`, `T5L_RELAY_PPS`, `T5L_MAX_RELAYS`, `T5L_MAX_RELAYS_PER_IP`,
  `T5L_RELAY_MAX_BYTES`, `T5L_RELAY_MAX_SECONDS`; a full node refuses the session and the match
  takes the next relay.
- **A new secret** (a copy leaked): `sudo rm /etc/t5lobby/relay.secret` and run install.sh again on
  the node (it makes a new one), copy it to the central server as in step 6. Until both have the
  new one the node shows DOWN.
- **The central server's own relay** stays a candidate. `T5L_RELAY=0` takes it out of the choice
  (then only nodes relay, and a pair with an older launcher cannot be relayed).

## Operations

### Admin tool

`sudo t5lobby-admin ...` on a systemd install (a wrapper that loads `/etc/t5lobby/t5lobby.env`
and runs as the service user). Elsewhere, use `docker compose exec lobby t5lobby-admin ...`,
`python lobby/run.py admin ...`, or `python -m t5lobby.server.admin --db FILE ...`. It works on
the SQLite file directly, which is safe while the server runs. The server polls for bans every
5 s and kicks the player.

| Command | |
|---|---|
| `status [--json]` | players online (guests/accounts/playing/searching), rooms, queues, matches running and in the last 24 h by path, relay sessions and kbit/s, one line per regional relay node (up/down, sessions, kbit/s, last answer), accounts, bans, certificate expiry, CPU/RSS. On a relay node: its sessions, kbit/s and the central server's last request |
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
| `drain [--wait SECONDS] [--off]` | before a restart: no new matches (queues, rooms, challenges, rematches are refused with "the server restarts for an update in a moment"), the running ones and the ranked sets finish. `--wait` returns 0 when none is left (1 on timeout). A restart ends the drain. See Updates and restarts |
| `release [X.Y.Z] [--clear]` | after the owner has published a release: launchers that report an older one see "T5DR Online X.Y.Z is out ... update the launcher" in their status bar (now and at every login) until `--clear`. Without an argument: what is set |
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

### Updates and restarts

A restart drops every lobby connection; the server forgets who was online, so the launchers cannot resume
their sessions. Launchers from 1.1.2 on log in again by themselves with a remembered login (a few seconds after the
server is back; guests and accounts without one log in again by hand). Launchers up to 1.1.1 show "Lost the lobby
connection": the player logs in again by hand (with the password) or restarts the launcher, which uses the
remembered login. A match that was running cannot be reported any more: the server marks it **void
(`server_restart`)** when it starts again -- no rating change, no blame for anybody -- and so is a ranked set that
was not finished (its games changed no rating yet). To restart without voiding anything:

    sudo t5lobby-admin drain --wait 600 && sudo systemctl restart t5lobby

`drain` stops new matches at once (players get a notice), `--wait` returns when the last running
match has its result (a first-to-3 match takes 2-7 minutes) and the last ranked set is over. A ranked set goes on
during a drain: its next game starts by itself, so a best-of-3 can take up to three games. (Before 1.1.2 the admin
tool did not wait for a set between two of its games, when no match runs; with an older server, check as in
docs/DEPLOY_1.1.2.md step C3.) The restart ends the drain.

**Database upgrades.** A new release may add tables: the server does it by itself at its first start (numbered
schema migrations, `PRAGMA user_version`; 1.1.2 adds the friends tables). Each step is one transaction together with
its version number, so a crash in the middle leaves the old version and the step runs again. Take a backup before
an update all the same (`t5lobby-admin backup`). Going back to the previous release after an upgrade works: an older
server leaves the tables it does not know alone. (An account the older server deletes keeps its friends rows; the
newer server drops them, and those of an account whose id SQLite gave to a newer account, when it starts again.)

**After a release is published**, `sudo t5lobby-admin release 1.1.2` (the new version) tells every launcher that
reports an older release, in its status bar, that the new version is out and that players on it cannot play against
it (different builds are never paired). Only after the owner has published the release; `release --clear` ends it.

What a crash (or `kill -9`, or a power cut) can and cannot do to the data:

- **Database**: everything the server writes while handling one message or timer -- for a ranked
  result both ratings, both records and the match row -- is one SQLite transaction, committed
  before any reply about it leaves the server (`synchronous=FULL`, WAL). A crash loses at most the
  last such step, never half of it. (Before, each statement committed alone; in a test that kills
  a writer at random moments, 6 of 12 kills left one player's rating changed without the match.)
- **Matches running at the crash**: void (`server_restart`) on the next start, as above.
- **TLS key and certificate, `host.json`**: written to a temporary file, flushed to disk, then
  renamed over the old one -- old or new, never a truncated file. Half a pair (a crash between
  the two files on the very first start) is noticed and made again; a working pair is never
  replaced.
- **Backups**: written as `*.part`, flushed, then renamed; a leftover `.part` from an interrupted
  backup is removed by the next one. The WAL file is folded back into the database every hour,
  and expired remembered logins are deleted then.

## Abuse protection: defaults for a public server

All limits are per server process, in memory, and need no configuration. The table lists the
built-in defaults and what `deploy/t5lobby.env.example` (the file install.sh installs) uses for
a public server.

| Limit | Built-in | Public profile | Why |
|---|---|---|---|
| Concurrent connections | 500 (`T5L_MAX_CLIENTS`) | 500 | ~35 MB RAM at this size. The admin tool shows how close you are |
| Connections per address | 8 (`T5L_MAX_PER_IP`) | 8 | Mobile carriers put many players behind one address (CGNAT). 8 is a compromise. Raise it for LAN events. An IPv6 address counts as its /64 (`T5L_IPV6_PREFIX`) here and in every other per-address limit: one subscriber usually has a whole /64 |
| New connections per address | 0.5/s, burst 10 (`T5L_CONN_RATE`, `T5L_CONN_BURST`) | same | Also limited by nftables (20/s) when you use `--firewall nft` |
| Connections not logged in yet | 100 in all (`T5L_MAX_PRELOGIN`) | same | A flood of connections that never log in is refused ("server busy") before it crowds out players |
| TLS handshake | starts only after the address checks, 10 s to finish (`T5L_TLS_HANDSHAKE_TIMEOUT`) | same | Before, every connection got an uncounted 60 s handshake: a slowloris could hold any number of sockets. (Python 3.11+; on 3.10 only the 10 s timeout applies) |
| Messages per connection | 20/s, burst 40. After 10 strikes, a 60 s address ban | same | |
| Expensive requests per connection | leaderboard, profile, history, whole lobby list: 1/s, burst 10 (`T5L_HEAVY_RATE`, `_BURST`). Queue, rooms, character, ping and other changes everybody's lobby list shows: 2/s, burst 20 (`T5L_STATE_RATE`, `_BURST`) | same | Each costs the server (database scans, an update to every player) far more than the client |
| Unread output per connection | 1 MB (`T5L_MAX_PENDING_KB`) | same | A client that stops reading is dropped at once (the connection is aborted; a graceful close waited for the peer to read, for ever) |
| Login | 15 s to finish. 5 wrong passwords per address and per name, then 1/min; attempts count before the check, so parallel guesses on many connections cannot get past it. An address the account logged in from before is not held back by the name's limit (someone else guessing cannot lock the owner out). 3 new accounts per address, then 1 per 10 min | same | |
| Password hashing | 2 at once, 64 waiting (`T5L_PW_CONCURRENCY`, `T5L_PW_QUEUE`); more: "the server is busy, try again". Password changes and new recovery codes: 3 per account, then one per 20 s, right or wrong (1.1.2) | same | scrypt costs ~16 MB and tens of ms each: a login flood from many addresses cannot pile up memory and CPU, and one logged-in account cannot keep the hashing busy for everybody |
| Names | 2–16 safe characters. Reserved names refused (`admin…`, `moderator…`, `official…`, `t5lobby…`, `system`, `server`, `p1`, ... ignoring case, punctuation, look-alike letters and digits for letters: `Adm1n`, `M0derat0r`, `5ystem`; see RANKED.md), plus any name containing a word from `T5L_NAME_BLOCKLIST`. A new name (guest or account) must not look like an account or a player online: `W1shin`, `WIshin`, `Wish.in` next to `Wishin` are refused | add a word file | Impersonation, offensive names |
| Text from clients | printable characters only (no control or direction-changing characters), at most 2 combining marks in a row; a character that cannot be sent becomes `?` | same | One unsendable character in a client's build name used to stop the lobby list for everybody |
| Chat | 1 line/s per player (burst 5), 2/s per address, **20/s for the whole lobby** (`T5L_CHAT_TOTAL_RATE`), 200 characters | same | Every line goes to every player |
| UDP control packets | 100/s per address **and 5000/s in total for pings** (`T5L_UDP_CTL_PPS`) | same | The total stops spoofed-source ping floods from being reflected at many victims. Answers are never larger than requests. Registrations and relay binds are answered only for a token the server handed out, so they do not count against the total: a flood that uses it up cannot stop the players' NAT setup (1.1.2) |
| Relay per player | 512 kbit/s, 400 packets/s | **256 kbit/s, 240 packets/s** | The game needs ~85 kbit/s at ~60 packets/s. 3–4× headroom, and the relay can't be used as a traffic cannon |
| What the relay carries | the game's own packets (`T5NP`) and the lobby's peer packets, at most 2048 bytes (`T5L_RELAY_MAX_BYTES`); everything else is dropped | same | Two accounts can always force the relay: it must not be a free tunnel or proxy |
| Relay sessions | 100 (`T5L_MAX_RELAYS`), 3 per address (`T5L_MAX_RELAYS_PER_IP`), closed when their match has run 20 min (`T5L_RELAY_MAX_SECONDS`; no match takes that long) | 100 | ~17 Mbit/s each way at the game's rate. A 2-vCPU VPS handles that. Without the per-address and time limits a few addresses could hold every slot for hours |
| Ranked between accounts on one address | never paired by the ranked queue; a ranked room or rematch between them is unranked (`T5L_RANKED_SAME_IP=1` allows it) | same | One player's alts feeding each other wins |
| Accounts on a server without TLS | the server warns in its log; the launcher refuses to send a password to it unless it is on the player's own network | install.sh turns accounts off with `--no-tls` | Passwords would cross the network in clear |
| Bans | `t5lobby-admin ban / ban-ip`. Take effect within 5 s | | |

Not handled (and how to cope): results are self-reported, so two colluding accounts on different
addresses can still trade wins within `T5L_PAIR_CAP` a day (RANKED.md "Results and match integrity"
lists what the server does decide from evidence: desync claims, early and withheld reports,
disconnect reports, repeat disputers). Every match's reports, path and RTT are in the database,
and you can use `matches` and `user`, then `reset-rating` and `ban`. There is no captcha or e-mail verification on account
creation. To clean up, use `purge-inactive`. A determined attacker with many addresses can
still fill the lobby. Lower `T5L_MAX_CLIENTS` keeps the server itself healthy, and the
provider's DDoS filtering handles volumetric floods.

## Firewall rules

Inbound, to the lobby server:

| Port | Proto | What | Needed |
|---|---|---|---|
| 7781 | TCP | control channel (TLS) | always |
| 7781 | UDP | ping, registration, relay | always |
| 7782 | UDP | NAT type probe | recommended: without it symmetric NATs are found only by failed punching and their next ports are never predicted (`T5L_UDP_PORT2=0` turns it off) |
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
- **A relay-only node** (`install.sh --relay-only`): only UDP 7781 (and SSH) inbound;
  `--firewall nft` installs `lobby/deploy/linux/nftables-t5relay.conf`. The central server needs no
  new inbound port for its nodes. See "Adding a relay server".
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

| | Typical (direct where possible: ~10–20% of matches need the relay) | Worst case (every match relayed, everybody in a match) |
|---|---|---|
| CPU | ~0.1 vCPU | ~0.3 fast core ≈ 0.6–0.9 VPS vCPU |
| RAM | ~35 MB | ~35 MB |
| Bandwidth out | ~2.5 Mbit/s lobby + ~1–2 Mbit/s relay | ~2.5 lobby + 8.6 relay ≈ 11 Mbit/s (8.6 in) |
| Traffic per month, if 100 players were online 24/7 | ~1.2 TB | ~3.6 TB out, 2.8 TB in |

A 2 vCPU / 2–4 GB VPS with 20 TB of traffic therefore holds several hundred players and the
default 100 relay sessions with room to spare. Real-world averages are far lower than "100
online all month". Over the internet, the relay's cost to players is the detour through the
server's location. Its processing adds 0.1–0.4 ms (ONLINE.md).

**Soak and abuse (2026-10-19, `lobby/tools/soak_test.py`, `lobby/tools/login_flood.py`).** The
server pinned to two CPUs (a 2 vCPU VPS), file database, backups every 6 minutes, the same
desktop as above (multiply CPU by 2–3 for a VPS). 200 simulated players for 35 minutes, ~176
online at a time: accounts and guests, quick and ranked queue, rooms, ready checks, NAT steps,
matches of 35–90 s with both results reported, rematches, a quarter of the matches through the
relay at the game's packet rate, chat, leaderboard and profiles -- and among them players who
lose the lobby mid-match and come back (8%), stop reading their socket for minutes (3%), send
malformed lines (3%), lines over the size limit (2%), floods (1%) or log in and out again and again
(3%). "Before" is main at 3dba465, "after" this hardening:

| | before | after |
|---|---|---|
| CPU, mean / p95 / max (of one core) | 10.9% / 13.8% / 15.8% | 11.6% / 15.4% / 18.4% |
| Memory (working set) after warm-up -> end, trend | 38.5 -> 45.2 MB, +8.8 MB/h | 39.1 -> 44.8 MB, +8.5 MB/h -- a warm-up, not a leak: in two 60-minute runs (with and without backups) it stays at 42–45 MB from minute 15 to the end (max 46.8 MB), and `--memtrace` snapshots show the Python heap flat (8.7 -> 6.9 MB between minutes 6 and 15) |
| Threads (max), handles | 10, 355–363 | 8, 346–356 |
| Response time (ping), p50 / p99 / p99.9 / max | 1.2 / 19.7 / 60 / 945 ms | 1.2 / 18.2 / 37 / 66 ms |
| Matches started, relay delivery | 2198, 99.94% | 2374, 99.96% |

Under a **login flood** (150 addresses sending wrong passwords for 20 real accounts as fast as
the answers come, 60 s, 20 honest players pinging):

| | before | after |
|---|---|---|
| Peak memory | **480 MB** working set (564 MB private: the systemd unit's `MemoryMax=512M` would kill the server) | 66 MB |
| Peak threads | 37 | 10 |
| Password checks run (limit: 5 per name) | 200 (parallel guesses got past the limit) | 100 |
| Honest players' ping, p50 / p99 | 0.8 / 5473 ms | 0.9 / 96 ms |

Every scrypt hash costs ~16 MB while it runs; before, nothing bounded how many ran at once.

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
4. **Relay every match (privacy) or direct**: direct is faster and cheaper, but players see each
   other's IP address. Relaying every match hides it at ~170 kbit/s per match.
5. **Who moderates**: who gets SSH and `t5lobby-admin`, and where players report cheaters (the MOTD).
6. **Builds**: whether to pin accepted builds (`T5L_BUILDS`) per release, or pair any equal builds.
7. **Regional relays**: where players live far from the lobby server, a small relay-only server
   near them (see "Adding a relay server") cuts their relayed matches' ping to a fraction, for the
   price of another VPS. Lobby and ranking stay on one server.

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
  `--self-signed/--firewall nft/--relay-only` (since 1.1.1: `--force-relay`) prints the expected
  steps. **`install.sh --root DIR --self-signed --relay-only`** (now `--force-relay`; a real staged install) produced the right layout, certificate,
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

Regional relays (branch regional-relays, 2026-10-19): `lobby/tests/test_relays.py` (control channel,
relays.json, the node's limits, the choice, a dead / silent / full node, the list pushed to clients,
the direct upgrade from a regional relay, a rematch in the running games renewing the node's lease,
admin lines, the 1.1.0 client and server from git) and `lobby/tools/relay_e2e.py` (central server and
two nodes as processes, players behind UDP delay proxies, stub games: the relay with the smallest
sum carries the match, a killed node is skipped, a 1.1.0 client gets the central relay). With two real
games (`--exe`, main's t5dr.exe) the match went through the node with the smallest sum (round trip
136 ms for a simulated 120), both relay bridges carried it: 4,270 frames, 0 mismatching, 18,329
packets through the node, result confirmed.
`install.sh --root DIR --relay-only --relay-id usw` (a staged install) was then run with the settings
it wrote and answered a control request signed with the secret it made. Not verified: a real node
on Hetzner and real round trips across the Atlantic.

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
