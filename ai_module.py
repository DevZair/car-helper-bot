import requests
from config import OLLAMA_URL, AI_MODEL

def ask_ollama(prompt: str):
    try:
        resp = requests.post(OLLAMA_URL, json={"model": AI_MODEL, "prompt": prompt}, timeout=60)
        data = resp.json()
        return data.get("response", "Извини, не удалось получить ответ от модели.")
    except Exception as e:
        return f"Ошибка при обращении к AI: {e}"