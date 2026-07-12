# 🏟️ Guía Completa — Agentic Football Cup

## Qué es

Workshop de 4 horas de AWS donde construyes un equipo de 5 agentes IA que juegan fútbol 5v5 en tiempo real. Los agentes se despliegan en Amazon Bedrock AgentCore y compiten contra otros equipos de participantes.

**El camino va más allá del workshop**: completar el evento te da acceso a la Global League Qualifying, y los ganadores compiten en vivo en AWS re:Invent 2026 en Las Vegas.

---

## Mecánica del Juego

### El loop de cada tick

```
1. Server congela el juego
2. Envía gameState a los 10 agentes (5 por equipo) EN PARALELO
3. Espera hasta 5 segundos por respuesta
4. Si no responde → mantiene el último comando
5. Aplica todos los comandos
6. Simula ~2 segundos de física
7. Repite (~150 ticks por partido = 5 minutos)
```

**El juego NO corre en tiempo real mientras los agentes piensan.** Es un sistema por turnos. El servidor espera a todos antes de avanzar.

### Parámetros clave

| Parámetro | Valor |
|-----------|-------|
| Jugadores por equipo | 5 (GK, DEF, MID, FWD1, FWD2) |
| Duración del partido | ~5 minutos (120-150 ticks) |
| Frecuencia de decisión | ~1 cada 2 segundos |
| Timeout por decisión | 5 segundos máximo |
| Timeout de riesgo real | ~900ms (según experiencia del equipo chino) |
| Invocaciones por partido | 300-600 por equipo |
| Coordenadas campo | x: -55 a +55, y: -35 a +35 |
| HOME ataca hacia | +x |
| AWAY ataca hacia | -x |

### Reglas especiales

- **NO hay fuera de banda** — el balón nunca sale del campo
- **NO hay corners, saques de banda ni goal kicks**
- **Juego continuo** — solo se pausa tras gol (reset a posiciones)
- **Formación del portal** solo define la posición INICIAL (kickoff)
- Una vez empieza el partido, cada agente se mueve donde quiera

### Comandos disponibles

**One-shot (ejecutan una vez):**
- `MOVE_TO` — target_x, target_y, sprint (bool)
- `PASS` — target_player_id, type (GROUND/AERIAL/THROUGH)
- `SHOOT` — aim_location (TL/TR/BL/BR/CENTER), power (0.0-1.0)
- `GK_DISTRIBUTE` — target_player_id, method (THROW/KICK)
- `SLIDE_TACKLE` — target_player_id, sprint, distance (riesgoso)

**Mantenidos (persisten entre ticks):**
- `PRESS_BALL` — intensity (0.0-1.0)
- `MARK` — target_player_id, tightness (LOOSE/TIGHT)
- `INTERCEPT` — aggressive (bool)
- `FOLLOW_PLAYER` — target_player_id, target_team, distance

**Tácticos:**
- `SET_STANCE` — stance (0=Balanced, 1=Attack, 2=Defend)
- `CLEAR_OVERRIDE` — volver al AI default

---

## Arquitectura del Sistema

```
┌─── Workshop (managed) ───┐      ┌─── Tu cuenta AWS ───────────┐
│                           │      │                              │
│  Match Server (física)    │◄────►│  5 Agents en AgentCore       │
│  Agent Loop (invoca)      │      │  (uno por jugador)           │
│  Player Portal (UI)       │      │                              │
│                           │      │  Amazon Bedrock (Nova/Claude) │
└───────────────────────────┘      └──────────────────────────────┘
```

Cada agente es **independiente**: tiene su propio prompt, su propio modelo, su propio fallback. Se invocan por separado cada tick.

---

## Modelos Recomendados

Del repo oficial y la experiencia del equipo chino:

| Posición | Modelo recomendado | Razón |
|----------|-------------------|-------|
| GK | Nova Micro | Decisiones simples, velocidad máxima |
| DEF | Nova Micro o Lite | Reacciones defensivas rápidas |
| MID | Nova Pro o Nova 2 Lite | Cerebro del equipo, necesita razonar |
| FWD1 | Nova Micro o Nova 2 Lite | Decisiones de gol rápidas |
| FWD2 | Nova Lite | Balance velocidad/inteligencia |

