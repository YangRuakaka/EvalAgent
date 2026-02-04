"""
Persona generation service using LangChain and large language models.
Handles the core logic for generating value agent personas based on demographic information.
"""
from typing import Dict, Any
import logging

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

# Import configuration
from ..core.config import get_settings
from .llm_factory import get_chat_llm, LLMConfigurationError

logger = logging.getLogger(__name__)
settings = get_settings()


class PersonaPromptTemplate:
    """Template for constructing persona generation prompts based on demographic information."""
    
    from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate

    example_prompt = PromptTemplate(
        input_variables=["demographic", "persona"],
        template="DEMOGRAPHIC: {demographic}\nPersona: {persona}"
    )

    examples = [
        {
            "demographic": "Name: Emma Johnson, Age: 32, Job: Marketing Manager, Location: Seattle, WA, Education: Master's in Business Administration, Interests: Sustainable living, yoga, cooking",
            "persona": "Emma Johnson is a 32-year-old marketing manager in Seattle who brings strategic thinking from her MBA to both her professional and personal decisions. Her passion for sustainable living influences her purchasing choices, leading her to favor brands that demonstrate authentic environmental commitment. She finds balance through regular yoga practice and enjoys experimenting with plant-based recipes in her kitchen. Living in Seattle's eco-conscious community, Emma researches thoroughly before making decisions and values transparency and quality over flashy marketing, seeking products that align with her mindful lifestyle."
        },
        {
            "demographic": "Name: Lucas Chen, Age: 28, Job: Software Engineer, Location: Austin, TX, Education: Bachelor's in Computer Science, Interests: Gaming, technology trends, craft beer",
            "persona": "Lucas Chen is a 28-year-old software engineer deeply embedded in Austin's thriving tech ecosystem, where he channels his computer science background into solving complex problems daily. His evenings are split between competitive gaming sessions, researching the latest in AI and hardware innovations, and discovering new craft breweries around the city. Lucas approaches purchasing decisions with an engineer's mindset, prioritizing performance metrics, technical specifications, and genuine innovation over marketing claims. His lifestyle reflects a blend of digital-native efficiency and appreciation for artisanal quality, making him drawn to brands that deliver authentic value and cutting-edge functionality."
        }
    ]

    suffix = """
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

    # FewShotPromptTemplate object
    few_shot_prompt = FewShotPromptTemplate(
        examples=examples,
        example_prompt=example_prompt,
        suffix=suffix,
        input_variables=["demographic"]
    )

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
        return cls.few_shot_prompt.format(demographic=demographic_str)





class PersonaGeneratorService:
    """Service for generating personas using a configured LangChain chat model."""

    def __init__(self, llm: ChatOpenAI):
        """Initialize the persona generator service with a chat model instance."""

        self.llm = llm
        self.prompt_template = PersonaPromptTemplate()
        self._fallback_llm = None
        
    def _get_fallback_llm(self):
        """Get or create fallback Ollama LLM for free model fallback."""
        if self._fallback_llm is None:
            try:
                from .llm_factory import get_chat_llm, LLMProvider
                self._fallback_llm = get_chat_llm(
                    provider=LLMProvider.OLLAMA.value,
                    model=settings.FALLBACK_LLM_MODEL,
                    max_tokens=settings.DEFAULT_MAX_TOKENS,
                    temperature=settings.PERSONA_LLM_TEMPERATURE,
                )
                logger.info(f"Created fallback LLM (Ollama) with model: {settings.FALLBACK_LLM_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to create fallback LLM: {str(e)}")
                return None
        return self._fallback_llm
        
    def _is_api_error(self, error: Exception) -> bool:
        """Check if error is an API error (insufficient balance, API key issue, etc.)."""
        error_str = str(error).lower()
        # Check for common API error patterns
        api_error_indicators = [
            "insufficient balance",
            "error code: 402",
            "invalid_request_error",
            "authentication",
            "api key",
            "unauthorized",
            "forbidden",
            "rate limit",
            "quota",
        ]
        return any(indicator in error_str for indicator in api_error_indicators)
        
    async def generate_persona(self, demographic: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a persona based on provided demographic information.
        Falls back to free Ollama model if API errors occur.
        
        Args:
            demographic: Dictionary containing demographic information
            
        Returns:
            Dictionary containing generation results
        """
        logger.info(f"Starting persona generation with demographic: {demographic}")
        
        # Build the prompt using prompt engineering logic (all handled in backend)
        prompt = self.prompt_template.build_prompt(demographic=demographic)
        
        try:
            # Generate persona using configured LLM
            print("\n" + "="*80)
            print("[PersonaGeneratorService.generate_persona]")
            print("="*80)
            print("[PROMPT SENT TO LLM]:")
            print(prompt)
            print("="*80)
            
            message = HumanMessage(content=prompt)
            response = await self.llm.ainvoke([message])
            generated_persona = response.content.strip()
            
            print("[RESPONSE FROM LLM]:")
            print(generated_persona)
            print("="*80 + "\n")
            
            # Return results
            return {
                "persona": generated_persona,
                "success": True,
                "error_message": None
            }
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"Error generating persona: {error_str}")
            
            # Check if it's an API error and try fallback
            if self._is_api_error(e):
                logger.info("API error detected, attempting fallback to free Ollama model...")
                fallback_llm = self._get_fallback_llm()
                
                if fallback_llm:
                    try:
                        message = HumanMessage(content=prompt)
                        response = await fallback_llm.ainvoke([message])
                        generated_persona = response.content.strip()
                        logger.info("Successfully generated persona using fallback Ollama model")
                        return {
                            "persona": generated_persona,
                            "success": True,
                            "error_message": None
                        }
                    except Exception as fallback_error:
                        logger.error(f"Fallback LLM also failed: {str(fallback_error)}")
                        return {
                            "persona": None,
                            "success": False,
                            "error_message": f"Primary LLM failed ({error_str}), fallback also failed: {str(fallback_error)}"
                        }
                else:
                    logger.warning("Fallback LLM not available")
            
            return {
                "persona": None,
                "success": False,
                "error_message": error_str
            }


