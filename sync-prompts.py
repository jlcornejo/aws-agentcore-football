#!/usr/bin/env python3
"""
sync-prompts.py — Sincroniza los prompts locales a AWS Bedrock Prompt Management.

Uso:
    python sync-prompts.py                  # Crear/actualizar TODOS los prompts
    python sync-prompts.py ai-def           # Solo el defensor
    python sync-prompts.py --list           # Listar prompts existentes
    python sync-prompts.py --version ai-gk  # Crear versión publicada del GK

Esto permite cambiar la táctica del equipo SIN hacer re-deploy de los agentes.
Solo actualizar el prompt en Bedrock → el agente lo carga dinámicamente.
"""

import argparse
import importlib.util
import json
import os
import re
import sys

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
PROMPT_PREFIX = "football-"

AGENTS = {
    "ai-gk": {"player_id": 0, "label": "GK", "description": "Goalkeeper agent"},
    "ai-def": {"player_id": 1, "label": "DEF", "description": "Defender agent"},
    "ai-mid": {"player_id": 2, "label": "MID", "description": "Midfielder agent"},
    "ai-fwd1": {"player_id": 3, "label": "FWD1", "description": "Forward 1 agent"},
    "ai-fwd2": {"player_id": 4, "label": "FWD2", "description": "Forward 2 agent"},
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_client():
    return boto3.client("bedrock-agent", region_name=REGION)


def prompt_name(agent_key: str) -> str:
    """Generate consistent prompt name: football-ai-gk, football-ai-def, etc."""
    return f"{PROMPT_PREFIX}{agent_key}"


def extract_system_prompt(agent_dir: str) -> str:
    """Extract SYSTEM_PROMPT from main.py using simple regex (avoids import issues)."""
    main_py = os.path.join(SCRIPT_DIR, agent_dir, "src", "main.py")

    if not os.path.exists(main_py):
        raise FileNotFoundError(f"Not found: {main_py}")

    with open(main_py, "r") as f:
        content = f.read()

    # Extract the SYSTEM_PROMPT = f"""...""" block
    # Try triple-quote f-string first
    match = re.search(
        r'SYSTEM_PROMPT\s*=\s*f?"""(.*?)"""',
        content,
        re.DOTALL,
    )
    if not match:
        match = re.search(
            r"SYSTEM_PROMPT\s*=\s*f?'''(.*?)'''",
            content,
            re.DOTALL,
        )
    if not match:
        raise ValueError(f"Could not extract SYSTEM_PROMPT from {main_py}")

    prompt_text = match.group(1)

    # Resolve f-string interpolations for MY_PLAYER_ID
    # Extract MY_PLAYER_ID from the same file
    pid_match = re.search(r"MY_PLAYER_ID\s*=\s*(\d+)", content)
    player_id = int(pid_match.group(1)) if pid_match else 0

    # Replace {MY_PLAYER_ID} with the actual value
    prompt_text = prompt_text.replace("{MY_PLAYER_ID}", str(player_id))
    # Replace escaped braces {{}} → {} (from f-string)
    prompt_text = prompt_text.replace("{{", "{").replace("}}", "}")

    return prompt_text.strip()


def find_existing_prompt(client, name: str) -> dict | None:
    """Find an existing prompt by name, return its summary or None."""
    paginator = client.get_paginator("list_prompts")
    for page in paginator.paginate():
        for summary in page.get("promptSummaries", []):
            if summary["name"] == name:
                return summary
    return None


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def create_or_update_prompt(client, agent_key: str) -> dict:
    """Create or update a prompt in Bedrock Prompt Management."""
    info = AGENTS[agent_key]
    name = prompt_name(agent_key)
    prompt_text = extract_system_prompt(agent_key)

    variant = {
        "name": "default",
        "templateType": "TEXT",
        "templateConfiguration": {
            "text": {
                "text": prompt_text,
                "inputVariables": [],
            }
        },
    }

    existing = find_existing_prompt(client, name)

    if existing:
        # Update existing prompt
        prompt_id = existing["id"]
        print(f"  📝 Updating existing prompt: {name} (id={prompt_id})")
        response = client.update_prompt(
            promptIdentifier=prompt_id,
            name=name,
            description=f"Football Cup - {info['description']}",
            variants=[variant],
        )
    else:
        # Create new prompt
        print(f"  🆕 Creating new prompt: {name}")
        response = client.create_prompt(
            name=name,
            description=f"Football Cup - {info['description']}",
            variants=[variant],
        )

    prompt_id = response["id"]
    print(f"  ✅ Prompt synced: {name} → id={prompt_id}")
    return response


def create_version(client, agent_key: str) -> dict:
    """Create a published version of a prompt (snapshot)."""
    name = prompt_name(agent_key)
    existing = find_existing_prompt(client, name)

    if not existing:
        print(f"  ❌ Prompt {name} not found. Run sync first.")
        sys.exit(1)

    prompt_id = existing["id"]
    response = client.create_prompt_version(promptIdentifier=prompt_id)
    version = response.get("version", "?")
    print(f"  📌 Version created: {name} → v{version}")
    return response


def list_prompts(client):
    """List all football prompts."""
    print("\n  Existing Football prompts in Bedrock:")
    print("  " + "─" * 60)

    paginator = client.get_paginator("list_prompts")
    found = False
    for page in paginator.paginate():
        for summary in page.get("promptSummaries", []):
            if summary["name"].startswith(PROMPT_PREFIX):
                found = True
                print(f"  • {summary['name']}")
                print(f"    ID: {summary['id']}")
                print(f"    Updated: {summary.get('updatedAt', 'N/A')}")
                print()

    if not found:
        print("  (ningún prompt encontrado con prefijo 'football-')")
        print("  Ejecuta: python sync-prompts.py  para crearlos")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sync prompts to AWS Bedrock Prompt Management"
    )
    parser.add_argument(
        "agents",
        nargs="*",
        help="Agent(s) to sync (e.g. ai-gk ai-def). Default: all.",
    )
    parser.add_argument(
        "--list", action="store_true", help="List existing prompts"
    )
    parser.add_argument(
        "--version", metavar="AGENT",
        help="Create a published version for an agent prompt",
    )
    parser.add_argument(
        "--show", metavar="AGENT",
        help="Show the extracted prompt text for an agent (local, no AWS call)",
    )

    args = parser.parse_args()
    client = get_client()

    if args.list:
        list_prompts(client)
        return

    if args.show:
        if args.show not in AGENTS:
            print(f"❌ Unknown agent: {args.show}. Options: {list(AGENTS.keys())}")
            sys.exit(1)
        prompt_text = extract_system_prompt(args.show)
        print(f"\n{'='*60}")
        print(f"  SYSTEM_PROMPT for {args.show}")
        print(f"{'='*60}\n")
        print(prompt_text)
        return

    if args.version:
        if args.version not in AGENTS:
            print(f"❌ Unknown agent: {args.version}. Options: {list(AGENTS.keys())}")
            sys.exit(1)
        create_version(client, args.version)
        return

    # Default: sync prompts
    targets = args.agents if args.agents else list(AGENTS.keys())

    print("=" * 50)
    print("  ⚽ Syncing prompts to Bedrock Prompt Management")
    print("=" * 50)
    print()

    results = {}
    for agent_key in targets:
        if agent_key not in AGENTS:
            print(f"  ⚠️  Unknown agent: {agent_key}, skipping")
            continue
        try:
            resp = create_or_update_prompt(client, agent_key)
            results[agent_key] = resp["id"]
        except Exception as e:
            print(f"  ❌ {agent_key}: {e}")
            results[agent_key] = None

    # Print summary with env vars to set
    print()
    print("=" * 50)
    print("  📋 Environment variables for your agents:")
    print("=" * 50)
    print()
    for agent_key, prompt_id in results.items():
        if prompt_id:
            label = AGENTS[agent_key]["label"]
            print(f"  PROMPT_ID_{label}={prompt_id}")

    # Write prompt_ids.py config file
    ids_file = os.path.join(SCRIPT_DIR, "lib", "prompt_ids.py")
    with open(ids_file, "w") as f:
        f.write('"""\nPrompt IDs de Bedrock Prompt Management.\n\n')
        f.write("Estos IDs son estables (no cambian a menos que borres y recrees el prompt).\n")
        f.write("Se usan para cargar dinámicamente el SYSTEM_PROMPT de cada agente sin re-deploy.\n\n")
        f.write('Generados por: python sync-prompts.py\n"""\n\n')
        f.write("PROMPT_IDS = {\n")
        for agent_key, prompt_id in results.items():
            if prompt_id:
                label = AGENTS[agent_key]["label"]
                f.write(f'    "{label}": "{prompt_id}",\n')
        f.write("}\n")
    print()
    print(f"  ✏️  Actualizado: lib/prompt_ids.py")
    print()
    print("  💡 Ahora puedes editar el prompt desde la consola de Bedrock")
    print("     o re-ejecutar este script, y el agente lo tomará en vivo.")


if __name__ == "__main__":
    main()