**El equipo chino usó**: FWD/MID en `nova-2-lite` (mejor razonamiento atacante), DEF/GK en `nova-micro` (baja latencia defensiva).

**Dato clave**: en una de sus victorias 3-2, promediaron 1049ms de latencia vs 550ms del rival — ganaron con táctica, no con velocidad. Pero latencia alta es un riesgo que reduce el margen.

---

## Estructura del Prompt (4 capas oficiales)

Según el workshop, un buen prompt tiene:

### Layer 1: Identidad y Rol
```
You are a defensive midfielder on a 5v5 football team.
Your primary job is to protect the space between midfield and defense.
You are Player 2 on the home team.
```

### Layer 2: Jerarquía de Decisiones
```
When deciding what to do, follow this priority order:
1. If opponent is in scoring position → MARK the nearest threat
2. If teammate has the ball → hold position to receive a pass
3. If ball is loose in midfield → PRESS_BALL
4. If I have the ball → PASS to a teammate in better position
5. If no better option → MOVE_TO toward opponent half
```

### Layer 3: Reglas Situacionales
```
- When WINNING: Play conservatively. Hold possession.
- When LOSING: Push forward. Take more shots.
- When stamina below 30%: MOVE_TO with sprint: false
```

### Layer 4: Restricciones
```
- NEVER leave the defensive third empty
- NEVER SHOOT from beyond midfield
- NEVER sprint when stamina < 20%
```

### Anti-patrones (lo que NO hacer)

| Anti-patrón | Por qué falla |
|-------------|---|
| "Play well and try to win" | Demasiado vago, decisiones inconsistentes |
| 500 palabras de narrativa | Desperdicia tokens, no influye en decisiones |
| Tablas complejas de posicionamiento | Confunde a modelos pequeños (Micro) |

---

## Lecciones del Equipo Chino (19 matches, 72 horas)

### Hallazgos tácticos

1. **"Prompts suggest, code enforces"** — Las reglas más importantes deben ser deterministas (overrides en código), no solo texto en el prompt. El LLM ignoraba instrucciones ~40% del tiempo.

2. **Blast shot override** — Cuando el FWD está en zona de tiro con ángulo claro, el CÓDIGO dispara directamente sin consultar al LLM. Esto aumentó significativamente los goles.

3. **92-98% de tiros eran desde >45m** — Sin overrides, los agentes disparaban desde el centro del campo. Fix: "only shoot near the box" + override de código.

4. **FWDs se amontonaban en el centro** — Los heatmaps mostraron a FWD1 tirando desde la mitad del campo. Fix: "stay on your wing" + positional overrides.

5. **DEF nunca marcaba** — 207/370 comandos eran MOVE_TO, 0 eran MARK. El prompt decía "MARK when pressed" pero el LLM lo ignoraba. Fix: override determinista.

6. **0% LLM decisions (bug invisible)** — Un error de deploy hizo que los 5 agentes jugaran solo con fallback rules. Sin observabilidad, esto es indetectable.

### Hallazgos técnicos

1. **`max_tokens: 200`** — La respuesta es un JSON de 1 línea. Limitar tokens reduce latencia.

2. **`temperature: 0.2`** — Baja temperatura = decisiones más consistentes.

3. **Reset conversation history cada tick** — Sin esto, el historial acumulado infla la latencia de prefill. Latencia bajó de ~1.5s a ~0.7s.

4. **Coaching tiene solo 6 presets** — El chat del coach acepta solo: `press_high`, `shoot_on_sight`, `slow_the_tempo`, `go_all_out_attack` (y algunos más). Texto libre fue rechazado con 400.

5. **Mensajes durante replay de gol se pierden** — Hay que esperar a que el reloj se reanude.

---

## Coaching en Vivo

Desde el Player Portal durante un match:

