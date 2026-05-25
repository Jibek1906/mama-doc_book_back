#!/bin/sh
set -e

echo "[certbot] renewed certificate, reloading nginx"
nginx -s reload || true
