"""
⚽ AgentCore Evaluations — On-Demand Dataset Runner

Usa el OnDemandEvaluationDatasetRunner del SDK de AgentCore para evaluar
los agentes desplegados en Runtime con evaluadores built-in.

Prerequisitos:
  - Agentes desplegados en AgentCore Runtime (./deploy-all.sh)
  - Observability habilitado (spans en CloudWatch)
  - Transaction Search habilitado en CloudWatch
  - pip install bedrock-agentcore boto3

Usage:
    python evaluations/run_evaluation.py --agent-arn <ARN> --log-group <LOG_GROUP>
    python evaluations/run_evaluation.py --config evaluations/agents.json

Ejemplo:
    python evaluations/run_evaluation.py \\
        --agent-arn arn:aws:bedrock-agentcore:us-east-1:123456:runtime/ai-mid \\
        --log-group /aws/bedrock-agentcore/runtimes/ai-mid-DEFAULT \\
        --region us-east-1
"""

import json
import sys
import os
import argparse
from datetime import datetime

import boto3
from bedrock_agentcore.evaluation import (
    AgentInvokerInput,
    AgentInvokerOutput,
    OnDemandEvaluationDatasetRunner,
    EvaluationRunConfig,
    EvaluatorConfig,
    FileDatasetProvider,
    CloudWatchAgentSpanCollector,
)


# ---------------------------------------------------------------------------
# Agent Invoker — llama al agente desplegado en AgentCore Runtime
# ---------------------------------------------------------------------------

def create_agent_invoker(agent_arn: str, region: str):
    """Crea un invoker para un agente desplegado en AgentCore Runtime."""
    client = boto3.client("bedrock-agentcore", region_name=region)

    def agent_invoker(invoker_input: AgentInvokerInput) -> AgentInvokerOutput:
        payload = invoker_input.payload
        if isinstance(payload, str):
            payload = payload.encode()
        elif isinstance(payload, dict):
            payload = json.dumps(payload).encode()

        print(f"  [{invoker_input.session_id[:20]}...] Invocando agente...")
        response = client.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            runtimeSessionId=invoker_input.session_id,
            payload=payload,
        )
        response_body = response["response"].read()
        agent_output = json.loads(response_body)
        print(f"  [{invoker_input.session_id[:20]}...] Respuesta: "
              f"{json.dumps(agent_output)[:100]}")
        return AgentInvokerOutput(agent_output=agent_output)

    return agent_invoker


# ---------------------------------------------------------------------------
# Run evaluation
# ---------------------------------------------------------------------------

