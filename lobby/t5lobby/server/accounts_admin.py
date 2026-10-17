"""Account help for whoever runs the lobby server (there is no e-mail, by design).

    python -m t5lobby.server.accounts_admin [--db t5lobby.db] show NAME
    python -m t5lobby.server.accounts_admin reset-password NAME     # prints a one-time password
    python -m t5lobby.server.accounts_admin recovery-codes NAME     # prints a new set of codes
    python -m t5lobby.server.accounts_admin logout-all NAME         # ends every remembered login

Use it when a player lost both the password and the recovery codes and proves who they
are some other way (a friend group knows its players). The player then logs in with the
printed password and changes it in the launcher (Online tab -> Change password). Works
on the live database while the server runs (SQLite locking). The database defaults to
T5L_DB (or ./t5lobby.db). The server-hosting admin tool may take these commands over.
"""
import argparse
import os
import secrets
import sys
import time

from .store import Store, hash_password


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m t5lobby.server.accounts_admin", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("T5L_DB", "t5lobby.db"))
    ap.add_argument("command", choices=["show", "reset-password", "recovery-codes", "logout-all"])
    ap.add_argument("name")
    a = ap.parse_args(argv)
    if not os.path.exists(a.db):
        sys.exit(f"no database at {a.db} (use --db or T5L_DB)")
    st = Store(a.db)
    st.db.execute("PRAGMA busy_timeout=5000")
    try:
        row = st.account(a.name)
        if row is None:
            sys.exit(f"no account {a.name!r}")
        aid = row["id"]
        if a.command == "show":
            print(f"{row['name']}: created {time.ctime(row['created'])}, last seen "
                  f"{time.ctime(row['last_seen']) if row['last_seen'] else 'never'}, rating {row['rating']:.0f} "
                  f"+/- {row['rd']:.0f}, {row['wins']}W {row['losses']}L, ranked {row['ranked_games']}, "
                  f"remembered logins {st.session_count(aid)}, recovery codes left {st.recovery_left(aid)}")
        elif a.command == "reset-password":
            pw = "-".join(secrets.token_hex(3) for _ in range(3))
            st.set_password(aid, hash_password(pw))
            st.revoke_sessions(aid)
            print(f"New password for {row['name']}: {pw}\nGive it to the player privately; they should change it "
                  "in the launcher right away. Their remembered logins have ended.")
        elif a.command == "recovery-codes":
            codes = st.issue_recovery_codes(aid)
            print(f"New recovery codes for {row['name']} (the old ones no longer work):")
            for c in codes:
                print("   ", c)
        elif a.command == "logout-all":
            n = st.session_count(aid)
            st.revoke_sessions(aid)
            print(f"Ended {n} remembered login(s) of {row['name']}.")
    finally:
        st.close()


if __name__ == "__main__":
    main()