| Situación | Instrucción |
|-----------|-------------|
| Acaban de marcar gol | `press_high` — recuperar rápido |
| Vas ganando y queda poco | `slow_the_tempo` — mantener forma |
| Vas perdiendo | `shoot_on_sight` — disparar a todo |
| Últimos minutos perdiendo | `go_all_out_attack` — todo al ataque |
| Marcaste gol con ventaja | `slow_the_tempo` — cerrar el partido |

Las instrucciones llegan en `teamChat` del game state. Los agentes con soporte de coaching (MID, DEF, FWD2 en nuestro caso) las leen y ajustan su comportamiento.

---

## Bots de Práctica (ordenados por dificultad)

| Bot | Estilo | Qué testea | Cómo ganarle |
|-----|--------|---|---|
| **Benchmark FC** | Balanced | Rendimiento general | Juego sólido, más tiros al arco |
| **Total Attack United** | Ultra agresivo | Tu defensa + contraataque | Defendé bien y contraatacá |
| **Fort Knox Athletic** | Ultra defensivo | Romper defensas bajas | Paciencia, pases y tiros |

---

## Despliegue (Día del Evento)

### Prerequisites
- Python 3.10+
- AWS CLI configurado
- `uv` instalado (para cross-compile ARM64)
- `bedrock-agentcore-starter-toolkit` instalado

### Flujo
```bash
# 1. Verificar credenciales
aws sts get-caller-identity

# 2. Desplegar los 5 agentes
AWS_DEFAULT_REGION=us-east-1 ./deploy-all.sh

# 3. Copiar los 5 ARNs del output

# 4. Ir al Player Portal → My Team → Pegar ARNs

# 5. Test de conectividad en el portal

# 6. Play practice match
```

### Redesplegar un agente específico (iteración rápida)
```bash
./deploy-all.sh ai-mid   # solo ~1 minuto
```

---

## El Loop Ganador

```
Observar partido → Identificar problema → Editar prompt → Redesplegar → Repetir
```

Cada iteración debería tomar ~3 minutos (1 min edit, 1 min deploy, 1 min test).

---

## Ventajas Competitivas que Ya Tenemos

1. ✅ Código listo para desplegar (ahorra ~1.5h del workshop)
2. ✅ Modelos correctos por posición (Micro/Lite/Pro)
3. ✅ Prompts calibrados por capacidad del modelo
4. ✅ Soporte de coaching (teamChat) activado
5. ✅ Fallback rule-based funcional (el equipo nunca se congela)
6. ✅ Conocimiento previo de las reglas y mecánicas

---

## Qué Hacer en el Evento (Plan de 4h)

| Tiempo | Acción |
|--------|--------|
| 0-15min | Setup: clonar repo, configurar credenciales |
| 15-30min | Deploy con `deploy-all.sh` |
| 30-45min | Registrar ARNs en Player Portal, test conectividad |
| 45-60min | 1er practice match vs Benchmark FC |
| 60-90min | Analizar, ajustar prompts, redesplegar |
| 90-120min | Practice vs Total Attack + Fort Knox |
| 120-180min | Iterar prompts agresivamente basado en resultados |
| 180-210min | Explorar overrides, memory, o gateway si hay tiempo |
| 210-240min | Torneo oficial contra otros participantes |

---

## Referencias

- [Workshop oficial](https://catalog.workshops.aws/agentic-football/en-US)
- [Repo oficial AWS](https://github.com/aws-samples/sample-ai-possibilities/tree/main/agentic-football-sample-agents)
- [Blog técnico Strands](https://strandsagents.com/blog/inside-agentic-football-cup/)
- [72 Hours de Agentic Football (equipo chino)](https://medium.com/@shi.pan218/72-hours-of-agentic-football-from-aws-agentcore-harness-to-a-full-observability-toolchain-c57ca58abb8b)
- [Repo del equipo chino](https://github.com/peterpanstechland/sample-ai-possibilities/tree/football-workshop/agentic-football-sample-agents)
- [agenticfootballcup.com](https://agenticfootballcup.com/)
- [Strands Agents SDK](https://strandsagents.com/)
- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/)
