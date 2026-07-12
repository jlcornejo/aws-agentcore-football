"""Local test for MID agent."""
import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from test_helpers import mock_agentcore, GAME_STATE, TEAM_ID
mock_agentcore()
from state import summarize_state
from parsing import parse_commands
from main import fallback_commands, MY_PLAYER_ID, POSITION_LABEL, SYSTEM_PROMPT

def test_summarize():
    print(f"=== STATE SUMMARY ({POSITION_LABEL}, player {MY_PLAYER_ID}) ===")
    print(summarize_state(GAME_STATE, TEAM_ID, MY_PLAYER_ID, POSITION_LABEL))
    print()

def test_fallback():
    print(f"=== FALLBACK ({POSITION_LABEL}) ===")
    cmds = fallback_commands(GAME_STATE, TEAM_ID, MY_PLAYER_ID)
    for c in cmds:
        ok = "OK" if c["playerId"] == MY_PLAYER_ID and c["teamId"] == TEAM_ID else "WRONG"
        print(f"  [{ok}] P{c['playerId']} T{c['teamId']}: {c['commandType']} {c.get('parameters', {})}")
    print()

def test_llm():
    print(f"=== LLM TEST ({POSITION_LABEL}) ===")
    from strands import Agent
    from strands.models import BedrockModel
    model = BedrockModel(model_id="us.amazon.nova-micro-v1:0")
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT)
    summary = summarize_state(GAME_STATE, TEAM_ID, MY_PLAYER_ID, POSITION_LABEL)
    print(f"Sending to Nova Micro ({len(summary)} chars)...")
    response = agent(summary)
    response_text = str(response)
    print(f"Raw response: {response_text[:300]}\n")
    cmds = parse_commands(response_text, TEAM_ID, MY_PLAYER_ID)
    print(f"Parsed {len(cmds)} commands:")
    for c in cmds:
        print(f"  P{c.get('playerId')}: {c.get('commandType')} {c.get('parameters', {})}")
    status = "PASSED" if cmds and all(c["playerId"] == MY_PLAYER_ID for c in cmds) else "FAILED"
    print(f"\nLLM test {status}")

if __name__ == "__main__":
    test_summarize()
    test_fallback()
    if "--llm" in sys.argv:
        test_llm()
    else:
        print("Skipping LLM test. Run with --llm to test against Bedrock.")
