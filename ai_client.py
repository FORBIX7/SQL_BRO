import logging
import os
import re
import requests
import httpx


from openai import OpenAI


class AIClient:
    def __init__(self, ai_provider="local", openai_api_key=None, openrouter_api_key=None, proxy=None,
                 local_url="http://127.0.0.1:1234/v1/chat/completions"):

        self.provider = ai_provider
        self.openai_api_key = openai_api_key
        self.openrouter_api_key = openrouter_api_key
        self.proxy = proxy
        self.local_url = local_url

        self.default_model = os.getenv("AI_MODEL")  # ✅ ← главный источник модели

        if not self.default_model:
            raise ValueError("❌ Переменная окружения AI_MODEL не установлена!")

        logging.info(f"[AIClient] Провайдер: {self.provider}, модель по умолчанию: {self.default_model}")

        if self.provider == "openai":
            self.client = self._create_openai_client()
        elif self.provider == "openrouter":
            self.session = self._create_openrouter_session()

    def chat(self, prompt, model=None, max_tokens=500, temperature=0):
        model = model or self.default_model  # ✅ используем AI_MODEL если model не задана

        logging.info(f"[AIClient.chat] Провайдер: {self.provider}, модель: {model}")

        if not model:
            raise ValueError("[AIClient.chat] ❌ Модель не передана! Укажи model_name либо настрой AI_MODEL в .env.")

        if self.provider == "local":
            return self._chat_local(prompt, model, max_tokens, temperature)
        elif self.provider == "openai":
            return self._chat_openai(prompt, model, max_tokens, temperature)
        elif self.provider == "openrouter":
            return self._chat_openrouter(prompt, model, max_tokens, temperature)
        else:
            logging.error(f"❌ Неизвестный провайдер AI: {self.provider}")
            return None

    def _create_openai_client(self):
        if self.proxy:
            logging.info(f"[AIClient] Используется прокси: {self.proxy}")

            proxy = httpx.Proxy(self.proxy)
            transport = httpx.HTTPTransport(proxy=proxy)
            http_client = httpx.Client(transport=transport)

            return OpenAI(api_key=self.openai_api_key, http_client=http_client)

        return OpenAI(api_key=self.openai_api_key)

    def _create_openrouter_session(self):
        session = requests.Session()
        if self.proxy:
            session.proxies.update({
                "http": self.proxy,
                "https": self.proxy
            })
        session.headers.update({
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "HTTP-Referer": "http://localhost",
            "X-Title": "SQLBro"
        })
        return session

    def _chat_openai(self, prompt, model, max_tokens, temperature):
        logging.info(f"[AIClient._chat_openrouter] Отправка запроса с моделью: {model}")
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"❌ Ошибка OpenAI API: {e}", exc_info=True)
            return None

    def _chat_openrouter(self, prompt, model, max_tokens, temperature):
        logging.info(f"[AIClient._chat_openrouter] Отправка запроса с моделью: {model}")

        # 1. Сначала пробуем без прокси
        try:
            logging.info("[AIClient._chat_openrouter] Пробуем без прокси")
            session = requests.Session()
            session.headers.update({
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "HTTP-Referer": "http://localhost",
                "X-Title": "SQLBro"
            })

            response = session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                },
                timeout=90
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

        except Exception as e:
            logging.warning(f"⚠️ Ошибка при подключении без прокси: {e}", exc_info=True)

            # 2. Если не удалось — пробуем через прокси
            if not self.proxy:
                logging.error("❌ Прокси не настроен, повторная попытка невозможна.")
                return None

            try:
                logging.info("[AIClient._chat_openrouter] Повторная попытка через прокси")
                proxy_session = requests.Session()
                proxy_session.proxies.update({
                    "http": self.proxy,
                    "https": self.proxy
                })
                proxy_session.headers.update({
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "HTTP-Referer": "http://localhost",
                    "X-Title": "SQLBro"
                })

                response = proxy_session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": temperature
                    },
                    timeout=90
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            except Exception as proxy_error:
                logging.error(f"❌ Ошибка OpenRouter API через прокси: {proxy_error}", exc_info=True)
                return None

    def _chat_local(self, prompt, model, max_tokens, temperature):
        try:
            response = requests.post(
                self.local_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                },
                timeout=90,
                proxies={}  # Явно отключаем прокси
            )
            response.raise_for_status()
            data = response.json()

            # Удаляем <think> блоки из ответа
            if 'choices' in data:
                for choice in data['choices']:
                    if 'message' in choice:
                        content = choice['message'].get('content', '')
                        choice['message']['content'] = re.sub(r'<think>[\s\S]*?</think>', '', content)

            return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            logging.error(f"Ошибка локального AI: {e}", exc_info=True)
            return None
