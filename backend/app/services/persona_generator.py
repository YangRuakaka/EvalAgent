"""
Persona generation service using LangChain and large language models.
Handles the core logic for generating value agent personas based on demographic information.
"""
from typing import Dict, Any, Optional
import logging

from langchain_core.messages import HumanMessage

# Import configuration
from ..core.config import get_settings
from .llm_factory import get_chat_llm, LLMConfigurationError

logger = logging.getLogger(__name__)
settings = get_settings()


class PersonaPromptTemplate:
    """Template for constructing persona generation prompts based on demographic information."""
    PERSONA_DIRECT_TEMPLATE = """
You are an expert at creating realistic personas from demographic information. 

TASK: Based on the following demographic information, create a natural persona description: {demographic}

INSTRUCTIONS:
1. Synthesize a cohesive character profile that reflects their background, lifestyle, and likely attitudes
2. Write in a natural, descriptive style - create a vivid picture of who this person is
3. Output a single cohesive paragraph of 4-5 sentences, beginning with the person's name
4. Keep it concise (approximately 50-100 words), realistic, and grounded in the provided demographics
5. Do NOT use bullet points, headings, or artificial formatting
6. Output ONLY the persona paragraph with no extra commentary

DEMOGRAPHIC: {demographic}

Persona:"""

    @classmethod
    def build_prompt(cls, demographic: Dict[str, Any]) -> str:
        """
        Build prompt from demographic information.
        
        Args:
            demographic: Dictionary containing demographic information
            
        Returns:
            Formatted prompt string
        """
        # Format demographic info into a readable string
        demo_parts = []
        demo_parts.append(f"Name: {demographic['name']}")
        demo_parts.append(f"Age: {demographic['age']}")
        demo_parts.append(f"Job: {demographic['job']}")
        
        if demographic.get('location'):
            demo_parts.append(f"Location: {demographic['location']}")
        if demographic.get('education'):
            demo_parts.append(f"Education: {demographic['education']}")
        if demographic.get('interests'):
            demo_parts.append(f"Interests: {demographic['interests']}")
            
        demographic_str = ", ".join(demo_parts)
        return cls.PERSONA_DIRECT_TEMPLATE.format(demographic=demographic_str).strip()





class PersonaGeneratorService:
    """Service for generating personas using a configured LangChain chat model."""

    def __init__(self, llm: Any):
        """Initialize the persona generator service with a chat model instance."""

        self.llm = llm
        self.prompt_template = PersonaPromptTemplate()
        self._llm_by_model: Dict[str, Any] = {
            settings.DEFAULT_LLM_MODEL.strip().lower(): llm,
        }

    def _resolve_llm(self, model: Optional[str] = None) -> Any:
        """Resolve and cache LLM instances by model name to avoid repeated client creation."""
        if not model or not model.strip():
            return self.llm

        model_name = model.strip()
        cache_key = model_name.lower()
        cached = self._llm_by_model.get(cache_key)
        if cached is not None:
            return cached

        resolved_llm = get_chat_llm(
            model=model_name,
            max_tokens=settings.DEFAULT_MAX_TOKENS,
            temperature=settings.PERSONA_LLM_TEMPERATURE,
        )
        self._llm_by_model[cache_key] = resolved_llm
        return resolved_llm
        
    async def generate_persona(
        self,
        demographic: Dict[str, Any],
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a persona based on provided demographic information.
        
        Args:
            demographic: Dictionary containing demographic information
            model: Optional model identifier to use (overrides default)
            
        Returns:
            Dictionary containing generation results
        """
        logger.info("Starting persona generation with model: %s", model or settings.DEFAULT_LLM_MODEL)
        
        # Build the prompt using prompt engineering logic (all handled in backend)
        prompt = self.prompt_template.build_prompt(demographic=demographic)
        
        try:
            llm = self._resolve_llm(model)
            logger.debug("Persona prompt: %s", prompt)

            message = HumanMessage(content=prompt)
            response = await llm.ainvoke([message])
            generated_persona = response.content.strip()
            logger.debug("Generated persona content: %s", generated_persona)
            
            # Return results
            return {
                "persona": generated_persona,
                "success": True,
                "error_message": None
            }
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"Error generating persona: {error_str}")

            return {
                "persona": None,
                "success": False,
                "error_message": error_str
            }


# Factory function to create persona generator service
def create_persona_generator_service() -> PersonaGeneratorService:
    """
    Factory function to create and configure persona generator service.
    
    Returns:
        Configured PersonaGeneratorService instance
    """
    try:
        llm = get_chat_llm(
            model=settings.DEFAULT_LLM_MODEL,
            max_tokens=settings.DEFAULT_MAX_TOKENS,
            temperature=settings.PERSONA_LLM_TEMPERATURE,
        )
        logger.info("Created persona generator with configured LLM provider")
    except LLMConfigurationError as exc:
        logger.error("Persona LLM configuration failed: %s", exc)
        raise ValueError(
            f"Persona LLM configuration failed: {str(exc)}. "
            "Please configure a valid API key for the selected provider."
        ) from exc

    return PersonaGeneratorService(llm=llm)