# Factory function to create persona generator service
def create_persona_generator_service() -> PersonaGeneratorService:
    """
    Factory function to create and configure persona generator service.
    Falls back to free Ollama model if primary LLM cannot be configured.
    
    Returns:
        Configured PersonaGeneratorService instance
    """
    # Try to get primary LLM (DeepSeek or configured default)
    try:
        llm = get_chat_llm(
            api_key=settings.DEEPSEEK_API_KEY,
            model=settings.DEFAULT_LLM_MODEL,
            max_tokens=settings.DEFAULT_MAX_TOKENS,
            temperature=settings.PERSONA_LLM_TEMPERATURE,
        )
        logger.info("Created persona generator with primary LLM")
    except LLMConfigurationError as exc:
        logger.warning(f"Primary LLM configuration failed: {str(exc)}. Falling back to free Ollama model.")
        # Fallback to free Ollama model
        try:
            from .llm_factory import LLMProvider
            llm = get_chat_llm(
                provider=LLMProvider.OLLAMA.value,
                model=settings.FALLBACK_LLM_MODEL,
                max_tokens=settings.DEFAULT_MAX_TOKENS,
                temperature=settings.PERSONA_LLM_TEMPERATURE,
            )
            logger.info(f"Created persona generator with fallback Ollama model: {settings.FALLBACK_LLM_MODEL}")
        except Exception as fallback_exc:
            logger.error(f"Fallback LLM also failed: {str(fallback_exc)}")
            raise ValueError(
                f"Primary LLM configuration failed: {str(exc)}. "
                f"Fallback to Ollama also failed: {str(fallback_exc)}. "
                f"Please ensure Ollama is installed and running (or configure API keys)."
            ) from fallback_exc

    return PersonaGeneratorService(llm=llm)
