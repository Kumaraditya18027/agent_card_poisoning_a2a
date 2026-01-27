import logging
from server.task_manager import InMemoryTaskManager
from models.request import SendTaskRequest, SendTaskResponse
from models.task import Message, TextPart, TaskStatus, TaskState
from agents.hotel_booking_agent.agent import HotelBookingAgent

logger = logging.getLogger(__name__)

class AgentTaskManager(InMemoryTaskManager):
    def __init__(self, agent: HotelBookingAgent):
        super().__init__()
        self.agent = agent

    def _get_user_query(self, request: SendTaskRequest) -> str:
        return request.params.message.parts[0].text

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """
        FIXED: Always return SendTaskResponse(id=..., result=task) where task is a Task object.
        Never return result=string or result=result_text.
        """
        logger.info(f"HotelBookingAgent processing task {request.params.id}")

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

        # ← THIS WAS THE BUG: Previously it was result=result_text (string)
        return SendTaskResponse(id=request.id, result=task)