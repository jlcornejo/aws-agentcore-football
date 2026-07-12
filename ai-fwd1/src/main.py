"""AI Soccer Forward 1 Agent — Player 3. Nova Micro (simple, fast decisions)."""

import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agent_base import create_agent, create_invoke_handler
from fallback import build_fallback, FWD1_CONFIG

app = BedrockAgentCoreApp()

MY_PLAYER_ID = 3
POSITION_LABEL = "FWD1"

# Nova Micro prompt: SHORT, direct if/then rules. No ambiguity.
SYSTEM_PROMPT = f"""You control player {MY_PLAYER_ID} (Forward 1, left striker) in 5v5 soccer. Return ONE JSON command.

RULES (follow in order):
1. If you have the ball AND distance to opponent goal < 25 → SHOOT (aim_location TR, power 0.9)
2. If you have the ball AND not in range → MOVE_TO toward opponent goal (target_x=40, target_y=-5, sprint true)
3. If teammate has the ball → MOVE_TO open space (target_x=30, target_y=-10, sprint true)
4. If opponent has the ball nearby → PRESS_BALL (intensity 0.7)
5. Otherwise → MOVE_TO attacking position (target_x=20, target_y=-8, sprint false)

FIELD: x=-55 to +55. Opponent goal at x=+55. Stay on LEFT side (negative y).

COMMANDS: SHOOT(aim_location:TL|TR|BL|BR|CENTER, power:0.0-1.0), MOVE_TO(target_x, target_y, sprint:bool), PASS(target_player_id, type:GROUND|THROUGH), PRESS_BALL(intensity:0.0-1.0)

FORMAT: [{{"commandType":"SHOOT","playerId":{MY_PLAYER_ID},"parameters":{{"aim_location":"TR","power":0.9}},"duration":0}}]
Return ONLY the JSON array."""

fallback_commands = build_fallback(FWD1_CONFIG)
agent = create_agent(SYSTEM_PROMPT, model_id="us.amazon.nova-micro-v1:0")
create_invoke_handler(app, agent, MY_PLAYER_ID, POSITION_LABEL, fallback_commands, fallback_cfg=FWD1_CONFIG)

if __name__ == "__main__":
    app.run()
