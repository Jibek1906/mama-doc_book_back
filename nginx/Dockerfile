FROM nginx:1.26.0

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    certbot \
    python3-certbot-nginx \
    openssl \
  && rm -rf /var/lib/apt/lists/*

COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY nginx_entrypoint.sh /nginx_entrypoint.sh
COPY autorenew_hook.sh /autorenew_hook.sh

RUN chmod +x /nginx_entrypoint.sh /autorenew_hook.sh

ENTRYPOINT ["/nginx_entrypoint.sh"]
