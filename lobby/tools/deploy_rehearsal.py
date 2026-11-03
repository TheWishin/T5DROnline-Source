"""Local rehearsal of a central-server lobby update (docs/DEPLOY_1.2.0.md), on 127.0.0.1 only.

    python lobby/tools/deploy_rehearsal.py --work D:/t5dr-reh --t4-repo <T4 lobby repository> \\
        [--old-ref v1.1.9] [--new-ref HEAD] [--new-version 1.2.0] [--t4-ref t4-server-beta]

Builds the central machine's layout in a staging folder (install.sh --root, the real admin wrappers, stand-ins for
systemctl / journalctl / ssh / scp that run the servers as local processes at below-normal priority) as it is today:
the OLD T5DR lobby (git archive of --old-ref) on a database made by that code (lobby_test_db.py: made-up players
only) and the T4 lobby (git archive of --t4-ref) sharing its accounts. Then the update exactly as on the server,
through tools/deploy_lobby.sh and lobby/deploy/linux/t5dr_deploy_remote.sh: upload, check, precheck, notice, a deploy
of a broken copy (must roll back by itself), the deploy while an old launcher and a T4 client stay connected, the
checks with old and new launchers, `admin release` (old launchers are told to update), rollback to the old code
(database kept), the deploy again, verify. Nothing leaves 127.0.0.1 (the servers get an unreachable HTTPS proxy, so
the 1.2.0 release lookup cannot reach GitHub). Exit 0 = every check passed. Runs about 3-5 minutes.

Internal sub-commands (used by the stand-ins): `stub ROOT systemctl|journalctl ARGS`, `client ...`.
"""
import argparse
import ctypes
import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)
REPO = os.path.dirname(LOBBY)
CHECKS = []
BELOW_NORMAL = 0x4000
NO_NET = {"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "NO_PROXY": "127.0.0.1,localhost"}


def check(what, ok, detail=""):
    CHECKS.append((what, bool(ok)))
    print(("PASS " if ok else "FAIL ") + what + (f"  ({detail})" if detail else ""), flush=True)
    return bool(ok)


def git_bash():
    for p in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if os.path.exists(p):
            return p
    return shutil.which("bash")


def posix(path):
    path = os.path.abspath(path).replace("\\", "/")
    if os.name == "nt" and len(path) > 1 and path[1] == ":":
        return "/" + path[0].lower() + path[2:]
    return path


def free_port(kind=socket.SOCK_STREAM):
    s = socket.socket(socket.AF_INET, kind)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ============================================================================ stand-ins for systemd (sub-command)
def _alive(pid):
    if not pid:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000 | 0x100000, False, pid)        # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
    if not h:
        return False
    try:
        return k.WaitForSingleObject(h, 0) == 0x102          # WAIT_TIMEOUT: still running
    finally:
        k.CloseHandle(h)


def _env_file(path):
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return out


