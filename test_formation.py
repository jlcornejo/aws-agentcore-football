"""Test that only nearest player presses, others hold formation."""
import sys
sys.path.insert(0, "lib")
from fallback import build_fallback, FWD1_CONFIG, FWD2_CONFIG, DEF_CONFIG, MID_CONFIG

game_state = {
    "ball": {"position": {"x": 0, "y": 5}, "possessionAgentId": "agentId_2"},
    "players": [
        {"agentId": "agentId_0", "teamCode": "home", "position": {"x": -52, "y": 0}},
        {"agentId": "agentId_1", "teamCode": "home", "position": {"x": -20, "y": -5}},
        {"agentId": "agentId_2", "teamCode": "home", "position": {"x": -10, "y": 3}},
        {"agentId": "agentId_3", "teamCode": "home", "position": {"x": 5, "y": -8}},
        {"agentId": "agentId_4", "teamCode": "home", "position": {"x": 5, "y": 10}},
        {"agentId": "agentId_0", "teamCode": "away", "position": {"x": 48, "y": 0}},
        {"agentId": "agentId_1", "teamCode": "away", "position": {"x": 15, "y": -3}},
        {"agentId": "agentId_2", "teamCode": "away", "position": {"x": 0, "y": 5}},
        {"agentId": "agentId_3", "teamCode": "away", "position": {"x": -10, "y": -10}},
        {"agentId": "agentId_4", "teamCode": "away", "position": {"x": -10, "y": 10}},
    ],
}

print("Scenario: Opponent has ball at (0,5). Who presses?")
print("=" * 50)
configs = [(1, "DEF", DEF_CONFIG), (2, "MID", MID_CONFIG), (3, "FWD1", FWD1_CONFIG), (4, "FWD2", FWD2_CONFIG)]
pressers = 0
for pid, label, cfg in configs:
    fb = build_fallback(cfg)
    cmds = fb(game_state, 0, pid)
    cmd = cmds[0]
    ct = cmd["commandType"]
    params = cmd.get("parameters", {})
    marker = " <-- PRESSES!" if ct == "PRESS_BALL" else ""
    if ct == "PRESS_BALL":
        pressers += 1
    print(f"  {label}(P{pid}): {ct:12} {str(params)[:40]}{marker}")

print(f"\nPressers: {pressers}")
if pressers <= 1:
    print("OK - Only 1 player presses, others hold shape")
else:
    print("PROBLEM - Multiple players chasing the ball!")
