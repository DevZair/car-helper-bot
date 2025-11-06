import json
import requests
from requests import Response
from config import OLLAMA_URL, AI_MODEL


def _extract_from_json(item: dict, bucket: list):
    if not isinstance(item, dict):
        return
    if item.get("response"):
        bucket.append(item["response"])
    message = item.get("message")
    if isinstance(message, dict) and message.get("content"):
        bucket.append(message["content"])


def _parse_text_stream(resp: Response):
    chunks = []
    raw_lines = []
    for raw_line in resp.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = raw_line.strip()
        if not line:
            continue
        raw_lines.append(line)
        try:
            piece = json.loads(line)
        except json.JSONDecodeError:
            continue
        _extract_from_json(piece, chunks)
        if piece.get("done"):
            break

    if chunks:
        return "".join(chunks).strip()

    if raw_lines:
        try:
            data = json.loads("\n".join(raw_lines))
            bucket = []
            _extract_from_json(data, bucket)
            if bucket:
                return "".join(bucket).strip()
        except json.JSONDecodeError:
            pass

    return ""


def ask_ollama(prompt: str):
    try:
        payload = {"model": AI_MODEL, "prompt": prompt, "stream": True}
        resp = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=(10, 180),
            stream=True,
        )
        resp.raise_for_status()
        try:
            reply = _parse_text_stream(resp)
        finally:
            resp.close()

        if reply:
            return reply

        resp = requests.post(
            OLLAMA_URL,
            json={**payload, "stream": False},
            timeout=(10, 180),
        )
        resp.raise_for_status()
        data = resp.json()
        bucket = []
        _extract_from_json(data, bucket)
        if bucket:
            return "".join(bucket).strip()

        return "Извини, не удалось получить ответ от модели."

    except requests.exceptions.Timeout:
        return "AI долго думает. Попробуй переформулировать вопрос или спроси чуть позже."
    except Exception as e:
        return f"Ошибка при обращении к AI: {e}"
