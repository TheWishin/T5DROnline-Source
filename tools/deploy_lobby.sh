#!/usr/bin/env bash
# PC side of a T5DR lobby update on the central server (Git Bash on the owner's PC). Only after the owner said yes.
#
#   bash tools/deploy_lobby.sh [--host H] [--key F] [--known-hosts F] [--dry-run] VERSION upload [REF]
#   bash tools/deploy_lobby.sh [...] VERSION STEP [ARGS]
#
# upload: packs lobby/ of REF (default the tag vVERSION) with `git -c core.autocrlf=false archive` (CRLF breaks the
#         shell scripts and the env template), copies it to /opt/src/lobby_VERSION.tgz on the server, checks its
#         SHA-256 there and unpacks it into /opt/src/t5dr-lobby-VERSION/ (refused if that folder exists).
# STEP:   check | precheck | notice MINUTES TEXT... | deploy [--drain-wait S] [--no-t4-stop] | verify | rollback [DIR]
#         runs /opt/src/t5dr-lobby-VERSION/lobby/deploy/linux/t5dr_deploy_remote.sh STEP there as root
#         (docs/DEPLOY_1.2.0.md says what each one does and prints).
# Defaults: --host 46.224.146.6 --key keys/vps_t5lobby --known-hosts keys/vps_known_hosts (from the repository).
# T5D_SSH / T5D_SCP: other ssh/scp commands (the local rehearsal, lobby/tools/deploy_rehearsal.py, uses stand-ins).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
HOST=46.224.146.6 KEY="$REPO/keys/vps_t5lobby" KNOWN="$REPO/keys/vps_known_hosts" DRY=0
die() { echo "deploy_lobby: $*" >&2; exit 1; }
while [ $# -gt 0 ]; do
    case "$1" in
        --host) HOST="${2:?}"; shift ;;
        --key) KEY="${2:?}"; shift ;;
        --known-hosts) KNOWN="${2:?}"; shift ;;
        --dry-run) DRY=1 ;;
        -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
        -*) die "unknown option $1" ;;
        *) break ;;
    esac
    shift
done
VERSION="${1:-}"; STEP="${2:-}"
printf '%s' "$VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || die "VERSION like 1.2.0 first (see --help)"
[ -n "$STEP" ] || die "a STEP after the version (see --help)"
shift 2
DIR="/opt/src/t5dr-lobby-$VERSION"
if [ -n "${T5D_SSH:-}" ]; then read -r -a SSH <<< "$T5D_SSH"; else
    SSH=(ssh -i "$KEY" -o BatchMode=yes -o "UserKnownHostsFile=$KNOWN" -o StrictHostKeyChecking=yes); fi
if [ -n "${T5D_SCP:-}" ]; then read -r -a SCP <<< "$T5D_SCP"; else
    SCP=(scp -i "$KEY" -o BatchMode=yes -o "UserKnownHostsFile=$KNOWN" -o StrictHostKeyChecking=yes); fi
run() { if [ "$DRY" = 1 ]; then printf '+ %s\n' "$*"; else "$@"; fi; }
q() { printf '%q ' "$@"; }

case "$STEP" in
    upload)
        REF="${1:-v$VERSION}"
        git -C "$REPO" rev-parse --verify -q "$REF^{commit}" >/dev/null || die "no commit $REF"
        TGZ="$REPO/build/lobby_$VERSION.tgz"
        mkdir -p "$REPO/build"
        run git -C "$REPO" -c core.autocrlf=false archive --format=tar.gz -o "$TGZ" "$REF" lobby
        SUM="$( [ "$DRY" = 1 ] && echo DRYRUN || sha256sum "$TGZ" | awk '{print $1}')"
        echo "lobby_$VERSION.tgz from $REF ($(git -C "$REPO" rev-parse --short=10 "$REF")): sha256 $SUM"
        run "${SCP[@]}" "$TGZ" "root@$HOST:/opt/src/lobby_$VERSION.tgz"
        run "${SSH[@]}" "root@$HOST" "set -e; cd /opt/src; echo '$SUM  lobby_$VERSION.tgz' | sha256sum -c -;
            [ ! -e '$DIR' ] || { echo '$DIR exists already: remove it first or use another version' >&2; exit 1; };
            mkdir -p '$DIR' && tar -xzf lobby_$VERSION.tgz -C '$DIR' && ls '$DIR/lobby/deploy/linux/t5dr_deploy_remote.sh'"
        ;;
    check|precheck|notice|deploy|verify|rollback)
        run "${SSH[@]}" "root@$HOST" "bash $DIR/lobby/deploy/linux/t5dr_deploy_remote.sh $(q "$STEP" "$@")"
        ;;
    *) die "STEP is upload, check, precheck, notice, deploy, verify or rollback" ;;
esac
