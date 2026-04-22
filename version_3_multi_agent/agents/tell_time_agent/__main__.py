# Purpose:
# This is the main script that starts your TellTimeAgent server.
# It:
# - Declares the agent’s capabilities and skills
# - Sets up the A2A server with a task manager and agent
# - Starts listening on a specified host and port
#
# This script can be run directly from the command line:
#     python -m agents.google_adk
# =============================================================================

# Your custom A2A server class
from server.server import A2AServer

# Models for describing agent capabilities and metadata
from models.agent import AgentCard, AgentCapabilities, AgentSkill

# Task manager and agent logic
from agents.tell_time_agent.task_manager import AgentTaskManager
from agents.tell_time_agent.agent import TellTimeAgent

# CLI and logging support
import click
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.command()
@click.option("--host", default="localhost", help="Host to bind the server to")
@click.option("--port", default=10002, help="Port number for the server")
def main(host, port):
    """
    This function sets up everything needed to start the agent server.
    You can run it via: `python -m agents.google_adk --host 0.0.0.0 --port 12345`
    """

 what this agent can do – in this case, it does NOT support streaming
    capabilities = AgentCapabilities(streaming=False)

    skill = AgentSkill(
        id="tell_time",
        name="Tell Time Tool",
        description="Replies with the current time",
        tags=["time"],
        examples=["What time is it?", "Tell me the current time"]
    )

    agent_card = AgentCard(
        name="TellTimeAgent",
        description="This agent replies with the current system time.",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=TellTimeAgent.SUPPORTED_CONTENT_TYPES,
        defaultOutputModes=TellTimeAgent.SUPPORTED_CONTENT_TYPES,
        capabilities=capabilities,                          # Supported features (e.g., streaming)
        skills=[skill]
    )

    # - the given host/port
    # - this agent’s metadata
    # - a task manager that runs the TellTimeAgent
    server = A2AServer(
        host=host,
        port=port,
        agent_card=agent_card,
        task_manager=AgentTaskManager(agent=TellTimeAgent())
    )

    server.start()

if __name__ == "__main__":
    main()
