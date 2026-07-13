#!/bin/bash
set -e

# ============================================================================
# Deploy all 5 agents to Amazon Bedrock AgentCore
# ============================================================================
#
# Usage:
#   ./deploy-all.sh              # deploy all 5 agents
#   ./deploy-all.sh ai-gk       # deploy single agent
#   ./deploy-all.sh ai-mid      # redeploy just the midfielder
#
# Prerequisites:
#   pip install bedrock-agentcore-starter-toolkit
#   aws credentials configured (or Workshop Studio env vars set)
#   rsync installed (pre-installed on macOS)
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/_build"

AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_DEFAULT_REGION

ALL_AGENTS=("ai-gk" "ai-def" "ai-mid" "ai-fwd1" "ai-fwd2")

# If agent name passed as argument, deploy only that one
if [ -n "$1" ]; then
  AGENTS=("$1")
else
  AGENTS=("${ALL_AGENTS[@]}")
fi

echo "=========================================="
echo "  ⚽ Agentic Football Cup — Deploy"
echo "=========================================="
echo ""

# ------ Pre-flight checks ------
echo "Checking prerequisites..."

if ! command -v agentcore &> /dev/null; then
  echo "  ❌ 'agentcore' CLI not found."
  echo "     Install: pip install bedrock-agentcore-starter-toolkit"
  exit 1
fi
echo "  ✅ agentcore CLI"

if ! command -v rsync &> /dev/null; then
  echo "  ❌ 'rsync' not found."
  exit 1
fi
echo "  ✅ rsync"

if ! command -v aws &> /dev/null; then
  echo "  ❌ 'aws' CLI not found."
  exit 1
fi
echo "  ✅ aws CLI"

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || {
  echo "  ❌ No valid AWS credentials. Set them first."
  exit 1
}
export AWS_ACCOUNT_ID
echo "  ✅ AWS Account: $AWS_ACCOUNT_ID"
echo "  ✅ Region: $AWS_DEFAULT_REGION"
echo ""

# ------ Cleanup on exit ------
cleanup() {
  rm -rf "$BUILD_DIR"
}
trap cleanup EXIT

# ------ Deploy each agent ------
DEPLOYED=()
FAILED=()

for AGENT in "${AGENTS[@]}"; do
  AGENT_SRC="$SCRIPT_DIR/$AGENT"
  STAGE="$BUILD_DIR/$AGENT"

  echo "=========================================="
  echo "  📦 Deploying: $AGENT"
  echo "=========================================="

  # Validate
  if [ ! -d "$AGENT_SRC" ]; then
    echo "  ❌ Directory not found: $AGENT_SRC"
    FAILED+=("$AGENT")
    continue
  fi

  # Assemble staging directory
  rm -rf "$STAGE"
  mkdir -p "$STAGE/src"

  # Copy agent source
  cp "$AGENT_SRC/src/main.py" "$STAGE/src/main.py"

  # Copy shared lib (exclude __pycache__)
  rsync -a --exclude='__pycache__' "$SCRIPT_DIR/lib/" "$STAGE/lib/"

  # Copy requirements
  cp "$AGENT_SRC/requirements.txt" "$STAGE/requirements.txt"

  # Generate .bedrock_agentcore.yaml from template
  sed \
    -e "s|\${AWS_ACCOUNT_ID}|$AWS_ACCOUNT_ID|g" \
    -e "s|\${AWS_DEFAULT_REGION}|$AWS_DEFAULT_REGION|g" \
    "$AGENT_SRC/.bedrock_agentcore.yaml.template" > "$STAGE/.bedrock_agentcore.yaml"

  # Deploy
  echo "  Deploying from: $STAGE"
  if (cd "$STAGE" && agentcore deploy --auto-update-on-conflict); then
    echo "  ✅ $AGENT: DEPLOYED"
    DEPLOYED+=("$AGENT")
  else
    echo "  ❌ $AGENT: FAILED"
    FAILED+=("$AGENT")
  fi
  echo ""
done

# ------ Summary ------
echo "=========================================="
echo "  Deployment Summary"
echo "=========================================="
echo ""
echo "  Deployed: ${DEPLOYED[*]:-none}"
echo "  Failed:   ${FAILED[*]:-none}"
echo "  Account:  $AWS_ACCOUNT_ID"
echo "  Region:   $AWS_DEFAULT_REGION"
echo ""

if [ ${#FAILED[@]} -gt 0 ]; then
  echo "⚠️  Some agents failed. Check output above."
  exit 1
fi

echo "🏆 All agents deployed! Now:"
echo "   1. Go to Bedrock Console → AgentCore → Runtime"
echo "   2. Copy each agent's ARN"
echo "   3. Paste in Player Portal → My Team"
