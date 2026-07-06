#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  deploy_ec2.sh — Déploiement ALife Simulation sur EC2 (Ubuntu 22.04/24.04)
#
#  Prérequis :
#    - Instance EC2 Ubuntu avec port 80 ouvert (security group)
#    - SSH configuré vers l'instance
#    - Ce script + le dossier build/web/ transférés sur l'instance
#
#  Usage :
#    chmod +x deploy_ec2.sh
#    sudo ./deploy_ec2.sh
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Configuration ───────────────────────────────────────────────────────
WEB_ROOT="/var/www/alife-sim"
NGINX_CONF="/etc/nginx/sites-available/alife-sim"
NGINX_ENABLED="/etc/nginx/sites-enabled/alife-sim"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/../build/web"

echo "============================================"
echo "  ALife Simulation — Déploiement EC2"
echo "============================================"

# ── Vérifications ───────────────────────────────────────────────────────
if [ ! -f "${BUILD_DIR}/index.html" ]; then
    echo "[ERREUR] build/web/index.html introuvable."
    echo "         Lancez d'abord : pygbag ."
    exit 1
fi

if ! command -v nginx &>/dev/null; then
    echo "[INFO] Installation de nginx..."
    apt-get update -qq
    apt-get install -y -qq nginx
else
    echo "[INFO] nginx déjà installé."
fi

# ── Copie des fichiers statiques ────────────────────────────────────────
echo "[INFO] Copie des fichiers vers ${WEB_ROOT}..."
mkdir -p "${WEB_ROOT}"
cp -r "${BUILD_DIR}"/* "${WEB_ROOT}/"

# Permissions
chown -R www-data:www-data "${WEB_ROOT}"
chmod -R 755 "${WEB_ROOT}"

# ── Configuration nginx ─────────────────────────────────────────────────
echo "[INFO] Configuration nginx..."
cat > "${NGINX_CONF}" << 'EOF'
server {
    listen 80;
    server_name _;

    root /var/www/alife-sim;
    index index.html;

    # Cache aggressif pour les assets statiques (apk, wasm, js)
    location ~* \.(apk|wasm|js|css|png|jpg|ico|svg|woff2?)$ {
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # Pas de cache pour index.html (pour détecter les mises à jour)
    location = /index.html {
        expires -1;
        add_header Cache-Control "no-store, no-cache, must-revalidate";
    }

    # Compression gzip
    gzip on;
    gzip_types text/html text/css application/javascript application/wasm;
    gzip_min_length 256;

    # CORS/COOP/COEP headers pour Pyodide (requis par SharedArrayBuffer)
    add_header Cross-Origin-Opener-Policy "same-origin" always;
    add_header Cross-Origin-Embedder-Policy "require-corp" always;

    # Types MIME pour wasm
    types {
        application/wasm wasm;
        application/javascript mjs;
    }

    # Taille max pour l'upload (non utilisé ici mais bonne pratique)
    client_max_body_size 10M;
}
EOF

# Activer le site
ln -sf "${NGINX_CONF}" "${NGINX_ENABLED}"

# Désactiver le site default si il bloque le port 80
if [ -f /etc/nginx/sites-enabled/default ]; then
    rm -f /etc/nginx/sites-enabled/default
fi

# ── Test + reload nginx ─────────────────────────────────────────────────
echo "[INFO] Test de la configuration nginx..."
nginx -t

echo "[INFO] Reload nginx..."
systemctl reload nginx || systemctl start nginx
systemctl enable nginx

# ── Firewall (UFW) ──────────────────────────────────────────────────────
if command -v ufw &>/dev/null; then
    echo "[INFO] Configuration UFW..."
    ufw allow 'Nginx Full' 2>/dev/null || true
fi

echo ""
echo "============================================"
echo "  Déploiement terminé !"
echo "============================================"
echo ""
echo "  Accès : http://<IP_DE_VOTRE_EC2>"
echo ""
echo "  Pour vérifier :"
echo "    curl -I http://localhost"
echo ""
echo "  Pour mettre à jour :"
echo "    1. pygbag .              (régénérer le build en local)"
echo "    2. scp -r build/web/* ec2-user@<IP>:/var/www/alife-sim/"
echo ""