class Stub:
    def __init__(self, root):
        self.root = root
        with open(os.path.join(root, "stub", "services.json"), encoding="utf-8") as f:
            self.services = json.load(f)

    def _pidfile(self, name):
        return os.path.join(self.root, "stub", name + ".pid")

    def pid(self, name):
        try:
            with open(self._pidfile(name)) as f:
                pid = int(f.read().strip() or 0)
        except (OSError, ValueError):
            return 0
        return pid if _alive(pid) else 0

    def start(self, name):
        if self.pid(name):
            return 0
        s = self.services[name]
        if not os.path.exists(s["unit"]):
            print(f"Unit {name}.service not found.", file=sys.stderr)
            return 5
        env = {k: v for k, v in os.environ.items() if not k.startswith("T5L_")}
        env.update(_env_file(s["envfile"]))
        env.update(s["env"])
        env.update(NO_NET)
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
        log = open(s["log"], "ab")
        log.write(f"-- {datetime.datetime.now():%Y-%m-%d %H:%M:%S} stub: starting {name}\n".encode())
        log.flush()
        flags = (subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008 | BELOW_NORMAL) if os.name == "nt" else 0
        p = subprocess.Popen([sys.executable, "-m", s["module"]], cwd=s["cwd"], env=env, stdout=log,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
        with open(self._pidfile(name), "w") as f:
            f.write(str(p.pid))
        time.sleep(0.5)
        return 0

    def stop(self, name):
        pid = self.pid(name)
        if pid:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, 15)
            end = time.time() + 15
            while _alive(pid) and time.time() < end:
                time.sleep(0.1)
            with open(self.services[name]["log"], "ab") as log:
                log.write(f"-- {datetime.datetime.now():%Y-%m-%d %H:%M:%S} stub: stopped {name}\n".encode())
        try:
            os.remove(self._pidfile(name))
        except OSError:
            pass
        return 0

    def systemctl(self, args):
        args = [a for a in args if a not in ("--quiet", "-q", "--no-pager")]
        if not args:
            return 1
        cmd, rest = args[0], args[1:]
        if cmd in ("daemon-reload", "enable"):
            return 0
        if cmd == "disable":
            names = [a for a in rest if not a.startswith("-")]
            if "--now" in rest:
                for n in names:
                    self.stop(n.replace(".service", ""))
            return 0
        if cmd == "show":
            name = rest[-1].replace(".service", "")
            if "MainPID" in rest:
                print(self.pid(name))
            elif "ActiveEnterTimestamp" in rest:
                print("")
            return 0
        names = [a.replace(".service", "") for a in rest]
        for n in names:
            if n not in self.services:
                print(f"Unit {n}.service not found.", file=sys.stderr)
                return 4 if cmd == "is-active" else 5
        if cmd == "is-active":
            return 0 if all(self.pid(n) for n in names) else 3
        if cmd == "start":
            return max(self.start(n) for n in names)
        if cmd == "stop":
            return max(self.stop(n) for n in names)
        if cmd == "restart":
            for n in names:
                self.stop(n)
            return max(self.start(n) for n in names)
        print(f"stub systemctl: {cmd} not handled", file=sys.stderr)
        return 1

    def journalctl(self, args):
        name, since = None, ""
        i = 0
        while i < len(args):
            if args[i] == "-u":
                name = args[i + 1].replace(".service", "")
                i += 1
            elif args[i] == "--since":
                since = args[i + 1]
                i += 1
            i += 1
        if name not in self.services:
            return 1
        keep = not since
        try:
            with open(self.services[name]["log"], encoding="utf-8", errors="replace") as f:
                for line in f:
                    head = line[3:22] if line.startswith("-- ") else line[:19]
                    if len(head) == 19 and head[4] == "-" and head[13] == ":":
                        keep = head >= since
                    if keep:
                        sys.stdout.write(line.rstrip("\r\n") + "\n")
        except FileNotFoundError:
            pass
        return 0


def stub_main(argv):
    root, tool, args = argv[0], argv[1], argv[2:]
    st = Stub(root)
    return getattr(st, tool)(args)


