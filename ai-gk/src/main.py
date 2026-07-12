"""AI Soccer Goalkeeper Agent — Player 0. Nova Micro (simple, fast decisions)."""

import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agent_base import create_agent, create_invoke_handler
from fallback import build_fallback, GK_CONFIG

app = BedrockAgentCoreApp()

MY_PLAYER_ID = 0
POSITION_LABEL = "GK"

# Nova Micro prompt: SHORT, direct if/then rules. No ambiguity.
SYSTEM_PROMPT = f"""You control player {MY_PLAYER_ID} (Goalkeeper) in 5v5 soccer. Return ONE JSON command.

RULES:
- If you have the ball → GK_DISTRIBUTE to player 1 or 2 (method THROW)
- If ball is loose within 15 units of you → INTERCEPT (aggressive true)
- Otherwise → MOVE_TO between ball and goal center (x=-52, y=ball_y * 0.4)

FIELD: x=-55 to +55. Your goal at x=-55. Never go past x=-35.

COMMANDS: GK_DISTRIBUTE(target_player_id, method:THROW|KICK), INTERCEPT(aggressive:bool), MOVE_TO(target_x, target_y, sprint:bool)

FORMAT: [{{"commandType":"GK_DISTRIBUTE","playerId":{MY_PLAYER_ID},"parameters":{{"target_player_id":1,"method":"THROW"}},"duration":0}}]
Return ONLY the JSON array."""

fallback_commands = build_fallback(GK_CONFIG)
agent = create_agent(SYSTEM_PROMPT, model_id="us.amazon.nova-micro-v1:0")
create_invoke_handler(app, agent, MY_PLAYER_ID, POSITION_LABEL, fallback_commands, fallback_cfg=GK_CONFIG)

if __name__ == "__main__":
    app.run()
