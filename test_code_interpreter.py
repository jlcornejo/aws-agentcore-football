#!/usr/bin/env python3
"""
Test AgentCore Code Interpreter integration — pre-game tactical analysis.

Runs a quick tactical calculation using Code Interpreter to verify the
integration works. This uses the DIRECT API (no model, no agentic loop)
to validate the Code Interpreter badge requirement.

Usage:
    python test_code_interpreter.py

Requires:
    - AWS credentials configured
    - bedrock-agentcore package installed
    - Code Interpreter access in your region
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

# Tactical analysis code to run in the sandbox
TACTICAL_CODE = """
import math

# Field dimensions
FIELD_X = (-55, 55)
FIELD_Y = (-35, 35)

# Team positions (HOME, attacks toward +x)
players = {
    'GK': (-48, 0),
    'DEF': (-22, 0),
    'MID': (0, 0),
    'FWD1': (18, -8),
    'FWD2': (18, 8),
}

# Opponent goal
OPP_GOAL = (55, 0)

# Calculate shot angles and distances for each attacking player
print("=== Pre-Game Tactical Analysis ===")
print(f"{'Player':<6} {'Dist to Goal':<14} {'Angle (deg)':<12} {'Shot Zone'}")
print("-" * 50)

for name, pos in players.items():
    dx = OPP_GOAL[0] - pos[0]
    dy = OPP_GOAL[1] - pos[1]
    dist = math.sqrt(dx**2 + dy**2)
    angle = math.degrees(math.atan2(abs(dy), dx))
    
    if dist < 25:
        zone = "DANGER ZONE"
    elif dist < 40:
        zone = "SHOOTING RANGE"
    else:
        zone = "TOO FAR"
    
    print(f"{name:<6} {dist:<14.1f} {angle:<12.1f} {zone}")

# Calculate optimal pressing trigger distance
print("\\n=== Pressing Trigger Analysis ===")
avg_sprint_speed = 4.5  # units per tick
ticks_to_close = {name: math.sqrt((pos[0]-0)**2 + (pos[1]-0)**2) / avg_sprint_speed 
                  for name, pos in players.items()}

for name, ticks in sorted(ticks_to_close.items(), key=lambda x: x[1]):
    print(f"  {name}: {ticks:.1f} ticks to reach center")

print("\\n✅ Analysis complete — Code Interpreter working!")
"""


def main():
    print("⚽ AgentCore Code Interpreter — Tactical Analysis Test")
    print("=" * 55)
    print(f"  Region: {REGION}")
    print()

    try:
        from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

        print("  Starting Code Interpreter session...")
        code_client = CodeInterpreter(REGION)
        code_client.start()

        try:
            print("  Executing tactical analysis...\n")
            response = code_client.invoke("executeCode", {
                "language": "python",
                "code": TACTICAL_CODE,
            })

            for event in response["stream"]:
                if "result" in event:
                    for item in event["result"].get("content", []):
                        if item["type"] == "text":
                            print(item["text"])

        finally:
            code_client.stop()
            print("\n  Session stopped.")

    except ImportError:
        print("  ❌ bedrock_agentcore.tools.code_interpreter_client not installed.")
        print("  Install: pip install bedrock-agentcore")
        sys.exit(1)
    except Exception as e:
        print(f"  ❌ Error: {e}")
        print("  Make sure you have valid AWS credentials and Code Interpreter access.")
        sys.exit(1)


if __name__ == "__main__":
    main()
