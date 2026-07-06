#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  start_from_web.sh — Lance la simulation ALife depuis le dossier web/ lui-même
#
#  Variante de test_local.sh : à utiliser si vous êtes déjà dans web/ ou si
#  vous voulez servir UNIQUEMENT le dossier web (les fichiers Python ont été
#  copiés à l'intérieur pour que web/ soit auto-suffisant).
#
#  Usage :
#    ./start_from_web.sh              # port 8000
#    ./start_from_web.sh 9090         # port personnalisé
#
#  Puis ouvrir : http://localhost:8000/
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

WEB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/web"
PORT="${1:-8000}"

if [ ! -f "${WEB_DIR}/index.html" ]; then
    echo "[ERREUR] web/index.html introuvable dans ${WEB_DIR}"
    exit 1
fi

if [ ! -f "${WEB_DIR}/main.py" ]; then
    echo "[ERREUR] web/main.py introuvable. web/ n'est pas auto-suffisant."
    echo "         Utilisez ./test_local.sh à la racine du projet."
    exit 1
fi

echo "============================================"
echo "  ALife Simulation — Serveur (depuis web/)"
echo "============================================"
echo "  Racine servie : ${WEB_DIR}"
echo "  URL           : http://localhost:${PORT}/"
echo ""
echo "  Ctrl+C pour arrêter"
echo "============================================"
echo ""

cd "${WEB_DIR}"
python3 -c "
import http.server
import sys

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Headers COOP/COEP requis par Pyodide (SharedArrayBuffer)
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        super().end_headers()

    def log_message(self, fmt, *args):
        print(f'  [{self.log_date_time_string()}] {args[0]}')

with http.server.HTTPServer(('', ${PORT}), Handler) as s:
    print(f'Serveur démarré sur le port ${PORT}')
    print(f'Ouvrez http://localhost:${PORT}/ dans votre navigateur')
    print('')
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        print('\nArrêt.')
        sys.exit(0)
"
