"""AgentCore Code Interpreter tool for tactical calculations.

Provides a @tool-decorated function that agents can use to run Python code
in a secure sandbox for advanced tactical analysis (geometry, interception
vectors, optimal positioning, etc.).

Usage in an agent:
    from code_interpreter_tool import tactical_compute
    agent = Agent(tools=[tactical_compute], ...)

The tool is designed to be LOW-IMPACT: agents only invoke it when they
need complex multi-step calculations that can't be done in a single
JSON decision. The sandbox has numpy available.

Environment:
    AWS_DEFAULT_REGION — region for Code Interpreter (default: us-east-1)
    CODE_INTERPRETER_ENABLED — set to "true" to enable (default: false)
"""

import os
import logging
from strands import tool

logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
CODE_INTERPRETER_ENABLED = os.environ.get("CODE_INTERPRETER_ENABLED", "false").lower() == "true"


@tool
def tactical_compute(code: str) -> str:
    """Execute Python code for tactical analysis in a secure sandbox.

    Use this ONLY for complex multi-step calculations that need numpy,
    such as optimal shot angles, interception probability matrices, or
    positional heat analysis. numpy is available in the sandbox.

    For simple decisions (move, pass, shoot), decide directly without this tool.

    Args:
        code: Python code to execute. Must print() results.
    """
    if not CODE_INTERPRETER_ENABLED:
        return "Code Interpreter disabled. Make your decision directly."

    try:
        from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

        code_client = CodeInterpreter(REGION)
        code_client.start()

        try:
            response = code_client.invoke("executeCode", {
                "language": "python",
                "code": code,
            })

            results = []
            for event in response["stream"]:
                if "result" in event:
                    for item in event["result"].get("content", []):
                        if item["type"] == "text":
                            results.append(item["text"])

            output = "\n".join(results)
            logger.info(f"Code Interpreter executed successfully: {output[:100]}")
            return output or "Code executed, no output."

        finally:
            code_client.stop()

    except ImportError:
        logger.warning("bedrock_agentcore.tools.code_interpreter_client not available")
        return "Code Interpreter not available. Make your decision directly."
    except Exception as e:
        logger.error(f"Code Interpreter error: {e}")
        return f"Execution failed: {e}. Make your decision directly."
