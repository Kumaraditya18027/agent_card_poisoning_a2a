import logging

# 🔁 Import the shared in-memory task manager from the server
from server.task_manager import InMemoryTaskManager

from agents.tell_time_agent.agent import TellTimeAgent

# 📦 Import data models used to structure and return tasks
from models.request import SendTaskRequest, SendTaskResponse
from models.task import Message, Task, TextPart, TaskStatus, TaskState
# This allows us to print nice logs like:
# INFO:agents.google_adk.task_manager:Processing new task: 12345
logger = logging.getLogger(__name__)

class AgentTaskManager(InMemoryTaskManager):
    """
    This class connects the Gemini agent to the task system.

    - It "inherits" all the logic from InMemoryTaskManager
    - It overrides the part where we handle a new task (on_send_task)
    - It uses the Gemini agent to generate a response
    """

    def __init__(self, agent: TellTimeAgent):
        super().__init__()
        self.agent = agent
    # 🔍 Extract the user's query from the incoming task
    def _get_user_query(self, request: SendTaskRequest) -> str:
        """
        Get the user’s text input from the request object.

        Example: If the user says "what time is it?", we pull that string out.

        Args:
            request: A SendTaskRequest object

        Returns:
            str: The actual text the user asked
        """
        return request.params.message.parts[0].text
    # Main logic to handle and complete a task
    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """
        This is the heart of the task manager.

        It does the following:
        1. Save the task into memory (or update it)
        2. Ask the Gemini agent for a reply
        3. Format that reply as a message
        4. Save the agent’s reply into the task history
        5. Return the updated task to the caller
        """

        logger.info(f"Processing new task: {request.params.id}")

        task = await self.upsert_task(request.params)

        query = self._get_user_query(request)

        result_text = await self.agent.invoke(query, request.params.sessionId)

        agent_message = Message(
            role="agent",
            parts=[TextPart(text=result_text)]
        )

        async with self.lock:
            task.status = TaskStatus(state=TaskState.COMPLETED)
            task.history.append(agent_message)

        return SendTaskResponse(id=request.id, result=task)