# ============================================================================ launcher clients (sub-command)
def client_main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lobby", required=True)
    ap.add_argument("--kind", default="t5")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--fp", required=True)
    ap.add_argument("--release", default="dev")
    ap.add_argument("--ops", required=True, help="JSON list of operations")
    ap.add_argument("--out", help="JSON lines of what happened (hold)")
    a = ap.parse_args(argv)
    sys.path.insert(0, a.lobby)
    pkg = "t4lobby" if a.kind == "t4" else "t5lobby"
    client_mod = __import__(pkg + ".client", fromlist=["LobbyClient"])
    build_mod = __import__(pkg + ".buildid", fromlist=["BuildInfo"])
    proto = __import__(pkg + ".proto", fromlist=["LobbyError"])
    build = build_mod.BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "rehearsal" + a.release, a.release)
    res = {"ok": True, "steps": []}

    def new():
        c = client_mod.LobbyClient(f"127.0.0.1:{a.port}", build, tls=True, tls_fingerprint=a.fp, relay_bridge=False)
        c.connect()
        return c

    c = None
    token = None
    try:
        for op in json.loads(a.ops):
            kind = op[0]
            if kind in ("login", "register"):
                c = c or new()
                getattr(c, kind)(op[1], op[2], remember=True)
                token = c.session
                res["steps"].append([kind, op[1], (c.me or {}).get("name"), bool(token)])
            elif kind == "token":
                c = c or new()
                c.login_session(op[1])
                token = op[1]
                res["steps"].append(["token", (c.me or {}).get("name")])
            elif kind == "welcome":
                w = dict(c.welcome or {})
                res["steps"].append(["welcome", {k: w.get(k) for k in ("server", "proto", "features", "latest_release")}])
            elif kind == "chat":
                c.chat(op[1])
                ev = c.next_event(5, types={"chat", "error"})
                res["steps"].append(["chat", (ev or {}).get("t"), (ev or {}).get("text") or (ev or {}).get("msg")])
            elif kind == "chat_term":          # a term of the server's list (never printed): must be refused
                with open(op[1], encoding="utf-8-sig") as f:
                    term = json.load(f)["terms"][0]["term"]
                c.chat(f"rehearsal {term} rehearsal")
                ev = c.next_event(5, types={"chat", "error"})
                res["steps"].append(["chat_term", (ev or {}).get("t"), "blocked" in str((ev or {}).get("msg", ""))])
            elif kind == "notices":
                time.sleep(op[1] if len(op) > 1 else 0)
                c.refresh() if hasattr(c, "refresh") else None
                time.sleep(0.5)
                res["steps"].append(["notices", c.active_notices()])
            elif kind == "lobby":
                time.sleep(1.0)
                res["steps"].append(["lobby", sorted(p.get("name", "") for p in (c.players or []))
                                     if hasattr(c, "players") else None])
            elif kind == "hold":               # stay connected op[1] s; a lost connection is resumed with the token
                end = time.time() + op[1]
                out = open(a.out, "a", encoding="utf-8")
                seen = set()
                while time.time() < end:
                    ev = c.next_event(1.0)
                    for n in c.active_notices():
                        if n not in seen:
                            seen.add(n)
                            out.write(json.dumps({"time": time.time(), "notice": n}) + "\n")
                    if ev is None:
                        continue
                    if ev["t"] in ("reconnecting", "reconnected", "disconnected", "server_notice", "notice", "kicked"):
                        out.write(json.dumps({"time": time.time(), "event": ev["t"],
                                              "text": ev.get("text") or ev.get("msg") or ev.get("reason")}) + "\n")
                        out.flush()
                    if ev["t"] in ("disconnected", "kicked"):
                        try:
                            c.close()
                        except Exception:  # noqa: BLE001
                            pass
                        c = None
                        while c is None and time.time() < end:
                            try:
                                c = new()
                                c.login_session(token)
                                out.write(json.dumps({"time": time.time(), "event": "logged_in_again",
                                                      "name": (c.me or {}).get("name"),
                                                      "latest_release": (c.welcome or {}).get("latest_release")})
                                          + "\n")
                                out.flush()
                            except (OSError, proto.LobbyError) as e:
                                if c is not None:
                                    try:
                                        c.close()
                                    except Exception:  # noqa: BLE001
                                        pass
                                c = None
                                out.write(json.dumps({"time": time.time(), "event": "retry", "error": str(e)}) + "\n")
                                out.flush()
                                time.sleep(2)
                out.write(json.dumps({"time": time.time(), "event": "end", "connected": c is not None,
                                      "notices": c.active_notices() if c else []}) + "\n")
                out.close()
                res["steps"].append(["hold", c is not None])
            else:
                raise SystemExit(f"unknown op {kind}")
    except proto.LobbyError as e:
        res["ok"] = False
        res["error"] = f"{getattr(e, 'code', '')}: {e}"
    finally:
        if c is not None:
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
    print(json.dumps(res))
    return 0


