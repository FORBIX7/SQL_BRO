import os
import logging



class AISettings:
    def __init__(self):
        self.ai_provider = os.getenv("AI_PROVIDER", "local").strip().lower()
        self.ai_model = os.getenv("AI_MODEL", "gpt-4o")

        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")
        self.proxy_username = os.getenv("PROXY_USERNAME")
        self.proxy_password = os.getenv("PROXY_PASSWORD")
        logging.info(f"AI provider: {self.ai_provider}, model: {self.ai_model}")
        self.proxy = None
        if self.proxy_host and self.proxy_port:
            self.proxy = f"http://{self.proxy_username}:{self.proxy_password}@{self.proxy_host}:{self.proxy_port}"
