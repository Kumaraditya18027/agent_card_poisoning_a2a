# agents/greeting_agent/__main__.py

import logging
import click

from server.server import A2AServer
from models.agent import (
    AgentCard,
    AgentCapabilities,
    AgentSkill
)
from agents.greeting_agent.task_manager import GreetingTaskManager
from agents.greeting_agent.agent import GreetingAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.command()
@click.option(
    "--host",
    default="localhost",
    help="Host to bind GreetingAgent server to"
)
@click.option(
    "--port",
    default=10001,
    help="Port for GreetingAgent server"
)
def main(host: str, port: int):
    """
    Launches the GreetingAgent A2A server.

    Args:
        host (str): Hostname or IP to bind to (default: localhost)
        port (int): TCP port to listen on (default: 10001)
    """
    print(f"\n Starting GreetingAgent on http://{host}:{port}/\n")

    capabilities = AgentCapabilities(streaming=False)

    skill = AgentSkill(
        id="greet",
        name="Greeting Tool",
        description="Returns a greeting based on the current time of day",
        tags=["greeting", "time", "hello"],
        examples=["Greet me", "Say hello based on time"]
    )

    agent_card = AgentCard(
        name="GreetingAgent",
        description="Agent that greets you based on the current time",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=capabilities,
        skills=[skill]
    )

    greeting_agent = GreetingAgent()
    task_manager = GreetingTaskManager(agent=greeting_agent)

    server = A2AServer(
        host=host,
        port=port,
        agent_card=agent_card,
        task_manager=task_manager
    )
    server.start()

if __name__ == "__main__":
    main()
