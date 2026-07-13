"""AI Soccer Forward 1 Agent — Player 3. Nova Micro (simple, fast decisions)."""

import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agent_base import create_agent, create_invoke_handler
from fallback import build_fallback, FWD1_CONFIG

app = BedrockAgentCoreApp()

MY_PLAYER_ID = 3
POSITION_LABEL = "FWD1"

SYSTEM_PROMPT = f"""You control player {MY_PLAYER_ID} (Forward 1, left striker) in 5v5 soccer. Return ONE JSON command.

RULES (follow in order):
1. If you have the ball AND distance to opponent goal < 25 → SHOOT (aim_location CENTER, power 0.9)
2. If you have the ball AND not in range → PASS to the teammate closest to opponent goal (type THROUGH)
3. If teammate has the ball → MOVE_TO open space ahead of the ball (x=ball_x+15, y=-10, sprint true)
4. If opponent has the ball AND within 8 units of you → INTERCEPT (aggressive true)
5. Otherwise → MOVE_TO attacking position (target_x=20, target_y=-8, sprint false)

NEVER use PRESS_BALL. Use INTERCEPT or MOVE_TO instead.

FIELD: x=-55 to +55. Opponent goal at x=+55. Stay LEFT (negative y).

COMMANDS: SHOOT(aim_location:TL|TR|BL|BR|CENTER, power), MOVE_TO(target_x, target_y, sprint), PASS(target_player_id, type:GROUND|THROUGH), INTERCEPT(aggressive)

FORMAT: [{{"commandType":"SHOOT","playerId":{MY_PLAYER_ID},"parameters":{{"aim_location":"CENTER","power":0.9}},"duration":0}}]
Return ONLY the JSON array."""

fallback_commands = build_fallback(FWD1_CONFIG)
agent = create_agent(SYSTEM_PROMPT, model_id="us.amazon.nova-micro-v1:0")
create_invoke_handler(app, agent, MY_PLAYER_ID, POSITION_LABEL, fallback_commands, fallback_cfg=FWD1_CONFIG)

if __name__ == "__main__":
    app.run()