def run_evaluation(
    agent_arn: str,
    log_group: str,
    region: str = "us-east-1",
    dataset_path: str = None,
    evaluator_ids: list = None,
    delay_seconds: int = 180,
):
    """Ejecuta evaluación on-demand con AgentCore Evaluations."""

    if dataset_path is None:
        dataset_path = os.path.join(os.path.dirname(__file__), "dataset.json")

    if evaluator_ids is None:
        evaluator_ids = [
            "Builtin.GoalSuccessRate",
            "Builtin.Correctness",
            "Builtin.Helpfulness",
            "Builtin.InstructionFollowing",
        ]

    print(f"\n{'═' * 70}")
    print(f"  ⚽ AgentCore Evaluations — On-Demand Dataset Runner")
    print(f"{'═' * 70}")
    print(f"  Agent ARN:  {agent_arn}")
    print(f"  Log Group:  {log_group}")
    print(f"  Region:     {region}")
    print(f"  Dataset:    {dataset_path}")
    print(f"  Evaluators: {evaluator_ids}")
    print(f"  Delay:      {delay_seconds}s")
    print(f"  Time:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═' * 70}\n")

    # 1. Load dataset
    print("📂 Cargando dataset...")
    dataset = FileDatasetProvider(dataset_path).get_dataset()
    print(f"   {len(dataset.scenarios)} escenarios cargados\n")

    # 2. Create invoker
    print("🔌 Creando agent invoker...")
    invoker = create_agent_invoker(agent_arn, region)

    # 3. Create span collector
    print("📡 Configurando span collector (CloudWatch)...")
    span_collector = CloudWatchAgentSpanCollector(
        log_group_name=log_group,
        region=region,
    )

    # 4. Configure evaluators
    config = EvaluationRunConfig(
        evaluator_config=EvaluatorConfig(
            evaluator_ids=evaluator_ids,
        ),
        evaluation_delay_seconds=delay_seconds,
        max_concurrent_scenarios=5,
    )

    # 5. Run!
    print(f"\n🚀 Ejecutando evaluación...")
    print(f"   (Esto toma ~{delay_seconds + 30}s: invocación + "
          f"espera de ingesta + evaluación)\n")

    runner = OnDemandEvaluationDatasetRunner(region=region)
    result = runner.run(
        agent_invoker=invoker,
        dataset=dataset,
        span_collector=span_collector,
        config=config,
    )

    # 6. Print results
    print_evaluation_results(result, evaluator_ids)

    # 7. Save results
    output_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(
        output_dir,
        f"agentcore_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(output_path, "w") as f:
        f.write(result.model_dump_json(indent=2))
    print(f"\n  📁 Resultados guardados: {output_path}")

    return result


# ---------------------------------------------------------------------------
# Print results
# ---------------------------------------------------------------------------

def print_evaluation_results(result, evaluator_ids):
    """Imprime resultados de evaluación de forma legible."""
    print(f"\n{'═' * 70}")
    print(f"  📊 RESULTADOS DE EVALUACIÓN AGENTCORE")
    print(f"{'═' * 70}\n")

    completed = 0
    failed = 0
    scores_by_evaluator = {}

    for scenario in result.scenario_results:
        status_icon = "✅" if scenario.status == "COMPLETED" else "❌"
        print(f"  {status_icon} Scenario: {scenario.scenario_id} "
              f"(session: {scenario.session_id[:30]}...)")

        if scenario.status != "COMPLETED":
            failed += 1
            print(f"     Error: {scenario.error}")
            continue

        completed += 1
        for evaluator in scenario.evaluator_results:
            ev_id = evaluator.evaluator_id
            if ev_id not in scores_by_evaluator:
                scores_by_evaluator[ev_id] = []

            for r in evaluator.results:
                value = r.get("value")
                label = r.get("label", "N/A")
                explanation = r.get("explanation", "")
                error_code = r.get("errorCode")

                if error_code:
                    print(f"     ⚠️  {ev_id}: ERROR {error_code}")
                    continue

                if value is not None:
                    scores_by_evaluator[ev_id].append(value)

                # Truncate explanation for display
                expl_short = explanation[:120] + "..." if len(explanation) > 120 else explanation
                print(f"     📈 {ev_id}:")
                print(f"        Score: {value}  Label: {label}")
                if expl_short:
                    print(f"        Razón: {expl_short}")
        print()

    # --- Aggregate scores ---
    print(f"{'═' * 70}")
    print(f"  📊 RESUMEN AGREGADO")
    print(f"{'═' * 70}")
    print(f"  Scenarios completados: {completed}/{completed + failed}")
    print(f"  Scenarios fallidos:    {failed}/{completed + failed}\n")

    print(f"  {'Evaluator':<40} {'Avg Score':<12} {'Samples'}")
    print(f"  {'─' * 65}")
    for ev_id in evaluator_ids:
        values = scores_by_evaluator.get(ev_id, [])
        if values:
            avg = sum(values) / len(values)
            emoji = "🟢" if avg >= 0.8 else ("🟡" if avg >= 0.5 else "🔴")
            print(f"  {ev_id:<40} {emoji} {avg:.3f}      {len(values)}")
        else:
            print(f"  {ev_id:<40} ⚪ N/A        0")

    # --- Identify failures ---
    print(f"\n{'═' * 70}")
    print(f"  🔍 QUÉ ESTÁ HACIENDO MAL (scores bajos)")
    print(f"{'═' * 70}")

    low_scores = []
    for scenario in result.scenario_results:
        if scenario.status != "COMPLETED":
            continue
        for evaluator in scenario.evaluator_results:
            for r in evaluator.results:
                value = r.get("value")
                if value is not None and value < 0.5:
                    low_scores.append({
                        "scenario": scenario.scenario_id,
                        "evaluator": evaluator.evaluator_id,
                        "score": value,
                        "label": r.get("label", ""),
                        "explanation": r.get("explanation", ""),
                    })

    if low_scores:
        for ls in low_scores:
            print(f"\n  ❌ {ls['scenario']} — {ls['evaluator']}")
            print(f"     Score: {ls['score']}  Label: {ls['label']}")
            print(f"     Razón: {ls['explanation'][:200]}")
    else:
        print("\n  🏆 ¡No hay scores críticos! Todos >= 0.5")

    print(f"\n{'═' * 70}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="⚽ AgentCore Evaluations — On-Demand Dataset Runner"
    )
    parser.add_argument(
        "--agent-arn", type=str,
        help="ARN del agente en AgentCore Runtime"
    )
    parser.add_argument(
        "--log-group", type=str,
        help="CloudWatch log group del agente "
             "(ej: /aws/bedrock-agentcore/runtimes/ai-mid-DEFAULT)"
    )
    parser.add_argument(
        "--region", type=str, default="us-east-1",
        help="AWS region (default: us-east-1)"
    )
    parser.add_argument(
        "--dataset", type=str, default=None,
        help="Path al dataset JSON (default: evaluations/dataset.json)"
    )
    parser.add_argument(
        "--delay", type=int, default=180,
        help="Segundos de espera para ingesta de spans (default: 180)"
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="JSON config con múltiples agentes: "
             '{"agents": [{"arn": "...", "log_group": "...", "dataset": "..."}]}'
    )
    parser.add_argument(
        "--evaluators", type=str, nargs="+",
        default=None,
        help="Lista de evaluator IDs (default: GoalSuccessRate, Correctness, "
             "Helpfulness, InstructionFollowing)"
    )
    args = parser.parse_args()

    # Multi-agent config mode
    if args.config:
        with open(args.config) as f:
            config = json.load(f)
        for agent_cfg in config["agents"]:
            run_evaluation(
                agent_arn=agent_cfg["arn"],
                log_group=agent_cfg["log_group"],
                region=agent_cfg.get("region", args.region),
                dataset_path=agent_cfg.get("dataset", args.dataset),
                evaluator_ids=args.evaluators,
                delay_seconds=args.delay,
            )
        return

    # Single agent mode
    if not args.agent_arn or not args.log_group:
        # Try environment variables
        agent_arn = args.agent_arn or os.environ.get("AGENT_ARN")
        log_group = args.log_group or os.environ.get("AGENT_LOG_GROUP")

        if not agent_arn or not log_group:
            parser.print_help()
            print("\n⚠️  Necesitas --agent-arn y --log-group, o un --config JSON.")
            print("\nEjemplo:")
            print("  python evaluations/run_evaluation.py \\")
            print("    --agent-arn arn:aws:bedrock-agentcore:us-east-1:"
                  "123456:runtime/ai-mid \\")
            print("    --log-group /aws/bedrock-agentcore/runtimes/"
                  "ai-mid-DEFAULT")
            print("\nO con config multi-agente:")
            print("  python evaluations/run_evaluation.py "
                  "--config evaluations/agents.json")
            sys.exit(1)
    else:
        agent_arn = args.agent_arn
        log_group = args.log_group

    run_evaluation(
        agent_arn=agent_arn,
        log_group=log_group,
        region=args.region,
        dataset_path=args.dataset,
        evaluator_ids=args.evaluators,
        delay_seconds=args.delay,
    )


if __name__ == "__main__":
    main()
