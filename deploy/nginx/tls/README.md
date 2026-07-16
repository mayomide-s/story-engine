Place origin TLS material for the managed production reverse proxy here at deploy time.

Do not commit real certificates or private keys.

Expected default mount paths inside the reverse-proxy container:

- `/etc/nginx/tls/fullchain.pem`
- `/etc/nginx/tls/privkey.pem`

If you use different paths, override:

- `NGINX_TLS_CERT_PATH`
- `NGINX_TLS_KEY_PATH`
- `NGINX_TLS_MOUNT_DIR`
