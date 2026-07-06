#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  deploy_from_local.sh — Build + transfert vers une instance EC2
#
#  Usage :
#    chmod +x deploy_from_local.sh
#    ./deploy_from_local.sh <USER>@<EC2_IP>
#
#  Exemple :
#    ./deploy_from_local.sh ubuntu@54.123.45.67
#
#  Prérequis locaux :
#    - pygbag installé dans le venv
#    - SSH configuré vers l'instance EC2
#
#  Ce script :
#    1. Régénère le build pygbag (build/web/)
#    2. Copie les fichiers de build sur l'EC2
#    3. Exécute le script de déploiement distant (nginx setup)
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}/.."

# ── Args ─────────────────────────────────────────────────────────────────
if [ $# -lt 1 ]; then
    echo "Usage: $0 <user>@<ec2_ip>"
    echo "Exemple: $0 ubuntu@54.123.45.67"
    exit 1
fi

EC2_TARGET="$1"
REMOTE_DIR="/tmp/alife-deploy"

echo "============================================"
echo "  ALife Simulation — Build + Deploy EC2"
echo "============================================"
echo "  Cible : ${EC2_TARGET}"
echo ""

# ── Step 1 : Build pygbag ──────────────────────────────────────────────
echo "[1/3] Build pygbag en cours..."
cd "${PROJECT_DIR}"
source venv/bin/activate
pygbag .
echo "[1/3] Build terminé."
echo ""

# ── Step 2 : Transfert ─────────────────────────────────────────────────
echo "[2/3] Transfert des fichiers vers ${EC2_TARGET}..."
ssh "${EC2_TARGET}" "mkdir -p ${REMOTE_DIR}/web ${REMOTE_DIR}/deploy"
scp -r build/web/* "${EC2_TARGET}:${REMOTE_DIR}/web/"
scp deploy/deploy_ec2.sh "${EC2_TARGET}:${REMOTE_DIR}/deploy/"
echo "[2/3] Transfert terminé."
echo ""

# ── Step 3 : Déploiement distant ───────────────────────────────────────
echo "[3/3] Déploiement sur l'instance EC2..."
ssh "${EC2_TARGET}" "cd ${REMOTE_DIR} && sudo bash deploy/deploy_ec2.sh"
echo "[3/3] Déploiement terminé."
echo ""

# ── Cleanup ─────────────────────────────────────────────────────────────
echo "[CLEANUP] Nettoyage des fichiers temporaires..."
ssh "${EC2_TARGET}" "rm -rf ${REMOTE_DIR}"

echo ""
echo "============================================"
echo "  Déploiement terminé !"
echo "============================================"
echo ""
EC2_IP=$(echo "${EC2_TARGET}" | cut -d'@' -f2)
echo "  Accès : http://${EC2_IP}"
echo ""
echo "  La simulation se charge dans le navigateur."
echo "  Cliquez sur la page pour lancer Pyodide."
echo ""