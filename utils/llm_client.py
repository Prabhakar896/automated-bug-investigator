"""
LLM client wrapper — abstracts the Google Gemini API behind a simple interface.

Includes automatic retry with exponential backoff for rate-limited requests.
When no API key is configured, falls back to deterministic analysis
so the pipeline can be demonstrated end-to-end without external calls.
"""

import json
import logging
import time
from typing import Any, Optional, Type

from pydantic import BaseModel

from config import Config

logger = logging.getLogger("pipeline.llm_client")

# Retry settings
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 5


class LLMClient:
    """Wrapper around the Google Generative AI SDK with retry logic."""

    def __init__(self):
        self._client = None
        self._available = False
        self._rate_limited = False
        self._last_error = ""
        self._init_client()

    def _init_client(self):
        """Initialize the Gemini client if API key is available."""
        if not Config.GOOGLE_API_KEY:
            logger.warning(
                "GOOGLE_API_KEY not set -- LLM client running in DETERMINISTIC mode. "
                "Set the env var to enable real LLM calls."
            )
            self._last_error = "No API key configured"
            return

        try:
            from google import genai

            self._client = genai.Client(api_key=Config.GOOGLE_API_KEY)
            self._available = True
            logger.info(f"LLM client initialized (model: {Config.LLM_MODEL})")
        except ImportError:
            self._last_error = "google-genai package not installed"
            logger.warning(
                "google-genai package not installed. "
                "Run: pip install google-genai"
            )
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to initialize LLM client: {e}")

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def status(self) -> dict:
        """Return detailed LLM status for dashboard display."""
        return {
            "available": self._available,
            "rate_limited": self._rate_limited,
            "model": Config.LLM_MODEL,
            "api_key_set": bool(Config.GOOGLE_API_KEY),
            "last_error": self._last_error,
            "mode": "LLM" if self._available and not self._rate_limited
                    else "RATE_LIMITED" if self._rate_limited
                    else "DETERMINISTIC",
        }

    def generate(
        self,
        prompt: str,
        system_instruction: str = "",
        response_schema: Optional[Type[BaseModel]] = None,
        temperature: Optional[float] = None,
    ) -> dict:
        """
        Generate a response from the LLM with automatic retry on rate limits.

        Args:
            prompt: User prompt text
            system_instruction: System instruction for the model
            response_schema: Optional Pydantic model for structured output
            temperature: Override default temperature

        Returns:
            Parsed dict from the LLM response
        """
        if not self._available:
            logger.debug("LLM unavailable -- using deterministic analysis")
            return self._mock_response(prompt, response_schema)

        try:
            from google import genai
            from google.genai import types

            config = types.GenerateContentConfig(
                temperature=temperature or Config.LLM_TEMPERATURE,
                max_output_tokens=Config.LLM_MAX_TOKENS,
            )

            if system_instruction:
                config.system_instruction = system_instruction

            if response_schema:
                config.response_mime_type = "application/json"
                config.response_schema = response_schema

            # Retry loop with exponential backoff
            last_exception = None
            for attempt in range(MAX_RETRIES):
                try:
                    response = self._client.models.generate_content(
                        model=Config.LLM_MODEL,
                        contents=prompt,
                        config=config,
                    )
                    self._rate_limited = False
                    self._last_error = ""

                    if response_schema:
                        try:
                            return json.loads(response.text)
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse structured response, returning raw")
                            return {"raw_response": response.text}
                    else:
                        return {"response": response.text}

                except Exception as e:
                    last_exception = e
                    error_str = str(e)

                    # Check if it's a rate limit error (429)
                    if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                        # If the limit is literally 0, it means free tier is disabled or region is unsupported.
                        # Retrying is pointless, so we must fall back immediately.
                        if "limit: 0" in error_str:
                            self._rate_limited = True
                            self._last_error = "Free tier quota unavailable (limit: 0) - check region/billing"
                            logger.warning(
                                "LLM API returned limit: 0. Skipping retries. "
                                "Using deterministic analysis engine instead."
                            )
                            break
                            
                        self._rate_limited = True
                        backoff = INITIAL_BACKOFF_SECONDS * (2 ** attempt)

                        # Try to extract retry delay from error
                        import re
                        retry_match = re.search(r'retry in (\d+)', error_str)
                        if retry_match:
                            backoff = max(backoff, int(retry_match.group(1)))

                        if attempt < MAX_RETRIES - 1:
                            logger.warning(
                                f"Rate limited (attempt {attempt + 1}/{MAX_RETRIES}), "
                                f"retrying in {backoff}s..."
                            )
                            time.sleep(backoff)
                            continue
                        else:
                            self._last_error = "Rate limit exceeded - using deterministic analysis"
                            logger.warning(
                                "Rate limit exceeded after all retries. "
                                "Using deterministic analysis engine instead."
                            )
                    else:
                        # Non-rate-limit error, don't retry
                        self._last_error = error_str[:200]
                        logger.error(f"LLM generation failed: {e}")
                        break

            logger.info("Falling back to deterministic analysis")
            return self._mock_response(prompt, response_schema)

        except Exception as e:
            self._last_error = str(e)[:200]
            logger.error(f"LLM generation failed: {e}")
            logger.info("Falling back to deterministic analysis")
            return self._mock_response(prompt, response_schema)

    def _mock_response(
        self,
        prompt: str,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> dict:
        """Return a deterministic mock response for demo mode."""
        if response_schema:
            # Build a response from the schema's default values
            try:
                instance = response_schema()
                return instance.model_dump()
            except Exception:
                return {}
        return {"response": "Deterministic analysis -- configure GOOGLE_API_KEY for LLM-enhanced responses."}


# Singleton instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get the singleton LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
