#!/bin/sh
set -e

# Env vars expected:
#   DOMAIN
#   CERTBOT_EMAIL
#   GET_CERTS (True/False)

DOMAIN="${DOMAIN:-}"
GET_CERTS="${GET_CERTS:-False}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"

if [ -z "$DOMAIN" ]; then
  echo "[nginx] DOMAIN is empty. Set DOMAIN in .env.prod"
  exit 1
fi

# Render nginx config from template using DOMAIN
export DOMAIN
envsubst '$DOMAIN' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

mkdir -p /var/www/certbot

if [ "$GET_CERTS" = "True" ]; then
  echo "[nginx] GET_CERTS=True, preparing certificates for domain: $DOMAIN"

  # If cert does not exist yet, generate a temporary self-signed cert
  # so nginx can start on 443 and later be replaced by Let's Encrypt cert.
  # If cert does not exist yet, create temporary self-signed cert so nginx can start.
  if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "[nginx] No existing cert found. Creating temporary self-signed cert for $DOMAIN"
    mkdir -p "/etc/letsencrypt/live/$DOMAIN"
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
      -keyout "/etc/letsencrypt/live/$DOMAIN/privkey.pem" \
      -out "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" \
      -subj "/CN=$DOMAIN" >/dev/null 2>&1 || true
  fi

  # Start nginx in background to serve HTTP-01 challenge
  nginx -g 'daemon on;'

  if [ -z "$CERTBOT_EMAIL" ]; then
    echo "[nginx] CERTBOT_EMAIL is empty. Refusing to request Let's Encrypt certificate."
  else
    echo "[nginx] Requesting/renewing Let's Encrypt certificate for $DOMAIN"
    certbot certonly --nginx \
      --non-interactive --agree-tos \
      -m "$CERTBOT_EMAIL" \
      -d "$DOMAIN" \
      --keep-until-expiring \
      --deploy-hook "/autorenew_hook.sh" \
      --preferred-challenges http \
      || true
  fi

  # Stop background nginx
  nginx -s quit || true

  # If certbot created a suffixed live dir (DOMAIN-0001, DOMAIN-0002, ...),
  # replace /live/DOMAIN with a symlink to the newest one so nginx config stays stable.
  latest_live_dir=$(ls -1dt "/etc/letsencrypt/live/${DOMAIN}-"* 2>/dev/null | head -n 1 || true)
  if [ -n "$latest_live_dir" ] && [ -d "$latest_live_dir" ]; then
    echo "[nginx] Found Let's Encrypt live dir: $latest_live_dir"
    rm -rf "/etc/letsencrypt/live/$DOMAIN" || true
    ln -s "$latest_live_dir" "/etc/letsencrypt/live/$DOMAIN" || true
  fi

  # Remove broken/empty renewal config that can appear due to initial self-signed placeholder
  if [ -f "/etc/letsencrypt/renewal/$DOMAIN.conf" ] && [ ! -s "/etc/letsencrypt/renewal/$DOMAIN.conf" ]; then
    echo "[certbot] Removing empty renewal config: /etc/letsencrypt/renewal/$DOMAIN.conf"
    rm -f "/etc/letsencrypt/renewal/$DOMAIN.conf" || true
  fi

  # If we managed to get a real LE cert, reload the config (issuer != CN=DOMAIN self-signed)
  if openssl x509 -in "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" -noout -issuer 2>/dev/null | grep -q "Let's Encrypt"; then
    echo "[nginx] Let's Encrypt certificate detected."
  else
    echo "[nginx] WARNING: certificate looks self-signed or not issued by Let's Encrypt yet. Check /var/log/letsencrypt/letsencrypt.log"
  fi

  # Background auto-renewal loop (no systemd in container)
  (
    while true; do
      echo "[certbot] renew check..."
      certbot renew --non-interactive --deploy-hook "/autorenew_hook.sh" || true
      sleep 12h
    done
  ) &
fi

echo "[nginx] Starting nginx in foreground"
exec nginx -g 'daemon off;'
