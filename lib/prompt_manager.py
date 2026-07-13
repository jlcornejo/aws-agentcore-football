"""
Prompt Manager — Carga prompts desde AWS Bedrock Prompt Management.

En lugar de hardcodear el SYSTEM_PROMPT en main.py, cada agente consulta
Bedrock Prompt Management para obtener su prompt. Esto permite actualizar
la táctica sin re-deploy.

Estrategia de cache:
- Al arrancar el agente, carga el prompt y lo cachea.
- Opcionalmente, refresca cada N invocaciones (configurable).
- Si falla, usa el prompt local como fallback.
"""

import os
import time
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
REFRESH_INTERVAL_SECONDS = int(os.environ.get("PROMPT_REFRESH_INTERVAL", "60"))
PROMPT_VERSION = os.environ.get("PROMPT_VERSION", "DRAFT")  # "DRAFT" or version number

# ---------------------------------------------------------------------------
# Bedrock Agent client (singleton)
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agent", region_name=REGION)
    return _client


# ---------------------------------------------------------------------------
# Prompt cache
# ---------------------------------------------------------------------------

class PromptCache:
    """Cache a prompt with TTL-based refresh."""

    def __init__(self, prompt_id: str, fallback_prompt: str, version: str = PROMPT_VERSION):
        self.prompt_id = prompt_id
        self.fallback_prompt = fallback_prompt
        self.version = version
        self._cached_prompt: Optional[str] = None
        self._last_fetch: float = 0

    def get_prompt(self) -> str:
        """Return the cached prompt, refreshing if TTL expired."""
        now = time.time()
        if self._cached_prompt and (now - self._last_fetch) < REFRESH_INTERVAL_SECONDS:
            return self._cached_prompt

        try:
            prompt_text = fetch_prompt(self.prompt_id, self.version)
            if prompt_text:
                self._cached_prompt = prompt_text
                self._last_fetch = now
                logger.info(f"Prompt refreshed from Bedrock: {self.prompt_id}")
                return prompt_text
        except Exception as e:
            logger.warning(f"Failed to fetch prompt {self.prompt_id}: {e}")

        # Fallback: use cached or local prompt
        if self._cached_prompt:
            return self._cached_prompt
        logger.warning(f"Using local fallback prompt for {self.prompt_id}")
        return self.fallback_prompt


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def fetch_prompt(prompt_id: str, version: str = "DRAFT") -> Optional[str]:
    """
    Fetch a prompt from Bedrock Prompt Management.

    Args:
        prompt_id: The prompt identifier (ID or ARN)
        version: "DRAFT" or a version number string

    Returns:
        The prompt text, or None if not found.
    """
    client = _get_client()

    kwargs = {"promptIdentifier": prompt_id}
    if version and version != "DRAFT":
        kwargs["promptVersion"] = version

    response = client.get_prompt(**kwargs)

    # Extract the text from the first variant
    variants = response.get("variants", [])
    if not variants:
        logger.warning(f"Prompt {prompt_id} has no variants")
        return None

    variant = variants[0]
    template_config = variant.get("templateConfiguration", {})
    text_config = template_config.get("text", {})
    prompt_text = text_config.get("text")

    return prompt_text


def list_prompts(prefix: str = "football-") -> list[dict]:
    """List all prompts with a given prefix."""
    client = _get_client()
    prompts = []

    paginator = client.get_paginator("list_prompts")
    for page in paginator.paginate():
        for summary in page.get("promptSummaries", []):
            if summary["name"].startswith(prefix):
                prompts.append({
                    "id": summary["id"],
                    "name": summary["name"],
                    "description": summary.get("description", ""),
                    "updatedAt": summary.get("updatedAt"),
                })

    return prompts


# ---------------------------------------------------------------------------
# Convenience: get prompt ID from environment or naming convention
# ---------------------------------------------------------------------------

def get_prompt_id_for_position(position_label: str) -> Optional[str]:
    """
    Resolve the Bedrock prompt ID for a given position.

    Lookup order:
    1. Environment variable: PROMPT_ID_<POSITION> (e.g. PROMPT_ID_DEF)
    2. Environment variable: PROMPT_ID (generic, single prompt for all)
    3. prompt_ids.py config file (generated by sync-prompts.py)
    4. None (caller should use local fallback)
    """
    env_key = f"PROMPT_ID_{position_label.upper()}"
    prompt_id = os.environ.get(env_key)
    if prompt_id:
        return prompt_id

    prompt_id = os.environ.get("PROMPT_ID")
    if prompt_id:
        return prompt_id

    # Fallback to config file
    try:
        from prompt_ids import PROMPT_IDS
        return PROMPT_IDS.get(position_label.upper())
    except ImportError:
        return None
