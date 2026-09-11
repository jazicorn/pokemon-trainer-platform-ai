#!/bin/sh
# Runs as root — the image's default user until this hands off — so it can
# fix ownership of whatever's mounted at /app/data before the app itself
# starts. A freshly created Docker/Fly volume is empty and root-owned, which
# appuser (the image's non-root runtime user, see Dockerfile) can't write
# to on its own; a plain bind mount inherits the host directory's ownership,
# which may not match either. Re-chowning here, every start, handles both.
#
# gosu then replaces this process with the actual command running as
# appuser — not a wrapping shell — so container signals (e.g. Docker's
# SIGTERM on shutdown) reach the app directly instead of a shell in between.
set -e

mkdir -p /app/data
chown -R appuser:appuser /app/data

exec gosu appuser "$@"
