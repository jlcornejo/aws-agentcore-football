"""
Setup AgentCore Evaluations — registra el evaluador custom y configura
online evaluation para monitoreo continuo.

Usage:
    python evaluations/setup_evaluator.py create     # Crea el evaluador custom
    python evaluations/setup_evaluator.py online     # Configura online evaluation
    python evaluations/setup_evaluator.py list       # Lista evaluadores existentes
"""

import sys
import os
import json
import boto3

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
EVALUATOR_NAME = "football-tactical-accuracy"


def create_custom_evaluator():
    """Registra el evaluador táctico custom en AgentCore."""
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)

    config_path = os.path.join(os.path.dirname(__file__), "custom_evaluator.json")
    with open(config_path) as f:
        evaluator_config = json.load(f)

    try:
        response = client.create_evaluator(
            evaluatorName=EVALUATOR_NAME,
            level="TRACE",
            evaluatorConfig=evaluator_config,
            description="Evalúa decisiones tácticas de agentes de fútbol IA",
        )
        evaluator_id = response.get("evaluatorId")
        evaluator_arn = response.get("evaluatorArn")
        print(f"✅ Evaluador creado:")
        print(f"   ID:  {evaluator_id}")
        print(f"   ARN: {evaluator_arn}")
        print(f"\n   Agrégalo a tu evaluación con:")
        print(f"   evaluator_ids=[\"{evaluator_arn}\"]")
        return evaluator_arn
    except Exception as e:
        if "already exists" in str(e).lower() or "ConflictException" in str(type(e)):
            print(f"ℹ️  Evaluador '{EVALUATOR_NAME}' ya existe.")
            # List to get the ARN
            return list_evaluators(quiet=True)
        raise


def setup_online_evaluation(agent_runtime_id: str, role_arn: str):
    """Configura online evaluation para monitoreo continuo."""
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)

    log_group = f"/aws/bedrock-agentcore/runtimes/{agent_runtime_id}-DEFAULT"
    service_name = f"{agent_runtime_id}.DEFAULT"

    try:
        response = client.create_online_evaluation_config(
            onlineEvaluationConfigName=f"football-{agent_runtime_id}-monitor",
            description=f"Monitoreo continuo del agente {agent_runtime_id}",
            rule={"samplingConfig": {"samplingPercentage": 100.0}},
            dataSourceConfig={
                "cloudWatchLogs": {
                    "logGroupNames": [log_group],
                    "serviceNames": [service_name],
                }
            },
            evaluators=[
                {"evaluatorId": "Builtin.GoalSuccessRate"},
                {"evaluatorId": "Builtin.Helpfulness"},
                {"evaluatorId": "Builtin.InstructionFollowing"},
                {"evaluatorId": "Builtin.ToolSelectionAccuracy"},
            ],
            evaluationExecutionRoleArn=role_arn,
            enableOnCreate=True,
        )
        config_name = response.get("onlineEvaluationConfigName")
        print(f"✅ Online evaluation configurada: {config_name}")
        print(f"   Log group:  {log_group}")
        print(f"   Sampling:   100%")
        print(f"   Evaluators: GoalSuccessRate, Helpfulness, "
              f"InstructionFollowing, ToolSelectionAccuracy")
    except Exception as e:
        print(f"❌ Error configurando online evaluation: {e}")


def list_evaluators(quiet=False):
    """Lista evaluadores custom existentes."""
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    try:
        response = client.list_evaluators()
        evaluators = response.get("evaluators", [])
        football_arn = None
        if not quiet:
            print(f"\n📋 Evaluadores custom ({len(evaluators)}):")
        for ev in evaluators:
            if not quiet:
                print(f"   • {ev['evaluatorName']} (ID: {ev['evaluatorId']})")
            if ev["evaluatorName"] == EVALUATOR_NAME:
                football_arn = ev.get("evaluatorArn")
        return football_arn
    except Exception as e:
        if not quiet:
            print(f"❌ Error listando evaluadores: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    if cmd == "create":
        create_custom_evaluator()
    elif cmd == "online":
        if len(sys.argv) < 4:
            print("Usage: setup_evaluator.py online <agent-runtime-id> <role-arn>")
            print("  agent-runtime-id: el ID del agente en AgentCore Runtime")
            print("  role-arn: ARN del IAM role para evaluación")
            return
        setup_online_evaluation(sys.argv[2], sys.argv[3])
    elif cmd == "list":
        list_evaluators()
    else:
        print(f"Comando desconocido: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
