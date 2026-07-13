#!/bin/bash
set -e

# ============================================================================
# Setup AgentCore Memory for the football team
# ============================================================================
#
# Creates a shared memory resource in Bedrock AgentCore that all 5 agents use.
# Run this ONCE before deploying with memory enabled.
#
# Usage:
#   ./setup-memory.sh
#
# After running, export the MEMORY_ID and set MEMORY_ENABLED=true in your .env
# ============================================================================

AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
MEMORY_NAME="${MEMORY_NAME:-football-team-memory}"

echo "=========================================="
echo "  🧠 AgentCore Memory Setup"
echo "=========================================="
echo ""
echo "Region: $AWS_DEFAULT_REGION"
echo "Memory name: $MEMORY_NAME"
echo ""

# Check if agentcore CLI is available
if ! command -v agentcore &> /dev/null; then
  echo "❌ 'agentcore' CLI not found."
  echo "   Install: pip install bedrock-agentcore-starter-toolkit"
  exit 1
fi

# Create memory using the SDK directly (more control than CLI)
python3 - <<'PYTHON_SCRIPT'
import os
import sys

try:
    from bedrock_agentcore.memory import MemoryClient
except ImportError:
    print("❌ bedrock_agentcore package not found.")
    print("   Install: pip install bedrock-agentcore")
    sys.exit(1)

region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
memory_name = os.environ.get("MEMORY_NAME", "football-team-memory")

print(f"Creating memory '{memory_name}' in {region}...")
print("")

client = MemoryClient(region_name=region)

# Create memory with semantic strategy for recalling game patterns
memory = client.create_memory_and_wait(
    name=memory_name,
    description="Short-term memory for football team agents - tracks opponent patterns and coaching instructions",
    strategies=[
        {
            "semanticMemoryStrategy": {
                "name": "GamePatterns",
                "namespaceTemplates": ["/game/{actorId}/{sessionId}/"]
            }
        }
    ]
)

memory_id = memory.get("id")
print(f"✅ Memory created successfully!")
print(f"")
print(f"   Memory ID: {memory_id}")
print(f"")
print(f"Add these to your .env file:")
print(f"")
print(f"   MEMORY_ENABLED=true")
print(f"   MEMORY_ID={memory_id}")
print(f"   MEMORY_ACTOR_ID=football-team")
print(f"")
print(f"Then redeploy: ./deploy-all.sh")
PYTHON_SCRIPT

echo ""
echo "=========================================="
echo "  Done!"
echo "=========================================="
