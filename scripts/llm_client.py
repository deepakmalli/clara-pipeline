"""
llm_client.py - Unified LLM client supporting Ollama (local) and Groq (free tier).

Usage:
    from scripts.llm_client import LLMClient
    client = LLMClient()  # reads from .env
    response = client.generate("Extract data from this transcript...")
"""

import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    """Unified LLM client for Ollama and Groq."""

    def __init__(self, provider: str = None):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower()

        if self.provider == "ollama":
            self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            self.model = os.getenv("OLLAMA_MODEL", "llama3")
        elif self.provider == "groq":
            self.api_key = os.getenv("GROQ_API_KEY", "")
            self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            if not self.api_key or self.api_key == "your_groq_api_key_here":
                raise ValueError(
                    "GROQ_API_KEY not set. Sign up free at https://console.groq.com "
                    "and set GROQ_API_KEY in your .env file."
                )
        else:
            raise ValueError(f"Unknown LLM_PROVIDER: {self.provider}. Use 'ollama' or 'groq'.")

        print(f"  [LLM] Using {self.provider} with model '{self.model}'")

    def generate(self, prompt: str, max_retries: int = 3, temperature: float = 0.1) -> str:
        """
        Send a prompt to the LLM and return the text response.
        Low temperature for consistent, factual extraction.
        """
        for attempt in range(1, max_retries + 1):
            try:
                if self.provider == "ollama":
                    return self._call_ollama(prompt, temperature)
                elif self.provider == "groq":
                    return self._call_groq(prompt, temperature)
            except requests.exceptions.ConnectionError:
                if self.provider == "ollama":
                    raise ConnectionError(
                        f"Cannot connect to Ollama at {self.base_url}. "
                        "Make sure Ollama is running: 'ollama serve' or start via Docker."
                    )
                raise
            except Exception as e:
                if attempt < max_retries:
                    wait = 2 ** attempt
                    print(f"  [LLM] Attempt {attempt} failed: {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"LLM call failed after {max_retries} attempts: {e}"
                    ) from e

    def _call_ollama(self, prompt: str, temperature: float) -> str:
        """Call Ollama's local API."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 4096,
            },
        }

        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "").strip()

    def _call_groq(self, prompt: str, temperature: float) -> str:
        """Call Groq's free API."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise data extraction assistant. Always respond with valid JSON when asked to extract structured data.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": 4096,
        }

        response = requests.post(url, json=payload, headers=headers, timeout=120)

        # Handle rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get("retry-after", 10))
            print(f"  [LLM] Rate limited. Waiting {retry_after}s...")
            time.sleep(retry_after)
            response = requests.post(url, json=payload, headers=headers, timeout=120)

        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"].strip()

    def health_check(self) -> bool:
        """Check if the LLM service is available."""
        try:
            if self.provider == "ollama":
                r = requests.get(f"{self.base_url}/api/tags", timeout=5)
                return r.status_code == 200
            elif self.provider == "groq":
                # Simple test call
                self.generate("Say 'ok'.", max_retries=1)
                return True
        except Exception:
            return False
