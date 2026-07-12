# ⚽ Agentic Football Cup — Super Equipo de Estrellas

Equipo de 5 agentes IA con **formación dinámica** para la [Agentic Football Cup](https://agenticfootballcup.com/) de AWS.

## Filosofía Táctica

Este equipo no usa una formación estática. Cada agente **adapta su posición en tiempo real** según:
- El marcador (ganando, perdiendo, empatando)
- El tiempo restante (no es lo mismo empatar al inicio que en los últimos 20 segundos)
- La posesión del balón

### Formaciones Dinámicas

```
INICIO / EMPATE (mucho tiempo)     PERDIENDO (<60s)          PERDIENDO (<20s)
─────────────────────────────      ─────────────────         ─────────────────
     [FWD1]  [FWD2]                [FWD1][FWD2][MID]          [FWD1][FWD2][MID]
         [MID]                          [DEF]                    [DEF] ← sube!
         [DEF]                          [GK]                      [GK] ← sube!
         [GK]
── 1-1-1-2 (seguro) ──            ── 1-1-0-3 (agresivo) ──  ── all-in attack ──

GANANDO (<120s)                    GANANDO CÓMODO (2+)
─────────────────────────────      ─────────────────────
    [FWD1 baja]  [FWD2 baja]           Todos bajan
         [MID baja]                    [posesión]
         [DEF] ← profundo             [MARK tight]
         [GK]                          [GK]
── 1-2-2-0 (conservar) ──         ── bunker + posesión ──
```

## Estructura del Proyecto

```
aws-football-cup/
├── lib/                    # Librería compartida (usada por TODOS los agentes)
│   ├── agent_base.py      #   Factory de agentes + invoke handler (3 capas de error)
│   ├── fallback.py        #   Lógica rule-based por posición (backup del LLM)
│   ├── parsing.py         #   Extrae JSON de la respuesta del LLM
│   ├── state.py           #   Resume el game state para el LLM
│   └── test_helpers.py    #   Mock de AgentCore + game state de prueba
│
├── ai-gk/                 # 🧤 Goalkeeper  (Player 0)
│   └── src/main.py        #   Prompt: protege, distribuye, sube si pierde en final
│
├── ai-def/                # 🛡️  Defender   (Player 1)
│   └── src/main.py        #   Prompt: marca, intercepta. Sube a MID si perdemos.
│
├── ai-mid/                # ⚙️  Midfielder (Player 2)
│   └── src/main.py        #   Prompt: conecta, dispara. Pivote entre DEF y FWD según score.
│
├── ai-fwd1/               # ⚡ Forward 1  (Player 3)
│   └── src/main.py        #   Prompt: goleador izquierdo. Baja a defender si ganamos.
│
├── ai-fwd2/               # 🔥 Forward 2  (Player 4)
│   └── src/main.py        #   Prompt: goleador derecho. Baja a defender si ganamos.
│
├── viewer.py              # 🎮 Viewer gráfico con Pygame (cancha 2D + event log)
├── simulate.py            # 📟 Simulador ASCII en terminal
├── deploy-all.sh          # 🚀 Script de despliegue a AgentCore
└── _official_reference/   # 📚 Clon del repo oficial de AWS (referencia)
```

## Cada Agente — Comportamiento Dinámico

| Agente | Base | Cuando Gana | Cuando Pierde (final) |
|--------|------|-------------|----------------------|
| `ai-gk` (P0) | x=-50, defiende | x=-50, ultra-conservador | x=-35, sweeper activo |
| `ai-def` (P1) | x=-25, marca | x=-30, profundo | x=+10, extra midfielder/FWD |
| `ai-mid` (P2) | x=0, conecta | x=-5, posesión | x=+30, extra striker |
| `ai-fwd1` (P3) | x=+25, ataca | x=+10, baja a ayudar | x=+40, camp near goal |
| `ai-fwd2` (P4) | x=+25, ataca | x=+10, baja a ayudar | x=+40, camp near goal |

## Test Local

```bash
# Activar el venv
source .venv/bin/activate

# Test sin AWS (valida parsing, fallback, state summary)
python ai-gk/test_local.py
python ai-def/test_local.py
python ai-mid/test_local.py
python ai-fwd1/test_local.py
python ai-fwd2/test_local.py

# Test con LLM (requiere credenciales AWS + Bedrock habilitado)
python ai-gk/test_local.py --llm
python ai-fwd1/test_local.py --llm

# Simulador gráfico (Pygame)
python viewer.py                # Modo fallback (sin AWS)
python viewer.py --llm          # Con LLM real
python viewer.py --ticks 50 --speed 3   # Más largo y rápido

# Simulador terminal (ASCII)
python simulate.py --ticks 20
python simulate.py --llm
```

## Controles del Viewer (Pygame)

| Tecla | Acción |
|-------|--------|
| `Espacio` | Pausa/Resume |
| `→` | Aumentar velocidad |
| `←` | Reducir velocidad |
| `Q` / `Esc` | Salir |

## Cómo Funciona

1. Cada ~2s el servidor envía el **game state** (posiciones, score, tiempo)
2. El agente resume el estado en texto conciso → lo envía al LLM (Nova Micro)
3. El LLM razona sobre el estado + su prompt → retorna un **comando JSON**
4. El prompt incluye **reglas de posicionamiento dinámico** según score/tiempo
5. Si LLM falla → fallback rule-based → last resort (SET_STANCE)

## Editar la Táctica

Para cambiar el comportamiento de cualquier agente:
1. Abre `ai-<posicion>/src/main.py`
2. Edita el `SYSTEM_PROMPT` — especialmente la tabla **"Dynamic Positioning"**
3. Prueba: `python ai-<posicion>/test_local.py --llm`

### Guía de tuning rápido

- **Más agresivo**: Reduce los thresholds de x en "Losing" (que suban antes)
- **Más defensivo**: Aumenta los thresholds (que no suban tan rápido)
- **Más tiros**: Agrega "SHOOT even from 30+ units" en losing scenarios
- **Mejor posesión**: Agrega "prefer PASS over MOVE_TO" en el MID

## Comandos del Juego

### One-shot
- `MOVE_TO` — target_x, target_y, sprint
- `PASS` — target_player_id, type (GROUND/AERIAL/THROUGH)
- `SHOOT` — aim_location (TL/TR/BL/BR/CENTER), power (0.0-1.0)
- `GK_DISTRIBUTE` — target_player_id, method (THROW/KICK)
- `SLIDE_TACKLE` — target_player_id (riesgoso)

### Mantenidos (persisten entre ticks)
- `PRESS_BALL` — intensity (0.0-1.0)
- `MARK` — target_player_id, tightness (LOOSE/TIGHT)
- `INTERCEPT` — aggressive (bool)
- `FOLLOW_PLAYER` — target_player_id, target_team, distance

### Tácticos
- `SET_STANCE` — stance (0=Balanced, 1=Attack, 2=Defend)
- `CLEAR_OVERRIDE` — volver al AI default

## Deploy (cuando IAM esté listo)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
pip install bedrock-agentcore-starter-toolkit
AWS_DEFAULT_REGION=us-east-1 ./deploy-all.sh
```

## Links

- [Workshop oficial](https://catalog.workshops.aws/agentic-football/en-US)
- [Repo referencia AWS](https://github.com/aws-samples/sample-ai-possibilities/tree/main/agentic-football-sample-agents)
- [Strands Agents SDK](https://strandsagents.com/)
- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/)
