# agents/greeting_agent/task_manager.py
# =============================================================================

class GreetingTaskManager(InMemoryTaskManager):
    """
    TaskManager for GreetingAgent:

    - Inherits storage, upsert_task, and locking from InMemoryTaskManager
    - Overrides on_send_task() to:
      * save the incoming message
      * call the GreetingAgent.invoke() to craft a greeting
      * update the task status and history
      * wrap and return the result as SendTaskResponse

    Note:
    - GreetingAgent.invoke() is asynchronous, but on_send_task()
      itself is also defined as async, so we await internal calls.
    """
    def __init__(self, agent: GreetingAgent):
        """
        Initialize the TaskManager with a GreetingAgent instance.

        Args:
            agent (GreetingAgent): The core logic handler that knows how to
                                   produce a greeting.
        """

        super().__init__()

        self.agent = agent

    def _get_user_text(self, request: SendTaskRequest) -> str:
        """
        Extract the raw user text from the incoming SendTaskRequest.

        Args:
            request (SendTaskRequest): The incoming JSON-RPC request
                                       containing a TaskSendParams object.

        Returns:
            str: The text content the user sent (first TextPart).
        """

        return request.params.message.parts[0].text

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """
        Handle a new greeting task:

        1. Store the incoming user message in memory (or update existing task)
        2. Extract the user's text for processing
        3. Call GreetingAgent.invoke() to generate the greeting
        4. Wrap that greeting string in a Message/TextPart
        5. Update the Task status to COMPLETED and append the reply
        6. Return a SendTaskResponse containing the updated Task

        Args:
            request (SendTaskRequest): The JSON-RPC request with TaskSendParams

        Returns:
            SendTaskResponse: A JSON-RPC response with the completed Task
        """

        logger.info(f"GreetingTaskManager received task {request.params.id}")

        # upsert_task() will create a new Task if it doesn't exist,
        # or append the incoming user message to existing history.
        task = await self.upsert_task(request.params)

        user_text = self._get_user_text(request)

        # Since GreetingAgent.invoke() might be an async function,
        # await it to get the returned string.
        greeting_text = await self.agent.invoke(
            user_text,
            request.params.sessionId
        )

        # Step 4: Wrap the greeting string in a TextPart, then in a Message
        reply_message = Message(
            role="agent",
            parts=[TextPart(text=greeting_text)]
        )

        async with self.lock:

            task.status = TaskStatus(state=TaskState.COMPLETED)

            task.history.append(reply_message)

        # Step 6: Return a SendTaskResponse, containing the JSON-RPC id
        # (mirroring the request.id) and the updated Task model.
        return SendTaskResponse(id=request.id, result=task)
