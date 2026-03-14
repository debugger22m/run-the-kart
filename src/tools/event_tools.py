"""
Event discovery tools for the EventAgent.

Web search is the sole event-discovery mechanism. The Anthropic-hosted
web_search_20250305 tool is handled server-side — no client handler required.
"""

EVENT_TOOLS = [
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 5,
    },
]
