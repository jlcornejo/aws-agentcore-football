#!/bin/bash
# Deploy all 5 agents to Amazon Bedrock AgentCore
# Usage:
#   ./deploy-all.sh              # Deploy all
#   ./deploy-all.sh ai-gk       # Deploy single agent

set -e

ALL_AGENTS=("ai-gk" "ai-def" "ai-mid" "ai-fwd1" "ai-fwd2")
AGENTS_TO_DEPLOY=("${@:-${ALL_AGENTS[@]}}")
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "🏟️  Deploying to account $ACCOUNT_ID in $REGION"
echo "   Agents: ${AGENTS_TO_DEPLOY[*]}"
echo ""

for AGENT in "${AGENTS_TO_DEPLOY[@]}"; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 Deploying $AGENT..."

    BUILD_DIR="_build/$AGENT"
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR"

    # Copy agent code + shared lib
    cp -r "$AGENT/src" "$BUILD_DIR/src"
    cp -r lib "$BUILD_DIR/lib"
    cp "$AGENT/requirements.txt" "$BUILD_DIR/requirements.txt"

    # Generate AgentCore config from template
    AGENT_NAME=$(echo "${AGENT}" | tr '-' '_')
    cat > "$BUILD_DIR/.bedrock_agentcore.yaml" <<EOF
default_agent: ${AGENT_NAME}_agent
agents:
  ${AGENT_NAME}_agent:
    name: ${AGENT_NAME}_agent
    framework: strands
    entry_point: src.main
    model_id: us.amazon.nova-micro-v1:0
    region: ${REGION}
EOF

    # Deploy
    cd "$BUILD_DIR"
    agentcore deploy
    cd - > /dev/null

    # Cleanup
    rm -rf "$BUILD_DIR"
    echo "✅ $AGENT deployed!"
    echo ""
done

rm -rf _build
echo "🏆 All agents deployed! Register their ARNs in the Player Portal."
