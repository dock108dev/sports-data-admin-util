"""
OpenAI Client for Story Generation.

Provides a simple wrapper around OpenAI API for chapter summaries,
titles, and compact stories.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from ..config import get_settings

logger = logging.getLogger(__name__)


class OpenAIClient:
    """OpenAI client for story generation.
    
    This client provides a simple .generate(prompt) interface
    that the chapter generators expect.
    """
    
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini"):
        """Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key (if None, uses settings)
            model: Model to use for generation
        """
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model
        
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")
        
        self.client = OpenAI(api_key=self.api_key)
        logger.info(f"OpenAI client initialized with model: {self.model}")
    
    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """Generate text from prompt.
        
        Args:
            prompt: Prompt text
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text (JSON string for structured outputs)
            
        Raises:
            Exception: If generation fails
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a sports narrative writer. Generate engaging, accurate summaries of game moments. Always respond with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("OpenAI returned empty response")
            
            # Validate it's valid JSON
            json.loads(content)
            
            return content
            
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            raise


def get_openai_client() -> OpenAIClient | None:
    """Get OpenAI client if API key is configured.
    
    Returns:
        OpenAIClient if configured, None otherwise
    """
    settings = get_settings()
    
    if not settings.openai_api_key:
        logger.warning("OpenAI API key not configured - AI generation disabled")
        return None
    
    try:
        return OpenAIClient()
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        return None
