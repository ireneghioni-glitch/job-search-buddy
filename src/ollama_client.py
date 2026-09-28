"""
ollama_client.py
================
Thin wrapper around the local Ollama HTTP API.

This module provides a single function, `generate`, that sends a prompt to a
locally-running Ollama instance and returns the model's response as a string.
"""

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"


def generate(model: str, prompt: str, system: str = "",
             temperature: float = 0.3, num_ctx: int = 8192) -> str:
    """Send a prompt to a local Ollama model and return its text response.

    Args:
        model: Name of the Ollama model to use (e.g. "llama3.2:3b").
        prompt: The user prompt to send to the model.
        system: Optional system prompt describing the assistant's role and rules.
        temperature: Sampling temperature. Lower values (0.1-0.4) give more
            deterministic, factual answers. Higher values give more creative ones.
        num_ctx: Size of the context window in tokens. Larger windows allow
            longer inputs (profile + job posting) but use more RAM.

    Returns:
        The model's response as a plain string.

    Raises:
        requests.HTTPError: If Ollama returns a non-2xx status code.
        requests.Timeout: If the request exceeds the 900-second timeout.
    """
    payload = {
        "model": model, 
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
        },
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=900)
    r.raise_for_status()
    return r.json()["response"]