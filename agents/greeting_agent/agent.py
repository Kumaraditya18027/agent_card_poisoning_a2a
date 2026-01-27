import logging                              # Built-in module to log info, warnings, errors
from dotenv import load_dotenv

load_dotenv()

# Gemini LLM agent and supporting services from Google’s ADK:
from google.adk.agents.llm_agent import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner

# Gemini types for wrapping messages
from google.genai import types

# Helper to wrap our Python functions as “tools” for the LLM to call
from google.adk.tools.function_tool import FunctionTool

# Utilities we wrote for agent discovery and HTTP connection:
from utilities.discovery import DiscoveryClient
from agents.host_agent.agent_connect import AgentConnector

logger = logging.getLogger(__name__)

class GreetingAgent:
    """
    Orchestrator “meta-agent” that:
      - Provides two LLM tools: list_agents() and call_agent(...)
      - On a “greet me” request:
          1) Calls list_agents() to see which agents are up
          2) Calls call_agent("TellTimeAgent", "What is the current time?")
          3) Crafts a 2–3 line poetic greeting referencing that time
    """

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        """
        Constructor: build the internal orchestrator LLM, runner, discovery client.
        """

        self.orchestrator = self._build_orchestrator()

        # A fixed user_id to group all greeting calls into one session
        self.user_id = "greeting_user"

        # Runner wires together: agent logic, sessions, memory, artifacts
        self.runner = Runner(
            app_name=self.orchestrator.name,
            agent=self.orchestrator,
            artifact_service=InMemoryArtifactService(),       # file blobs, unused here
            session_service=InMemorySessionService(),         # in-memory sessions
            memory_service=InMemoryMemoryService(),           # conversation memory
        )

        # A helper client to discover what agents are registered
        self.discovery = DiscoveryClient()

        self.connectors: dict[str, AgentConnector] = {}

    def _build_orchestrator(self) -> LlmAgent:
        """
        🔧 Internal: define the LLM, its system instruction, and wrap tools.
        """

        # --- Tool 1: list_agents ---
        async def list_agents() -> list[dict]:
            """
            Fetch all AgentCard metadata from the registry,
            return as a list of plain dicts.
            """

            cards = await self.discovery.list_agent_cards()

            return [card.model_dump(exclude_none=True) for card in cards]

        # --- Tool 2: call_agent ---
        async def call_agent(agent_name: str, message: str) -> str:
            """
            Given an agent_name string and a user message,
            find that agent’s URL, send the task, and return its reply.
            """

            cards = await self.discovery.list_agent_cards()

            matched = next(
                (c for c in cards
                 if c.name.lower() == agent_name.lower()
                 or getattr(c, "id", "").lower() == agent_name.lower()),
                None
            )

            if not matched:
                matched = next(
                    (c for c in cards if agent_name.lower() in c.name.lower()),
                    None
                )

 still nothing, error out
            if not matched:
                raise ValueError(f"Agent '{agent_name}' not found.")

            key = matched.name
 we haven’t built a connector yet, create and cache one
            if key not in self.connectors:
                self.connectors[key] = AgentConnector(
                    name=matched.name,
                    base_url=matched.url
                )
            connector = self.connectors[key]

            session_id = self.user_id

            task = await connector.send_task(message, session_id=session_id)

            if task.history and task.history[-1].parts:
                return task.history[-1].parts[0].text

 no reply, return empty string
            return ""

        # --- System instruction for the LLM ---
        system_instr = (
            "You have two tools:\n"
            "1) list_agents() → returns metadata for all available agents.\n"
            "2) call_agent(agent_name: str, message: str) → fetches a reply from that agent.\n"
            "When asked to greet, first call list_agents(), then "
            "call_agent('TellTimeAgent','What is the current time?'), "
            "then craft a 2–3 line poetic greeting referencing that time."
        )

        tools = [
            FunctionTool(list_agents),   # auto-uses function name and signature
            FunctionTool(call_agent),
        ]

        # Finally, create and return the LlmAgent with everything wired up
        return LlmAgent(
            model="gemini-2.5-flash",               # which Gemini model
            name="greeting_orchestrator",                  # internal name
            description="Orchestrates time fetching and generates poetic greetings.",
            instruction=system_instr,                      # system prompt
            tools=tools,                                   # available tools
        )

    async def invoke(self, query: str, session_id: str) -> str:
        """
        🔄 Public: send a user query through the orchestrator LLM pipeline,
        ensuring session reuse or creation, and return the final text reply.
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
        session = await self.runner.session_service.get_session(
            app_name=self.orchestrator.name,
            user_id=self.user_id,
            session_id=session_id,
        )

        if session is None:
            session = await self.runner.session_service.create_session(
                app_name=self.orchestrator.name,
                user_id=self.user_id,
                session_id=session_id,
                state={},  # you could prefill memory here if desired
            )

        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=query)]
        )

        # 🚀 Run the agent using the Runner and collect the last event
        last_event = None
        async for event in self.runner.run_async(
            user_id=self.user_id,
            session_id=session.id,
            new_message=content
        ):
            last_event = event

        # 🧹 Fallback: return empty string if something went wrong
        if not last_event or not last_event.content or not last_event.content.parts:
            return ""

        # 📤 Extract and join all text responses into one string
        return "\n".join([p.text for p in last_event.content.parts if p.text])