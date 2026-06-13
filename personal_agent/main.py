"""Personal Agent – A2A entry point (port 9001)."""

from google.adk.a2a.utils.agent_to_a2a import to_a2a

from agent import root_agent

app = to_a2a(root_agent, host="0.0.0.0", port=9001)
