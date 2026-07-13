#!/bin/bash
set -e

# ============================================================================
# Deploy agents to Amazon Bedrock AgentCore — PARALLEL deployment
# ============================================================================
#
# Usage:
#   ./deploy-all.sh              # deploy all 5 agents in parallel
#   ./deploy-all.sh ai-gk       # deploy single agent
#   ./deploy-all.sh ai-mid ai-fwd1  # deploy specific agents in parallel
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/_build"

AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_DEFAULT_REGION

ALL_AGENTS=("ai-gk" "ai-def" "ai-mid" "ai-fwd1" "ai-fwd2")

if [ -n "$1" ]; then
  AGENTS=("$@")
else
  AGENTS=("${ALL_AGENTS[@]}")
fi

echo "=========================================="
echo "  ⚽ Agentic Football Cup — Parallel Deploy"
echo "=========================================="
echo ""

# Pre-flight
if ! command -v agentcore &> /dev/null; then
  echo "  ❌ 'agentcore' CLI not found. Install: pip install bedrock-agentcore-starter-toolkit"
  exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || {
  echo "  ❌ No valid AWS credentials."
  exit 1
}
export AWS_ACCOUNT_ID
echo "  Account: $AWS_ACCOUNT_ID | Region: $AWS_DEFAULT_REGION"
echo "  Agents:  ${AGENTS[*]}"
echo "  Mode:    PARALLEL"
echo ""

# Cleanup on exit
cleanup() { rm -rf "$BUILD_DIR"; }
trap cleanup EXIT

# Deploy one agent (called as background job)
deploy_one() {
  local AGENT=$1
  local AGENT_SRC="$SCRIPT_DIR/$AGENT"
  local STAGE="$BUILD_DIR/$AGENT"

  if [ ! -d "$AGENT_SRC" ]; then
    echo "  ❌ $AGENT: directory not found"
    return 1
  fi

  # Stage
  rm -rf "$STAGE"
  mkdir -p "$STAGE/src"
  cp "$AGENT_SRC/src/main.py" "$STAGE/src/main.py"
  rsync -a --exclude='__pycache__' "$SCRIPT_DIR/lib/" "$STAGE/lib/"
  cp "$AGENT_SRC/requirements.txt" "$STAGE/requirements.txt"

  # Generate config
  sed \
    -e "s|\${AWS_ACCOUNT_ID}|$AWS_ACCOUNT_ID|g" \
    -e "s|\${AWS_DEFAULT_REGION}|$AWS_DEFAULT_REGION|g" \
    "$AGENT_SRC/.bedrock_agentcore.yaml.template" > "$STAGE/.bedrock_agentcore.yaml"

  # Deploy
  if (cd "$STAGE" && agentcore deploy --auto-update-on-conflict > /tmp/deploy_${AGENT}.log 2>&1); then
    echo "  ✅ $AGENT: DEPLOYED"
  else
    echo "  ❌ $AGENT: FAILED (see /tmp/deploy_${AGENT}.log)"
    return 1
  fi
}

# Launch all deploys in parallel
PIDS=()
for AGENT in "${AGENTS[@]}"; do
  deploy_one "$AGENT" &
  PIDS+=($!)
done

# Wait for all
FAILED=0
for i in "${!PIDS[@]}"; do
  if ! wait ${PIDS[$i]}; then
    FAILED=$((FAILED + 1))
  fi
done

echo ""
echo "=========================================="
if [ $FAILED -eq 0 ]; then
  echo "  🏆 All ${#AGENTS[@]} agents deployed!"
else
  echo "  ⚠️  $FAILED agent(s) failed. Check /tmp/deploy_*.log"
fi
echo "=========================================="
