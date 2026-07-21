# utils.py

import re
import json
import logging

logger = logging.getLogger("Utils")

def extract_json_from_response(response_text: str) -> dict:
    """
    Универсальный метод для извлечения JSON из произвольного текста ответа модели.
    """
    try:
        cleaned = re.sub(r'```(?:json)?|</?answer>|Ответ завершен', '', response_text, flags=re.IGNORECASE).strip()
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start == -1 or end == -1:
            raise ValueError("Не удалось найти JSON в ответе.")
        json_str = cleaned[start:end + 1]
        return json.loads(json_str)
    except Exception as e:
        logger.error(f"Не удалось извлечь JSON из ответа: {e}")
        logger.debug(f"Сырой ответ модели:\n{response_text}")
        return {}
