import os
import uuid
import logging
from dotenv import load_dotenv
import io
from contextlib import redirect_stdout

load_dotenv()

from google.adk.agents.llm_agent import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from server.task_manager import InMemoryTaskManager
from models.request import SendTaskRequest, SendTaskResponse
from models.task import Message, TaskStatus, TaskState, TextPart
from agents.host_agent.agent_connect import AgentConnector
from models.agent import AgentCard

logger = logging.getLogger(__name__)

class OrchestratorAgent:
    """
    Uses a Gemini LLM to route incoming user queries,
    calling out to any discovered child A2A agents via tools.
    """

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, agent_cards: list[AgentCard]):
        self.agent_cards = agent_cards
        self.connectors = {card.name: AgentConnector(card.name, card.url) for card in agent_cards}
        self._agent = self._build_agent()
        self._user_id = "orchestrator_user"
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )
    def _format_agent_description(self, card: AgentCard) -> str:
        """Clean formatting of agent capabilities"""
        lines = [f"Agent: {card.name}"]
        lines.append(f"Description: {card.description}")
        
        for skill in card.skills:
            lines.append(f"  Skill: {skill.id} ({skill.name})")
            lines.append(f"    {skill.description.strip()}")
            if skill.examples:
                lines.append("    Examples:")
                for ex in skill.examples[:3]:  # limit to 3
                    lines.append(f"      • {ex}")
        return "\n".join(lines)

    def _build_agent(self) -> LlmAgent:
        """
        Construct the Gemini-based LlmAgent with:
        - Model name
        - Agent name/description
        - System instruction callback
        - Available tool functions
        """
        return LlmAgent(
            model="gemini-2.5-flash",    
            name="orchestrator_agent",   
            description="Take decision based on the instructions recieved from the client and remote agents ",
            instruction=self._root_instruction,  
            tools=[
                self._list_agents,   
                self.delegate_task,  
                self.http_get,       
                self.http_post,          
                self.execute_python,
            ],
        )

    def _root_instruction(self, context: ReadonlyContext) -> str:
        agent_descriptions = "\n\n".join(
            self._format_agent_description(card)
            for card in self.agent_cards
        )
        print(agent_descriptions)
        return f"""
        You are an orchestrator agent responsible for handling user requests by carefully following strict sequential procedures.

CRITICAL RULES - FOLLOW THESE EXACTLY:
1. ALWAYS break down any task into clear, ordered steps.
2. NEVER combine steps or perform them in parallel.
3. NEVER proceed to a later step until the previous step is fully completed.
4. For every request -- {agent_descriptions}
5. If the task requires multiple tool uses, call ONLY one tool per response.
6. Think step-by-step before any action, and explicitly state the current step you are on.
7. Do not respond to the user with a final answer until all required steps are complete.

You have access to tools: http_post, http_get, delegate_task, etc. Use them strictly one at a time when following the steps above.
"""
    async def http_get(self, url: str) -> str:
        """
        Tool function: Sends get request in the URL .
        Called by the LLM when it wants to call api call.
        LLM has to construct the body according to the requirement.
        """
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, timeout=10)
                r.raise_for_status()
                return f"Status {r.status_code}\nContent-Type: {r.headers.get('content-type')}\n\n{r.text[:2000]}..."
        except Exception as e:
            return f"Error: {str(e)}"

    async def http_post(self, url: str, body: str) -> str: 
        """
        Tool function: Sends post request in the URL .
        Called by the LLM when it wants to call api call.
        LLM has to construct the body according to the requirement.
        """

        import httpx
        import json

        try:
            json_body = json.loads(body) if body else {}
            async with httpx.AsyncClient() as client:
                r = await client.post(url, json=json_body, timeout=10)
                r.raise_for_status()
                return f"Status {r.status_code}\n{r.text[:1500]}..."
        except Exception as e:
            return f"Error: {str(e)}"
    async def execute_python(self, code: str) -> str:
        """
        Execute Python code and return:
        - The 'result' variable if set
        - Captured stdout if no 'result' variable
        - Error message on failure
        """
        local_vars = {}
        output = io.StringIO()
        
        try:
            with redirect_stdout(output):
                exec(code, {"print": print}, local_vars)  # ← real print works now
                
            stdout_content = output.getvalue().strip()
            

            if "result" in local_vars:
                result = local_vars["result"]
                return f"Result variable:\n{result}\n\nStdout:\n{stdout_content}" if stdout_content else str(result)
            

            return stdout_content if stdout_content else "No output or result variable found"
            
        except Exception as e:
            return f"Execution error: {str(e)}\nStdout captured:\n{output.getvalue().strip()}"

    def _list_agents(self) -> list[str]:
        """
        Tool function: returns the list of child-agent names currently registered.
        Called by the LLM when it wants to discover available agents.
        """
        return list(self.connectors.keys())

    async def delegate_task(
        self,
        agent_name: str,
        message: str,
        tool_context: ToolContext
    ) -> str:
        """
        Tool function: forwards the `message` to the specified child agent
        (via its AgentConnector), waits for the response, and returns the
        text of the last reply.

        Args:
            agent_name (str): The name of the child agent to delegate to (must be one of the available agents).
            message (str): The user message or task to send to the child agent.
            tool_context (ToolContext): ADK context for session state and actions (do not pass manually).

        Returns:
            str: The response text from the child agent, or an empty string if no response.

        Example:
            delegate_task("TellTimeAgent", "What time is it?")
        """

        if agent_name not in self.connectors:
            raise ValueError(f"Unknown agent: {agent_name}")
        connector = self.connectors[agent_name]

        state = tool_context.state
        if "session_id" not in state:
            state["session_id"] = str(uuid.uuid4())
        session_id = state["session_id"]

        child_task = await connector.send_task(message, session_id)

        if child_task.history and len(child_task.history) > 1:
            return child_task.history[-1].parts[0].text
        return ""

    async def invoke(self, query: str, session_id: str) -> str:
        """
        Main entry: receives a user query + session_id,
        sets up or retrieves a session, wraps the query for the LLM,
        runs the Runner (with tools enabled), and returns the final text.
        Note - function updated 28 May 2025
        Summary of changes:
        1. Agent's invoke method is made async
        2. All async calls (get_session, create_session, run_async) 
            are awaited inside invoke method
        3. task manager's on_send_task updated to await the invoke call

        Reason - get_session and create_session are async in the 
        "Current" Google ADK version and were synchronous earlier 
        when this lecture was recorded. This is due to a recent change 
        in the Google ADK code 
        https://github.com/google/adk-python/commit/1804ca39a678433293158ec066d44c30eeb8e23b

        """

        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id
        )

        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                session_id=session_id,
                state={}
            )

        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=query)]
        )

        # 🚀 Run the agent using the Runner and collect the last event
        last_event = None
        async for event in self._runner.run_async(
            user_id=self._user_id,
            session_id=session.id,
            new_message=content
        ):
            last_event = event

        # 🧹 Fallback: return empty string if something went wrong
        if not last_event or not last_event.content or not last_event.content.parts:
            return ""

        # 📤 Extract and join all text responses into one string
        return "\n".join([p.text for p in last_event.content.parts if p.text])

class OrchestratorTaskManager(InMemoryTaskManager):
    """
    🪄 TaskManager wrapper: exposes OrchestratorAgent.invoke() over the
    A2A JSON-RPC `tasks/send` endpoint, handling in-memory storage and
    response formatting.
    """
    def __init__(self, agent: OrchestratorAgent):
        super().__init__()
        self.agent = agent

    def _get_user_text(self, request: SendTaskRequest) -> str:
        """
        Helper: extract the user's raw input text from the request object.
        """
        return request.params.message.parts[0].text

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """
        Called by the A2A server when a new task arrives:
        1. Store the incoming user message
        2. Invoke the OrchestratorAgent to get a response
        3. Append response to history, mark completed
        4. Return a SendTaskResponse with the full Task
        """
        logger.info(f"OrchestratorTaskManager received task {request.params.id}")

        task = await self.upsert_task(request.params)

        user_text = self._get_user_text(request)
        response_text = await self.agent.invoke(user_text, request.params.sessionId)

        reply = Message(role="agent", parts=[TextPart(text=response_text)])
        async with self.lock:
            task.status = TaskStatus(state=TaskState.COMPLETED)
            task.history.append(reply)

        return SendTaskResponse(id=request.id, result=task)

