import logging
from google import genai
from google.genai import types

from bot_core import config

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self, api_key=None):
        """Initializes the AI service with the Gemini client."""
        self.api_key = api_key or config.GEMINI_API_KEY
        if not self.api_key:
            logger.error("Gemini API key is not configured.")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)

    def generate_content(self, prompt_parts: list, system_instruction: str = None, model_name: str = "gemini-2.0-flash-exp"):
        """
        Generates content using the Gemini model, following the original script's pattern.
        """
        if not self.client:
            logger.error("AI Service client not initialized due to missing API key.")
            return None
        
        try:
            # Using the client.models.generate_content pattern
            response = self.client.models.generate_content(
                model=model_name,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction
                ),
                contents=prompt_parts
            )
            return response.text
        except Exception as e:
            logger.error(f"Error during Gemini content generation: {e}")
            return None