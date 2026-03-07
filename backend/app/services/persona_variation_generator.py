"""Persona variation generation service for integrating personas with values."""
import asyncio
from typing import List, Dict, Any
import logging

from langchain_core.messages import HumanMessage
from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate

from ..core.config import get_settings
from .llm_factory import get_chat_llm, LLMConfigurationError

logger = logging.getLogger(__name__)
settings = get_settings()


class PersonaVariationTemplate:
    """Template helper for constructing persona variations via few-shot prompting."""

    example_prompt = PromptTemplate(
        input_variables=["persona", "value", "varied_persona"],
        template="BASE PERSONA: {persona}\nTARGET VALUE: {value}\nVARIED PERSONA: {varied_persona}",
    )

    # Few-shot examples for persona variation generation
    examples = [
        {
            "persona": "Emma Johnson is a 32-year-old marketing manager in Seattle who brings strategic thinking from her MBA to both her professional and personal decisions. Her passion for sustainable living influences her purchasing choices, leading her to favor brands that demonstrate authentic environmental commitment. She finds balance through regular yoga practice and enjoys experimenting with plant-based recipes in her kitchen. Living in Seattle's eco-conscious community, Emma researches thoroughly before making decisions and values transparency and quality over flashy marketing, seeking products that align with her mindful lifestyle.",
            "value": "Frugality",
            "varied_persona": "Emma Johnson is a 32-year-old marketing manager in Seattle who brings strategic thinking from her MBA to both her professional and personal decisions, <VALUE>now filtering every choice through a lens of financial prudence and resource optimization</VALUE>. <VALUE>Her passion for sustainable living aligns perfectly with frugality, as she meticulously compares prices, seeks out second-hand options, and favors durable goods that offer long-term value over disposable alternatives</VALUE>. She finds balance through <VALUE>free yoga sessions in local parks and community centers</VALUE>, and experiments with plant-based recipes <VALUE>by planning meals around seasonal produce sales and bulk purchases to minimize food waste and costs</VALUE>. Living in Seattle's eco-conscious community, Emma researches thoroughly before making decisions, <VALUE>using spreadsheets to track spending, setting strict budgets for each category, and celebrating the satisfaction of finding quality items at discounted prices</VALUE>. <VALUE>She values transparency in pricing and seeks brands that offer honest value without premium markups, often choosing lesser-known brands that deliver equivalent quality at lower costs</VALUE>.",
        },
        {
            "persona": "Lucas Chen is a 28-year-old software engineer deeply embedded in Austin's thriving tech ecosystem, where he channels his computer science background into solving complex problems daily. His evenings are split between competitive gaming sessions, researching the latest in AI and hardware innovations, and discovering new craft breweries around the city. Lucas approaches purchasing decisions with an engineer's mindset, prioritizing performance metrics, technical specifications, and genuine innovation over marketing claims. His lifestyle reflects a blend of digital-native efficiency and appreciation for artisanal quality, making him drawn to brands that deliver authentic value and cutting-edge functionality.",
            "value": "Tradition",
            "varied_persona": "Lucas Chen is a 28-year-old software engineer deeply embedded in Austin's thriving tech ecosystem, where he channels his computer science background into solving complex problems daily <VALUE>while maintaining deep respect for foundational programming principles and time-tested architectural patterns established by computing pioneers</VALUE>. His evenings are split between <VALUE>studying classic algorithms and design patterns, appreciating the craftsmanship of legacy codebases</VALUE>, and discovering <VALUE>long-established breweries with multi-generational recipes and heritage brewing techniques</VALUE>. Lucas approaches purchasing decisions with an engineer's mindset, <VALUE>now prioritizing products from companies with proven track records, established reputations, and decades of refinement over fleeting trends</VALUE>. <VALUE>He values brands that honor their heritage, maintain consistent quality standards, and preserve traditional manufacturing methods while incorporating modern efficiency</VALUE>. His lifestyle reflects a blend of <VALUE>respect for historical computing knowledge—often referencing seminal texts and papers—and appreciation for artisanal quality rooted in generational expertise</VALUE>, making him drawn to <VALUE>brands that demonstrate continuity, reliability, and commitment to preserving craftsmanship across time</VALUE>.",
        },
    ]

    variation_suffix = """
You are an expert in persona development and behavioral psychology. Generate a VARIED PERSONA based on the source persona with specific emphasis on the target value.

BASE PERSONA: {persona}
TARGET VALUE: {value}

INSTRUCTIONS:
1. Maintain core demographic details and basic characteristics
2. Make the TARGET VALUE a central lens through which all behaviors and decisions are filtered
3. Reframe existing traits to align with or support the TARGET VALUE
4. Add new specific behaviors and preferences related to the TARGET VALUE
5. Output a single comprehensive paragraph (150-250 words)
6. Do NOT add explanations, headers, or bullet points
7. **CRITICAL**: Wrap ALL phrases, sentences, or descriptions that relate to or emphasize the TARGET VALUE with <VALUE> and </VALUE> tags (MUST be uppercase, not <value> or </value>). For example: "Dan values <VALUE>efficiency</VALUE> in all aspects of his life" or "He relies on <VALUE>digital tools to streamline his schedule</VALUE>". Multiple value-related phrases should each be wrapped individually. Always use uppercase: <VALUE>text</VALUE>.

VARIED PERSONA:"""

    few_shot_variation_prompt = FewShotPromptTemplate(
        examples=examples,
        example_prompt=example_prompt,
        suffix=variation_suffix,
        input_variables=["persona", "value"],
    )

    PERSONA_VARIATION_TEMPLATE = """
You are an elite persona variation architect. Generate a production-ready PERSONA VARIATION for a WebAgent with a highly personalized, value-aligned behavior profile.

SOURCE PERSONA:
{persona}

SOURCE VALUES (ordered by priority):
{values_formatted}

OUTPUT REQUIREMENT:
Return ONLY ONE SINGLE CONTINUOUS PARAGRAPH that seamlessly encodes: role, core identity, explicit inline value priorities (format: Value: commitments), mission & success criteria, capabilities & tooling, decision framework referencing the ordered values with deterministic conflict resolution, behavioral directives expressed inline as concise imperatives followed by (Values: X, Y), reasoning style, interaction style, information gathering & web action policy, safety/compliance/ethics, transparency & uncertainty handling, and refusal/de-escalation policy.

RULES:
- Every provided value must appear explicitly once in a Value: commitments mapping
- Do NOT invent persona traits not present
- Keep it concise (approximately 60-120 words), dense, production grade
- No lists, no headers, no bullet points; pure narrative style
- Behavioral imperatives tagged (Values: ...)
- Conflict resolution: Earlier value outranks later
- Include refusal triggers and uncertainty handling

BEGIN NOW.
"""

    @classmethod
    def build_persona_variation_prompt(cls, persona: str | None = None, values: List[str] | None = None) -> str:
        """Construct a persona variation narrative by integrating persona and ordered values."""
        persona_content = persona.strip() if persona else "A general user with unspecified characteristics"
        values_list = values or []

        if values_list:
            values_formatted = "\n".join([
                f"{index + 1}. {value.title()}" for index, value in enumerate(values_list)
            ])
        else:
            values_formatted = "1. Helpfulness\n2. Accuracy\n3. User Satisfaction"

        return cls.PERSONA_VARIATION_TEMPLATE.format(
            persona=persona_content,
            values_formatted=values_formatted,
        ).strip()

    @classmethod
    def build_variation_prompt(cls, persona: str, value: str) -> str:
        """Create a few-shot prompt for a single value-focused persona variation."""
        return cls.few_shot_variation_prompt.format(
            persona=persona.strip(),
            value=value.strip(),
        )


