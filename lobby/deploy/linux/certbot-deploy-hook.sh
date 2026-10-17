#!/bin/sh
# certbot deploy hook: copy a renewed Let's Encrypt certificate to where the lobby server reads
# it (the service user cannot read /etc/letsencrypt/live). Installed by install.sh as
# /etc/letsencrypt/renewal-hooks/deploy/t5lobby.sh; certbot runs it after every successful
# issue/renewal with RENEWED_LINEAGE=/etc/letsencrypt/live/<domain>.
# The server notices the new files within seconds; the reload below just makes it immediate.
set -eu
DEST=/etc/t5lobby/tls
[ -n "${RENEWED_LINEAGE:-}" ] || { echo "RENEWED_LINEAGE not set (run by certbot)" >&2; exit 1; }
install -d -m 0750 -o root -g t5lobby "$DEST"
# key first, certificate last: the server reloads when the files change and needs a matching pair
install -m 0640 -o root -g t5lobby "$RENEWED_LINEAGE/privkey.pem" "$DEST/privkey.pem.new"
install -m 0644 -o root -g t5lobby "$RENEWED_LINEAGE/fullchain.pem" "$DEST/fullchain.pem.new"
mv -f "$DEST/privkey.pem.new" "$DEST/privkey.pem"
mv -f "$DEST/fullchain.pem.new" "$DEST/fullchain.pem"
systemctl reload t5lobby 2>/dev/null || true
echo "t5lobby: certificate for $(basename "$RENEWED_LINEAGE") installed in $DEST"
