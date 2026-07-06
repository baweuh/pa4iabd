#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  test_local.sh — Lancer la simulation ALife dans le navigateur
#
#  La page web (web/index.html) charge Pyodide qui exécute le code Python
#  directement dans le navigateur. Aucun serveur Python requis.
#
#  Usage :
#    chmod +x test_local.sh
#    ./test_local.sh
#    ./test_local.sh 9090    # port personnalisé
#
#  Puis ouvrir : http://localhost:8000/web/
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-8000}"

# ── Vérifications ───────────────────────────────────────────────────────
if [ ! -f "${SCRIPT_DIR}/web/index.html" ]; then
    echo "[ERREUR] web/index.html introuvable dans ${SCRIPT_DIR}"
    exit 1
fi

if [ ! -f "${SCRIPT_DIR}/main.py" ]; then
    echo "[ERREUR] main.py introuvable. Ce script doit être lancé depuis la racine du projet."
    exit 1
fi

echo "============================================"
echo "  ALife Simulation — Serveur local"
echo "============================================"
echo "  Racine   : ${SCRIPT_DIR}"
echo "  URL      : http://localhost:${PORT}/web/"
echo ""
echo "  Ctrl+C pour arrêter"
echo "============================================"
echo ""

# ── Servir la racine du projet (web/index.html fetch les .py en relatif) ─
cd "${SCRIPT_DIR}"
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
    print(f'Ouvrez http://localhost:${PORT}/web/ dans votre navigateur')
    print('')
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        print('\nArrêt.')
        sys.exit(0)
"