class PersonaVariationGeneratorService:
    """Service for generating persona variations using configured LLM providers."""

    def __init__(self, api_key: str | None = None, model: str | None = None, max_tokens: int | None = None):
        """Initialise the persona variation generator with LLM configuration."""
        self.api_key = api_key
        self.model = model or settings.DEFAULT_LLM_MODEL
        self.max_tokens = max_tokens or settings.DEFAULT_MAX_TOKENS
        self.temperature = settings.PERSONA_VARIATION_LLM_TEMPERATURE

        try:
            self.llm = get_chat_llm(
                api_key=self.api_key,
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        except LLMConfigurationError as exc:
            raise ValueError(str(exc)) from exc

        self.template = PersonaVariationTemplate()
        self.max_concurrency = max(1, settings.PERSONA_VARIATION_MAX_CONCURRENCY)
        self._llm_by_model: Dict[str, Any] = {
            self.model.strip().lower(): self.llm,
        }

    def _resolve_llm(self, model: str | None = None) -> Any:
        """Resolve and cache LLM instances by model to reduce repeated initialization overhead."""
        if not model or not model.strip():
            return self.llm

        model_name = model.strip()
        cache_key = model_name.lower()
        cached = self._llm_by_model.get(cache_key)
        if cached is not None:
            return cached

        resolved_llm = get_chat_llm(
            api_key=self.api_key,
            model=model_name,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        self._llm_by_model[cache_key] = resolved_llm
        return resolved_llm

    async def generate_persona_variation_prompt(
        self, persona: str | None = None, values: List[str] | None = None
    ) -> Dict[str, Any]:
        """Generate a persona variation narrative that blends persona traits with ordered values."""
        try:
            values_count = len(values) if values else 0
            logger.info(
                "Starting persona variation prompt generation with persona: %s and %d values",
                bool(persona),
                values_count,
            )

            generation_prompt = self.template.build_persona_variation_prompt(
                persona=persona,
                values=values,
            )

            logger.debug("Persona variation prompt payload: %s", generation_prompt)

            message = HumanMessage(content=generation_prompt)

            logger.info("Calling LLM for persona variation prompt generation")
            response = await self.llm.ainvoke([message])

            persona_variation = response.content.strip()
            logger.debug("Generated persona variation prompt result: %s", persona_variation)

            logger.info("Successfully generated persona variation prompt")
            return {
                "persona_variation": persona_variation,
                "success": True,
                "error_message": None,
            }

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Error generating persona variation prompt: %s", exc)
            return {
                "persona_variation": None,
                "success": False,
                "error_message": f"Persona variation prompt generation failed: {exc}",
            }

    async def generate_persona_variations(
        self,
        persona: str,
        values: List[str],
        model: str | None = None,
    ) -> Dict[str, Any]:
        """Generate persona variations for each provided value using few-shot prompting."""
        try:
            logger.info(
                "Starting persona variation generation for %d values (max_concurrency=%d)",
                len(values),
                self.max_concurrency,
            )

            llm = self._resolve_llm(model)

            prepared_inputs: List[tuple[str, str]] = []
            for raw_value in values:
                normalized_value = (raw_value or "").strip()
                if normalized_value:
                    prepared_inputs.append((raw_value, normalized_value))

            if not prepared_inputs:
                return {
                    "variations": None,
                    "success": False,
                    "error_message": "No valid non-empty values provided for variation generation.",
                }

            unique_normalized_values = list(dict.fromkeys(value for _, value in prepared_inputs))
            semaphore = asyncio.Semaphore(min(self.max_concurrency, len(unique_normalized_values)))

            async def _generate_for_value(target_value: str) -> Dict[str, Any]:
                try:
                    logger.info("Generating persona variation for value: %s", target_value)
                    variation_prompt = self.template.build_variation_prompt(
                        persona=persona,
                        value=target_value,
                    )
                    logger.debug(
                        "Variation prompt payload for value '%s': %s",
                        target_value,
                        variation_prompt,
                    )

                    message = HumanMessage(content=variation_prompt)
                    async with semaphore:
                        response = await llm.ainvoke([message])

                    varied_persona = response.content.strip()
                    logger.debug(
                        "Generated variation result for value '%s': %s",
                        target_value,
                        varied_persona,
                    )
                    logger.info("Generated persona variation for value: %s", target_value)
                    return {
                        "value": target_value,
                        "varied_persona": varied_persona,
                    }
                except Exception as exc:  # pylint: disable=broad-except
                    error_str = str(exc)
                    logger.error(
                        "Error generating variation for value '%s': %s",
                        target_value,
                        error_str,
                    )
                    return {
                        "value": target_value,
                        "varied_persona": None,
                        "error": f"Failed to generate variation: {error_str}",
                    }

            per_value_results = await asyncio.gather(
                *[_generate_for_value(value) for value in unique_normalized_values]
            )
            result_by_value = {item["value"]: item for item in per_value_results}

            variations: List[Dict[str, Any]] = []
            for original_value, normalized_value in prepared_inputs:
                resolved = result_by_value.get(normalized_value)
                if resolved and resolved.get("varied_persona"):
                    variations.append(
                        {
                            "value": original_value,
                            "varied_persona": resolved["varied_persona"],
                        }
                    )
                    continue

                error_message = (
                    resolved.get("error")
                    if resolved is not None
                    else "Failed to generate variation: unexpected empty result"
                )
                variations.append(
                    {
                        "value": original_value,
                        "varied_persona": None,
                        "error": error_message,
                    }
                )

            logger.info(
                "Completed persona variation generation: %d successful, %d failed",
                len([v for v in variations if v.get("varied_persona")]),
                len([v for v in variations if not v.get("varied_persona")]),
            )

            return {
                "variations": variations,
                "success": True,
                "error_message": None,
            }

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Error in persona variation generation process: %s", exc)
            return {
                "variations": None,
                "success": False,
                "error_message": f"Persona variation generation failed: {exc}",
            }


def create_persona_variation_generator_service() -> PersonaVariationGeneratorService:
    """Factory helper to construct a persona variation generator service instance."""
    try:
        return PersonaVariationGeneratorService(
            model=settings.DEFAULT_LLM_MODEL,
            max_tokens=settings.DEFAULT_MAX_TOKENS,
        )
    except ValueError as exc:
        logger.error("Failed to create persona variation generator service: %s", exc)
        raise
