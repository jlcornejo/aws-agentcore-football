# ⚽ AgentCore Evaluations — Football Cup

Evaluación automatizada usando **Amazon Bedrock AgentCore Evaluations** (On-Demand Dataset Runner).

## Prerequisitos

1. Agentes desplegados en AgentCore Runtime (`./deploy-all.sh`)
2. Observability habilitado (spans en CloudWatch)
3. Transaction Search habilitado en CloudWatch
4. Python deps: `pip install bedrock-agentcore boto3`

## Estructura

```
evaluations/
├── run_evaluation.py          # Script principal — usa OnDemandEvaluationDatasetRunner
├── setup_evaluator.py         # Registra custom evaluator + configura online eval
├── custom_evaluator.json      # Config del evaluador táctico custom (LLM-as-a-Judge)
├── dataset_mid.json           # Scenarios para ai-mid (4 escenarios)
├── dataset_fwd1.json          # Scenarios para ai-fwd1 (2 escenarios)
├── agents.json.example        # Template de config multi-agente
└── results/                   # Resultados guardados (JSON)
```

## Uso Rápido

### Evaluar un agente específico:

```bash
python evaluations/run_evaluation.py \
    --agent-arn arn:aws:bedrock-agentcore:us-east-1:123456:runtime/ai-mid \
    --log-group /aws/bedrock-agentcore/runtimes/ai-mid-DEFAULT \
    --dataset evaluations/dataset_mid.json
```

### Evaluar todos los agentes:

```bash
cp evaluations/agents.json.example evaluations/agents.json
# Editar con tus ARNs reales
python evaluations/run_evaluation.py --config evaluations/agents.json
```

### Registrar el evaluador custom táctico:

```bash
python evaluations/setup_evaluator.py create
```

### Configurar online evaluation (monitoreo continuo):

```bash
python evaluations/setup_evaluator.py online <agent-runtime-id> <role-arn>
```

## Evaluadores Usados

| Evaluador | Nivel | Qué mide |
|-----------|-------|----------|
| `Builtin.GoalSuccessRate` | Session | ¿El agente logró lo que debía? |
| `Builtin.Correctness` | Trace | ¿La respuesta es correcta vs expected? |
| `Builtin.Helpfulness` | Trace | ¿La decisión es útil en contexto? |
| `Builtin.InstructionFollowing` | Trace | ¿Sigue las instrucciones del prompt? |
| Custom: `football-tactical-accuracy` | Trace | ¿La decisión táctica es correcta? |

## Cómo Funciona

```
1. OnDemandEvaluationDatasetRunner invoca el agente con cada scenario
2. Espera 180s para que los spans lleguen a CloudWatch
3. CloudWatchAgentSpanCollector recoge los spans
4. Llama al Evaluate API con cada evaluador + ground truth
5. Retorna scores por scenario y evaluador
```

## Interpretar Resultados

- **GoalSuccessRate < 0.8**: El agente no cumple assertions → revisar prompt
- **Correctness < 0.7**: Respuesta incorrecta vs expected → prompt demasiado vago
- **InstructionFollowing < 0.7**: Ignora instrucciones → prompt muy largo o conflictivo
- **Helpfulness < 0.7**: Decisiones inútiles → modelo muy pequeño para la complejidad

## Agregar Escenarios

Edita `dataset_<agent>.json` siguiendo el schema:

```json
{
  "scenarios": [
    {
      "scenario_id": "unique-id",
      "turns": [{"input": {"prompt": "..."}, "expected_response": "..."}],
      "assertions": ["Assertion 1", "Assertion 2"]
    }
  ]
}
```
