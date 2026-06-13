"""CS Agent – A2A entry point (port 9002).

Builds the KB index first (readiness gate), then serves the agent.
Run: uvicorn main:app --host 0.0.0.0 --port 9002
"""

import os

from ingest import build_index

build_index()  # Readiness gate: index must exist before serving any requests

from agent import root_agent  # noqa: E402  (import after readiness gate)

from google.adk.a2a.utils.agent_to_a2a import to_a2a  # noqa: E402

app = to_a2a(root_agent, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "9002")))
