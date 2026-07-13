#!/bin/bash
# ============================================================================
# update-prompt.sh — Actualiza prompts SIN re-deploy
# ============================================================================
#
# Uso:
#   ./update-prompt.sh              # Sync todos los prompts
#   ./update-prompt.sh ai-def       # Solo el defensor
#
# Esto es ~100x más rápido que hacer deploy-all.sh porque:
#   - NO sube código a CodeBuild
#   - NO reconstruye el agente
#   - Solo actualiza el prompt en Bedrock Prompt Management
#   - El agente lo carga dinámicamente en la siguiente invocación
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if available
if [ -d ".venv/bin" ]; then
    source .venv/bin/activate
fi

echo "⚡ Actualizando prompts (sin re-deploy)..."
echo ""

if [ -n "$1" ]; then
    python sync-prompts.py "$@"
else
    python sync-prompts.py
fi

echo ""
echo "✅ ¡Listo! Los agentes cargarán los nuevos prompts automáticamente."
echo "   (máximo ${PROMPT_REFRESH_INTERVAL:-60} segundos de delay)"
