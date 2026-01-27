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

    print(f"\n🚀 Starting GreetingAgent on http://{host}:{port}/\n")

    # It will always send a single, complete reply.
    capabilities = AgentCapabilities(streaming=False)

    # - id: unique identifier for the skill
    # - name: human-readable name
    # - description: what this skill does
    # - tags: keywords for discovery or categorization
    # - examples: sample user inputs to illustrate the skill
    skill = AgentSkill(
        id="greet",
        name="Greeting Tool",
        description="Returns a greeting based on the current time of day",
        tags=["greeting", "time", "hello"],
        examples=["Greet me", "Say hello based on time"]
    )

    # from "/.well-known/agent.json". It describes:
    # - name, description, URL, version
    # - supported input/output modes
    # - capabilities and skills
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
    # A2AServer wires up:
    # - HTTP routes (POST "/" for tasks, GET "/.well-known/agent.json" for discovery)
    # - our AgentCard metadata
    # - the TaskManager that handles incoming requests
    server = A2AServer(
        host=host,
        port=port,
        agent_card=agent_card,
        task_manager=task_manager
    )
    server.start()  # Blocks here, serving requests until the process is killed
# Ensures `main()` only runs when this script is executed directly,
# not when it’s imported as a module.
if __name__ == "__main__":
    main()