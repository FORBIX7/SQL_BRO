# agent_manager.py
from SQLBRO import SQLAgent
from ai_config import AISettings

class AgentManager:
    @staticmethod
    def get_agent(context, db_type="sqlite", db_path=None, force_reload=False):
        user_context = context.user_data.setdefault("user_context", {})
        agent = user_context.get("agent")

        if agent is None or force_reload:
            ai_settings = AISettings()
            agent = SQLAgent(db_type=db_type, db_path=db_path, ai_settings=ai_settings)
            user_context["agent"] = agent

        return agent
