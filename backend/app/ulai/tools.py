import json
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

# The model only needs the gist; a huge response would blow its context.
MAX_RESULT_BYTES = 16_000


async def run_tool(http: httpx.AsyncClient, tool: dict, args: dict[str, Any], call_context: dict) -> dict:
    """Calls the tool's webhook and returns what the model should hear back. Never raises."""
    method = tool.get("method", "POST")
    headers = {"User-Agent": "ulai-voice-studio", **(tool.get("headers") or {})}
    timeout = tool.get("timeout_seconds", 10)
    try:
        if method == "GET":
            params = {k: v if isinstance(v, str) else json.dumps(v) for k, v in args.items()}
            resp = await http.get(tool["url"], params=params, headers=headers, timeout=timeout)
        else:
            body = {"arguments": args, "call": call_context}
            resp = await http.post(tool["url"], json=body, headers=headers, timeout=timeout)
    except httpx.TimeoutException:
        return {"error": f"The {tool['name']} service took too long to respond."}
    except httpx.HTTPError as err:
        log.warning("tool %s failed: %s", tool["name"], err)
        return {"error": f"The {tool['name']} service could not be reached."}

    text = resp.text[:MAX_RESULT_BYTES]
    if resp.status_code >= 400:
        return {"error": f"The {tool['name']} service returned an error ({resp.status_code}).", "body": text}
    try:
        data = json.loads(text)
    except ValueError:
        return {"result": text}
    return data if isinstance(data, dict) else {"result": data}
