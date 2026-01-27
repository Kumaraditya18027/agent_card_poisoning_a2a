

import asyncclick as click
import asyncio
from uuid import uuid4
from prompt_toolkit import PromptSession  # For async prompting

# Correct import from the repo
from client.client import A2AClient

# Import the Task model so we can handle and parse responses from the agent
from models.task import Task

# -----------------------------------------------------------------------------
# CLI Command
# -----------------------------------------------------------------------------
@click.command()
@click.option("--agent", default="http://localhost:10002", help="Base URL of the A2A agent server")
@click.option("--session", default="0", help="Session ID (use 0 to generate a new one)")
@click.option("--history", is_flag=True, help="Print full task history after receiving a response")
async def cli(agent: str, session: str, history: bool):
    """
    CLI to send user messages to an A2A agent and display the response.
    """
    # Initialize the client
    client = A2AClient(url=agent)

    # Generate a new session ID if not provided
    session_id = uuid4().hex if str(session) == "0" else str(session)

    # Async prompt session
    session_prompt = PromptSession()

    print(f"Connected to {agent}. Type ':q' or 'quit' to exit.\n")

    # Main input loop
    while True:
        try:
            # Async prompt (this fixes the original coroutine error)
            user_input = await session_prompt.prompt_async("\nYou: ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        # Exit conditions
        if user_input.strip().lower() in [":q", "quit", "exit"]:
            print("Goodbye!")
            break

        if not user_input.strip():
            continue

        # Construct the JSON-RPC payload (matches repo's send_task expectation)
        payload = {
            "id": uuid4().hex,  # Unique task ID
            "sessionId": session_id,  # Reuse session
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": user_input}]
            }
        }

        try:
            # Send the task and get response
            task: Task = await client.send_task(payload)

            # Extract and print agent's reply
            if task.history and len(task.history) > 1:
                reply = task.history[-1]  # Last message is from agent
                print(f"\nAgent says: {reply.parts[0].text}")
            else:
                print("\nNo response received.")

            # Optional full history
            if history:
                print("\n========= Conversation History =========")
                for msg in task.history:
                    role = msg.role.upper()
                    text = msg.parts[0].text if msg.parts else "[No text]"
                    print(f"[{role}] {text}")
                print("=======================================")

        except Exception as e:
            import traceback
            traceback.print_exc()  # For debugging
            print(f"\n❌ Error sending task: {e}")

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Run the async CLI
    asyncio.run(cli())