# ============================================================================ the rehearsal
class Rehearsal:
    def __init__(self, a):
        self.a = a
        self.work = os.path.abspath(a.work)
        self.R = os.path.join(self.work, "root")
        self.bash = git_bash()
        self.holds = []
        self.p5, self.u5, self.s5 = free_port(), free_port(socket.SOCK_DGRAM), free_port()
        self.p4, self.u4, self.s4 = free_port(), free_port(socket.SOCK_DGRAM), free_port()

    # --------------------------------------------------------------------------- helpers
    def r(self, *parts):
        return os.path.join(self.R, *parts)

    def sh(self, script, env=None, timeout=900, quiet=False):
        """A bash command line with the stand-ins first on PATH. -> (exit code, output)."""
        e = dict(os.environ, **NO_NET)
        e.update(env or {})
        e["PYTHON"] = posix(sys.executable)
        cmd = f'export PATH="{posix(self.r("stub", "bin"))}:$PATH"; {script}'
        p = subprocess.run([self.bash, "-c", cmd], env=e, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        out = p.stdout + p.stderr
        with open(os.path.join(self.work, "rehearsal.log"), "a", encoding="utf-8") as f:
            f.write(f"\n$ {script}\n{out}\n[exit {p.returncode}]\n")
        if not quiet:
            for line in out.splitlines():
                print("   | " + line)
        return p.returncode, out

    def remote(self, version, step, *args, expect=0):
        """tools/deploy_lobby.sh VERSION STEP ... through the ssh/scp stand-ins (= on the "server")."""
        q = " ".join("'" + x.replace("'", "'\\''") + "'" for x in args)
        code, out = self.sh(f'bash "{posix(os.path.join(REPO, "tools", "deploy_lobby.sh"))}" {version} {step} {q}',
                            env={"T5D_SSH": posix(self.r("stub", "bin", "ssh")), "T5D_SCP": posix(self.r("stub", "bin", "scp"))})
        return code, out

    def admin(self, which, *args):
        q = " ".join("'" + x + "'" for x in args)
        return self.sh(f'"{posix(self.r("usr", "local", "bin", which))}" {q}', quiet=True)

    def archive(self, repo, ref, dest):
        os.makedirs(dest, exist_ok=True)
        tgz = os.path.join(self.work, "tmp.tar")
        subprocess.run(["git", "-C", repo, "-c", "core.autocrlf=false", "archive", "-o", tgz, ref, "lobby"], check=True)
        code, out = self.sh(f'tar -xf "{posix(tgz)}" -C "{posix(dest)}"', quiet=True)
        os.remove(tgz)
        if code:
            raise SystemExit(out)

    def client(self, version, ops, kind="t5", out=None, background=False):
        lobby = self.r("opt", "src", "t4lobby", "lobby") if kind == "t4" else self.src(version)
        port, fp = (self.p4, self.fp4) if kind == "t4" else (self.p5, self.fp5)
        cmd = [sys.executable, os.path.abspath(__file__), "client", "--lobby", lobby, "--kind", kind,
               "--port", str(port), "--fp", fp, "--release", version, "--ops", json.dumps(ops)]
        if out:
            cmd += ["--out", out]
        env = dict(os.environ, **NO_NET, PYTHONDONTWRITEBYTECODE="1")
        flags = BELOW_NORMAL if os.name == "nt" else 0
        if background:
            log = open(out + ".stderr", "w")
            return subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=log, text=True, creationflags=flags)
        p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120, creationflags=flags)
        try:
            res = json.loads(p.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            res = {"ok": False, "error": (p.stdout + p.stderr)[-600:]}
        res["traceback"] = "Traceback" in p.stderr
        return res

    def src(self, version):
        return self.r("opt", "src", f"t5dr-lobby-{version}", "lobby")

    def schema(self):
        import sqlite3
        db = sqlite3.connect(f"file:{self.r('var', 'lib', 't5lobby', 't5lobby.db')}?mode=ro", uri=True)
        try:
            return db.execute("PRAGMA user_version").fetchone()[0]
        finally:
            db.close()

    def installed_has(self, relpath):
        return os.path.exists(self.r("opt", "t5lobby", *relpath.split("/")))

    # --------------------------------------------------------------------------- the machine as it is today
    def setup(self):
        a = self.a
        if os.path.exists(self.work):
            self.stop_all()
            shutil.rmtree(self.work)
        os.makedirs(self.r("stub", "bin"))
        old, new = a.old_version, a.new_version
        print(f"== staging the central machine in {self.R}: T5DR {old} ({a.old_ref}) + T4 ({a.t4_ref})")
        self.archive(REPO, a.old_ref, os.path.dirname(self.src(old)))
        self.archive(a.t4_repo, a.t4_ref, self.r("opt", "src", "t4lobby"))
        stub = posix(os.path.abspath(__file__))
        py = posix(sys.executable)
        rr = self.R.replace("\\", "/")
        for tool in ("systemctl", "journalctl"):
            with open(self.r("stub", "bin", tool), "w", newline="\n") as f:
                f.write(f'#!/bin/sh\nexec "{py}" "{stub}" stub "{rr}" {tool} "$@"\n')
        # ssh root@host "command": the command runs here, with /opt/src etc. under the staging folder
        with open(self.r("stub", "bin", "ssh"), "w", newline="\n") as f:
            f.write('#!/bin/bash\nshift\ncmd="$*"\nR="' + posix(self.R) + '"\n'
                    'cmd="${cmd//\\/opt\\/src/$R/opt/src}"\n'
                    'T5D_ROOT="$R" exec bash -c "$cmd"\n')
        with open(self.r("stub", "bin", "scp"), "w", newline="\n") as f:
            f.write('#!/bin/bash\nsrc="$1"; dst="${2#*:}"\nmkdir -p "$(dirname "' + posix(self.R) + '$dst")"\n'
                    'cp "$src" "' + posix(self.R) + '$dst"\n')
        # T5DR as installed by its install.sh (staged), its env with local ports
        code, out = self.sh(f'bash "{posix(self.src(old))}/deploy/linux/install.sh" --root "{posix(self.R)}" --self-signed',
                            quiet=True)
        check(f"T5DR {old} staged by its own install.sh", code == 0, out.strip().splitlines()[-1] if out else "")
        with open(self.r("etc", "t5lobby", "t5lobby.env"), "a", encoding="utf-8", newline="\n") as f:
            f.write(f"\n# rehearsal: local ports\nT5L_HOST=127.0.0.1\nT5L_PORT={self.p5}\nT5L_UDP_PORT={self.u5}\n"
                    f"T5L_UDP_PORT2=0\nT5L_STATUS_PORT={self.s5}\nT5L_ADMIN_POLL=1\nT5L_CONN_RATE=50\n"
                    "T5L_MAX_PER_IP=64\nT5L_SCRYPT_N=4096\nT5L_RANKED_SAME_IP=1\n")
        # the database: made by the OLD code, made-up players only
        db = self.r("var", "lib", "t5lobby", "t5lobby.db")
        logins = os.path.join(self.work, "logins.json")
        subprocess.run([sys.executable, os.path.join(HERE, "lobby_test_db.py"), "make", "--lobby", self.src(old),
                        "--out", db, "--logins", logins, "--release", old, "--accounts", str(a.accounts)],
                       check=True, env=dict(os.environ, **NO_NET))
        with open(logins, encoding="utf-8") as f:
            self.logins = json.load(f)["logins"]
        unit5 = self.r("etc", "systemd", "system", "t5lobby.service")
        services = {
            "t5lobby": {"unit": unit5, "cwd": self.r("opt", "t5lobby"), "module": "t5lobby.server",
                        "envfile": self.r("etc", "t5lobby", "t5lobby.env"), "log": self.r("stub", "t5lobby.log"),
                        "env": {"T5L_DB": db, "T5L_BACKUP_DIR": self.r("var", "lib", "t5lobby", "backups")}},
            "t4lobby": {"unit": self.r("etc", "systemd", "system", "t4lobby.service"), "cwd": self.r("opt", "t4lobby"),
                        "module": "t4lobby.server", "envfile": self.r("etc", "t4lobby", "t4lobby.env"),
                        "log": self.r("stub", "t4lobby.log"),
                        "env": {"T5L_DB": self.r("var", "lib", "t4lobby", "t4lobby.db"),
                                "T5L_BACKUP_DIR": self.r("var", "lib", "t4lobby", "backups")}},
        }
        with open(self.r("stub", "services.json"), "w", encoding="utf-8") as f:
            json.dump(services, f, indent=1)
        self.sh("systemctl start t5lobby", quiet=True)
        ok = self.wait_health("t5lobby-admin")
        check(f"T5DR {old} running on its {self.schema()} schema database", ok and self.schema() >= 1)
        # T4 as its install.sh does it today: --shared-accounts T5DR's database
        code, out = self.sh(f'bash "{posix(self.r("opt", "src", "t4lobby", "lobby"))}/deploy/linux/install.sh" '
                            f'--root "{posix(self.R)}" --self-signed --shared-accounts /var/lib/t5lobby/t5lobby.db',
                            quiet=True)
        check("T4 staged by its own install.sh with --shared-accounts", code == 0,
              next((l for l in out.splitlines() if "T5DR database ok" in l), out.strip().splitlines()[-1] if out else ""))
        with open(self.r("etc", "t4lobby", "t4lobby.env"), "a", encoding="utf-8", newline="\n") as f:
            f.write(f"\n# rehearsal: local ports\nT5L_HOST=127.0.0.1\nT5L_PORT={self.p4}\nT5L_UDP_PORT={self.u4}\n"
                    f"T5L_UDP_PORT2=0\nT5L_STATUS_PORT={self.s4}\nT5L_ADMIN_POLL=1\nT5L_CONN_RATE=50\n"
                    "T5L_MAX_PER_IP=64\nT5L_SCRYPT_N=4096\n")
        self.sh("systemctl start t4lobby", quiet=True)
        check("T4 running, accounts shared with T5DR", self.wait_health("t4lobby-admin") and
              "accounts shared with T5DR" in open(services["t4lobby"]["log"], encoding="utf-8", errors="replace").read())
        sys.path.insert(0, self.src(old))
        from t5lobby.server.selfsigned import fingerprint
        self.fp5 = fingerprint(self.r("etc", "t5lobby", "tls", "cert.pem"))
        self.fp4 = fingerprint(self.r("etc", "t4lobby", "tls", "cert.pem"))
        sys.path.pop(0)

    def wait_health(self, admin, seconds=30):
        end = time.time() + seconds
        while time.time() < end:
            if self.admin(admin, "health", "-q")[0] == 0:
                return True
            time.sleep(1)
        return False

    def stop_all(self):
        try:
            st = Stub(self.R)
        except (OSError, ValueError):
            return
        for n in st.services:
            st.stop(n)

    # --------------------------------------------------------------------------- client checks
    def logins_work(self, when, version):
        """Accounts of the database in both games: password, remembered login; a launcher of `version`."""
        L = self.logins
        r = self.client(version, [["login", L[0]["name"], L[0]["password"]], ["welcome"]])
        check(f"{when}: a {version} launcher logs in with a password", r["ok"] and r["steps"][0][2] == L[0]["name"]
              and not r["traceback"], r.get("error", ""))
        r = self.client(version, [["token", L[1]["token"]]])
        check(f"{when}: a {version} launcher logs in with its remembered login", r["ok"] and r["steps"][0][1] == L[1]["name"],
              r.get("error", ""))
        t4 = self.client("t4", [["login", L[2]["name"], L[2]["password"]]], kind="t4")
        check(f"{when}: T4 logs in with the T5DR account's password", t4["ok"] and t4["steps"][0][2] == L[2]["name"],
              t4.get("error", ""))
        t4 = self.client("t4", [["token", L[3]["token"]]], kind="t4")
        check(f"{when}: T4 logs in with T5DR's remembered login", t4["ok"] and t4["steps"][0][1] == L[3]["name"],
              t4.get("error", ""))

    def hold(self, version, idx, seconds, tag):
        out = os.path.join(self.work, f"hold-{tag}.jsonl")
        if version == "t4":
            p = self.client("t4", [["token", self.logins[idx]["token"]], ["hold", seconds]], kind="t4", out=out,
                            background=True)
        else:
            p = self.client(version, [["token", self.logins[idx]["token"]], ["hold", seconds]], out=out, background=True)
        self.holds.append((p, out, tag))
        return out

    def hold_lines(self, out):
        try:
            with open(out, encoding="utf-8") as f:
                return [json.loads(l) for l in f if l.strip()]
        except FileNotFoundError:
            return []

    # --------------------------------------------------------------------------- the update
    def run(self):
        a = self.a
        old, new = a.old_version, a.new_version
        self.setup()
        self.logins_work(f"before ({old})", old)
        r = self.client(new, [["login", self.logins[4]["name"], self.logins[4]["password"]], ["welcome"]])
        check(f"before: a {new} launcher logs into the {old} server", r["ok"] and not r["traceback"], r.get("error", ""))

        print(f"\n== upload {new} ({a.new_ref}) with tools/deploy_lobby.sh")
        code, out = self.remote(new, "upload", a.new_ref)
        check("upload: archive copied, SHA-256 checked, unpacked into /opt/src/t5dr-lobby-" + new,
              code == 0 and "OK" in out and os.path.exists(os.path.join(self.src(new), "deploy", "linux",
                                                                         "t5dr_deploy_remote.sh")))
        code, out = self.remote(new, "upload", a.new_ref)
        check("upload again refused (the folder exists)", code != 0 and "exists already" in out)

        print("\n== check")
        code, out = self.remote(new, "check")
        check("check: read only, everything found", code == 0 and "check done" in out and "T4 shares T5DR" in out
              and f"running code = " in out and "chat filter list" in out)
        before = os.path.getmtime(self.r("var", "lib", "t5lobby", "t5lobby.db"))

        print("\n== precheck")
        code, out = self.remote(new, "precheck")
        check("precheck: new code migrated a copy, data unchanged, T4 accepts it, old code opens it",
              code == 0 and "data unchanged" in out and "T4 lobby accepts the migrated database" in out
              and "running (old) code opens the migrated copy" in out)
        check("precheck left the live database at its schema", self.schema() == 1)
        check("precheck removed its copies", not [f for f in os.listdir(self.r("root")) if any(
            x.endswith((".db", ".db-wal")) and x.startswith("precheck") for x in os.listdir(self.r("root", f)))])

        print("\n== a broken new code (the server cannot start): the deploy must put the old code back itself")
        broken = os.path.join(self.r("opt", "src"), f"t5dr-lobby-{new}-broken")
        shutil.copytree(os.path.dirname(self.src(new)), broken)
        with open(os.path.join(broken, "lobby", "t5lobby", "server", "__main__.py"), "a", encoding="utf-8") as f:
            f.write("\nraise SystemExit('rehearsal: a server that cannot start')\n")
        code, out = self.sh(f'bash "{posix(broken)}/lobby/deploy/linux/t5dr_deploy_remote.sh" deploy --drain-wait 60',
                            env={"T5D_ROOT": posix(self.R)})
        check("broken deploy: failed and rolled back by itself", code != 0 and "rolled back" in out
              and "old code running again, health ok" in out)
        check("broken deploy: the old code runs again, T4 runs", self.wait_health("t5lobby-admin")
              and self.wait_health("t4lobby-admin") and not self.installed_has("t5lobby/server/chatfilter.py"))
        self.logins_work("after the broken deploy", old)
        shutil.rmtree(broken)

        print("\n== notice")
        code, out = self.remote(new, "notice", "15", "Server update in 15 minutes: about 2 minutes.")
        check("notice sent in both lobbies", code == 0 and out.count("notice #") >= 2)

        print(f"\n== deploy (an old {old} launcher and a T4 client stay connected through it)")
        hold_old = self.hold(old, 5, a.hold_seconds, "old")
        hold_t4 = self.hold("t4", 6, a.hold_seconds, "t4")
        time.sleep(4)
        t0 = time.time()
        code, out = self.remote(new, "deploy", "--drain-wait", "60")
        took = time.time() - t0
        check(f"deploy: done in {took:.0f} s", code == 0 and "done: t5dr-lobby-" + new in out)
        check("deploy: the database migrated on the new server's start",
              "database upgraded to schema" in out and self.schema() >= 2, f"schema {self.schema()}")
        check("deploy: T4 stopped for the migration and started after it, shared, on the new schema",
              "stop t4lobby for the migration" in out and "T4 runs on T5DR's schema" in out)
        check("the new code is installed (chat filter list beside it)",
              self.installed_has("t5lobby/server/data/chat_filter_terms.json"))
        self.logins_work(f"after the deploy, {old} launchers", old)
        self.logins_work(f"after the deploy, {new} launchers", new)
        L = self.logins
        r = self.client(new, [["login", L[7]["name"], L[7]["password"]], ["chat", "hello after the update"],
                              ["chat_term", self.r("opt", "t5lobby", "t5lobby", "server", "data", "chat_filter_terms.json")]])
        check(f"{new}: chat delivered, a listed term refused by the server's filter",
              r["ok"] and r["steps"][1][1] == "chat" and r["steps"][2][1] == "error" and r["steps"][2][2],
              str(r.get("steps", r.get("error")))[:200])
        r = self.client(old, [["login", L[8]["name"], L[8]["password"]], ["chat", "hello from an old launcher"]])
        check(f"{old} launcher on the new server: chat works, no error in the old client",
              r["ok"] and r["steps"][1][1] == "chat" and not r["traceback"], str(r.get("steps", r.get("error")))[:200])
        made4 = self.client("t4", [["register", "RehT4Made", "t4-made-pw"]], kind="t4")
        made5 = self.client(new, [["login", "RehT4Made", "t4-made-pw"]])
        check("an account registered in T4 after the update logs into T5DR " + new,
              made4["ok"] and made5["ok"] and made5["steps"][0][2] == "RehT4Made", made4.get("error", "") + made5.get("error", ""))
        made5 = self.client(new, [["register", "Reh120Made", "t5-made-pw"]])
        made4 = self.client("t4", [["login", "Reh120Made", "t5-made-pw"]], kind="t4")
        check(f"an account registered in T5DR {new} logs into T4",
              made5["ok"] and made4["ok"] and made4["steps"][0][2] == "Reh120Made", made5.get("error", "") + made4.get("error", ""))
        code, out = self.admin("t5lobby-admin", "badge", L[9]["name"], "dev")
        check("admin badge works on the migrated database", code == 0, out.strip()[-120:])

        print(f"\n== `t5lobby-admin release {new}` (rehearsal only: on the server only after the owner published it)")
        self.admin("t5lobby-admin", "release", new)
        time.sleep(4)
        r_old = self.client(old, [["login", L[10]["name"], L[10]["password"]], ["notices", 3]])
        r_new = self.client(new, [["login", L[11]["name"], L[11]["password"]], ["notices", 3]])
        upd = f"T5DR Online {new} is out"
        check(f"a {old} launcher logging in is told to update, politely (a notice)",
              r_old["ok"] and any(upd in n for n in r_old["steps"][1][1]) and not r_old["traceback"],
              str(r_old["steps"][1][1] if r_old["ok"] else r_old.get("error"))[:160])
        check(f"a {new} launcher is not", r_new["ok"] and not any(upd in n for n in r_new["steps"][1][1]))
        print("   waiting for the connected clients to finish their hold ...")
        for p, out_f, tag in self.holds:
            try:
                p.wait(a.hold_seconds + 60)
            except subprocess.TimeoutExpired:
                p.kill()
        self.holds.clear()
        ev = self.hold_lines(hold_old)
        names = [e.get("event") for e in ev]
        notices = [e.get("notice") or e.get("text") or "" for e in ev]
        check(f"the connected {old} launcher saw the maintenance notice", any("Server update in 15" in n for n in notices))
        check(f"... lost the connection at the restart and was back on the new server",
              ("reconnected" in names or "logged_in_again" in names) and ev and ev[-1].get("connected"),
              ", ".join(n for n in names if n)[:200])
        check(f"... got the update notice while connected, no crash in the old client",
              any(upd in n for n in notices) and "Traceback" not in open(hold_old + ".stderr").read())
        ev4 = self.hold_lines(hold_t4)
        check("the connected T4 client was back after T4's restart", ev4 and ev4[-1].get("connected")
              and "Traceback" not in open(hold_t4 + ".stderr").read(),
              ", ".join(e.get("event", "") for e in ev4 if e.get("event"))[:200])
        self.admin("t5lobby-admin", "release", "--clear")

        print("\n== rollback (the old code; the database stays at the new schema)")
        code, out = self.remote(new, "rollback")
        check("rollback: done, old code healthy on the new schema", code == 0 and "rollback done" in out
              and self.schema() >= 2 and not self.installed_has("t5lobby/server/chatfilter.py"))
        self.logins_work(f"after the rollback, {old} launchers", old)
        r = self.client(new, [["login", "Reh120Made", "t5-made-pw"]])
        check(f"after the rollback: the account made under {new} still works", r["ok"], r.get("error", ""))

        print("\n== deploy again (from the rolled-back state), then verify")
        code, out = self.remote(new, "deploy", "--drain-wait", "60")
        check("deploy again: done, no migration needed", code == 0 and "done: t5dr-lobby-" + new in out
              and self.installed_has("t5lobby/server/chatfilter.py"))
        code, out = self.remote(new, "verify")
        check("verify: both lobbies healthy, T4 shared on the new schema", code == 0 and "verify done" in out)
        self.logins_work("final", new)
        import sqlite3
        db = sqlite3.connect(f"file:{self.r('var', 'lib', 't5lobby', 't5lobby.db')}?mode=ro", uri=True)
        integ = db.execute("PRAGMA integrity_check").fetchone()[0]
        n = db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        db.close()
        check("final database: integrity ok, every account still there", integ == "ok" and n >= a.accounts - 1, f"{n} accounts")
        backups = [d for d in os.listdir(self.r("root")) if d.startswith("t5dr-deploy-")]
        check("every deploy/rollback left its backup folder", len(backups) >= 4, ", ".join(sorted(backups))[:200])


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "stub":
        return stub_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "client":
        return client_main(sys.argv[2:])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True, help="a new folder for the staged machine (removed first)")
    ap.add_argument("--t4-repo", required=True, help="the T4 lobby repository (git)")
    ap.add_argument("--t4-ref", default="t4-server-beta")
    ap.add_argument("--old-ref", default="v1.1.9")
    ap.add_argument("--old-version", default="1.1.9")
    ap.add_argument("--new-ref", default="HEAD")
    ap.add_argument("--new-version", default="1.2.0")
    ap.add_argument("--accounts", type=int, default=1300)
    ap.add_argument("--hold-seconds", type=float, default=150)
    ap.add_argument("--keep", action="store_true", help="leave the staged machine (servers stopped)")
    a = ap.parse_args()
    reh = Rehearsal(a)
    try:
        reh.run()
    finally:
        for p, _out, _tag in reh.holds:
            p.kill()
        reh.stop_all()
    failed = [w for w, ok in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed" + (f"; failed: {failed}" if failed else ""))
    print("log:", os.path.join(reh.work, "rehearsal.log"))
    if not a.keep and not failed:
        shutil.rmtree(reh.work, ignore_errors=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
