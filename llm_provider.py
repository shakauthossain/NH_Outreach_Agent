# llm_provider.py
import os
from typing import Dict, Tuple
from dotenv import load_dotenv
from langchain_groq import ChatGroq

# Load .env exactly once here
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set in environment (.env).")

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

# Optional default temperature override via .env
DEFAULT_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.7"))

# Cache ChatGroq instances by (model, temperature)
_clients: Dict[Tuple[str, float], ChatGroq] = {}

def get_chat_groq(temperature: float | None = None) -> ChatGroq:
    """
    Returns a cached ChatGroq instance configured with the shared model/key.
    - temperature: if None, uses DEFAULT_TEMPERATURE from env.
    """
    temp = DEFAULT_TEMPERATURE if temperature is None else float(temperature)
    key = (GROQ_MODEL, temp)
    if key not in _clients:
        _clients[key] = ChatGroq(
            model_name=GROQ_MODEL,
            temperature=temp,
            groq_api_key=GROQ_API_KEY,
        )
    return _clients[key]
