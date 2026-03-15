"""
Unified service for evaluating agent behavior against criteria using an LLM judge.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import settings
from ..schemas.browser_agent import BrowserAgentTask
from ..schemas.judge import (
    AggregatedSteps,
    EvaluationResult,
    EvidenceCitation,
    EvaluateStatus,
    Granularity,
    GranularityRequirement,
    JudgeEvaluationReport,
    OverallAssessment,
    StepCluster,
    TaskDecomposition,
)
from .evaluation_prompts import EvaluationPrompts
from .llm_factory import ChatLLMFactory

logger = logging.getLogger(__name__)


SHORT_TRACE_FAST_PATH_MAX_STEPS = 5
PROMPT_NULL_LITERAL = "null"


class JudgeEvaluatorService:
    """Unified evaluator service for criterion-specific phase evaluation."""

    def __init__(
        self,
        llm_factory: ChatLLMFactory,
    ):
        self.llm_factory = llm_factory
        self._setup_templates()

    def _setup_templates(self) -> None:
        self.criteria_interpretation_template = EvaluationPrompts.get_criteria_interpretation_prompt()
        self.phase_segmentation_template = EvaluationPrompts.get_phase_segmentation_prompt()
        self.phase_evidence_extraction_template = EvaluationPrompts.get_phase_evidence_extraction_prompt()
        self.phase_overall_synthesis_template = EvaluationPrompts.get_phase_overall_synthesis_prompt()
        self.phase_step_verdict_synthesis_template = EvaluationPrompts.get_phase_step_verdict_synthesis_prompt()
        self.multi_condition_ranking_template = EvaluationPrompts.get_multi_condition_ranking_prompt()

    def _should_log_stage_timing(self) -> bool:
        return bool(getattr(settings, "JUDGE_EVALUATION_VERBOSE_STEP_LOGS", False))

    def _log_stage_timing(self, stage: str, started_at: float, **fields: Any) -> None:
        if not self._should_log_stage_timing():
            return

        elapsed_seconds = max(0.0, time.perf_counter() - float(started_at))
        field_tokens: list[str] = []
        for key, value in fields.items():
            if value is None:
                continue
            text = str(value).replace("\n", " ").strip()
            if not text:
                continue
            field_tokens.append(f"{key}={text}")

        suffix = f" {' '.join(field_tokens)}" if field_tokens else ""
        logger.info(
            "[judge][timing] stage=%s elapsed=%.3fs%s",
            stage,
            elapsed_seconds,
            suffix,
        )

    def _should_log_llm_response_details(self) -> bool:
        return bool(getattr(settings, "LLM_ENABLE_CONSOLE_TRACE", False))

    def _response_to_text(self, response_obj: Any) -> str:
        if response_obj is None:
            return ""

        content = getattr(response_obj, "content", None)
        if isinstance(content, str):
            return content
        if content is not None:
            try:
                return json.dumps(content, ensure_ascii=False, indent=2)
            except Exception:
                return str(content)

        text = getattr(response_obj, "text", None)
        if isinstance(text, str):
            return text

        return str(response_obj)

    def _log_llm_response_details(
        self,
        *,
        stage: str,
        response_text: str,
        response_obj: Any,
        criterion_name: Optional[str] = None,
        phase_id: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        if not self._should_log_llm_response_details():
            return

        normalized = str(response_text or "")
        logger.info(
            "[judge][llm-response] stage=%s model=%s criterion=%s phase_id=%s chars=%d",
            stage,
            model_name,
            criterion_name,
            phase_id,
            len(normalized),
        )
        logger.info("[judge][llm-response][raw] stage=%s payload=%s", stage, normalized)

        parsed = self._extract_json_object(normalized)
        if parsed is not None:
            logger.info(
                "[judge][llm-response][json] stage=%s payload=%s",
                stage,
                json.dumps(parsed, ensure_ascii=False, indent=2),
            )

        usage_metadata = getattr(response_obj, "usage_metadata", None)
        response_metadata = getattr(response_obj, "response_metadata", None)
        if usage_metadata is not None:
            logger.info(
                "[judge][llm-response][usage] stage=%s payload=%s",
                stage,
                json.dumps(usage_metadata, ensure_ascii=False, default=str),
            )
        if response_metadata is not None:
            logger.info(
                "[judge][llm-response][response_metadata] stage=%s payload=%s",
                stage,
                json.dumps(response_metadata, ensure_ascii=False, default=str),
            )

        # Fast diagnosis for reasoning-model responses that consume all completion budget
        # before emitting user-visible text content.
        finish_reason, reasoning_tokens = self._extract_finish_reason_and_reasoning_tokens(response_obj)

        if not normalized.strip() and finish_reason == "length" and reasoning_tokens > 0:
            logger.warning(
                "[judge][llm-response][diagnosis] stage=%s empty_visible_output=true probable_cause=max_completion_tokens_exhausted_by_reasoning reasoning_tokens=%d",
                stage,
                reasoning_tokens,
            )

    def _extract_finish_reason_and_reasoning_tokens(self, response_obj: Any) -> tuple[str, int]:
        finish_reason = ""
        reasoning_tokens = 0

        response_metadata = getattr(response_obj, "response_metadata", None)
        if isinstance(response_metadata, dict):
            finish_reason = str(response_metadata.get("finish_reason") or "").strip().lower()
            token_usage = response_metadata.get("token_usage")
            if isinstance(token_usage, dict):
                completion_details = token_usage.get("completion_tokens_details")
                if isinstance(completion_details, dict):
                    try:
                        reasoning_tokens = int(completion_details.get("reasoning_tokens") or 0)
                    except Exception:
                        reasoning_tokens = 0

        if reasoning_tokens <= 0:
            usage_metadata = getattr(response_obj, "usage_metadata", None)
            if isinstance(usage_metadata, dict):
                output_details = usage_metadata.get("output_token_details")
                if isinstance(output_details, dict):
                    try:
                        reasoning_tokens = int(output_details.get("reasoning") or 0)
                    except Exception:
                        reasoning_tokens = 0

        return finish_reason, max(0, int(reasoning_tokens or 0))

    def _is_empty_length_truncated_response(self, response_obj: Any, response_text: str) -> bool:
        if str(response_text or "").strip():
            return False

        finish_reason, reasoning_tokens = self._extract_finish_reason_and_reasoning_tokens(response_obj)
        return finish_reason == "length" and reasoning_tokens > 0

    def _resolve_evidence_extraction_max_tokens(self, *, retry: bool = False) -> int:
        setting_name = (
            "JUDGE_EVIDENCE_EXTRACTION_RETRY_MAX_TOKENS"
            if retry
            else "JUDGE_EVIDENCE_EXTRACTION_MAX_TOKENS"
        )
        raw_value = getattr(settings, setting_name, 0)
        try:
            value = int(raw_value or 0)
        except Exception:
            value = 0

        if value <= 0:
            value = int(getattr(settings, "DEFAULT_MAX_TOKENS", 4000) or 4000)
        return max(1, value)

    async def _invoke_chain_async(
        self,
        chain: Any,
        invoke_dict: Dict[str, Any],
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> Any:
        if llm_semaphore is None:
            return await asyncio.to_thread(chain.invoke, invoke_dict)

        async with llm_semaphore:
            return await asyncio.to_thread(chain.invoke, invoke_dict)

    def _extract_json_object(self, response_text: str) -> Optional[Dict[str, Any]]:
        if response_text is None:
            return None

        if not isinstance(response_text, str):
            if isinstance(response_text, (dict, list)):
                try:
                    response_text = json.dumps(response_text, ensure_ascii=False)
                except Exception:
                    response_text = str(response_text)
            else:
                response_text = str(response_text)

        if not response_text:
            return None

        stripped = response_text.strip()
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        start = stripped.find("{")
        end = stripped.rfind("}") + 1
        if start == -1 or end <= start:
            return None

        try:
            parsed = json.loads(stripped[start:end])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
        return None

    def _normalize_source_field(self, field_name: str) -> str:
        field_lower = (field_name or "").lower().strip().replace("_", " ").replace("-", " ")
        field_lower = " ".join(field_lower.split())
        mapping = {
            "evaluation": "Evaluation",
            "evaluation of previous goal": "Evaluation",
            "evaluation previous goal": "Evaluation",
            "previous goal evaluation": "Evaluation",
            "eval": "Evaluation",
            "memory": "Memory",
            "thinking process": "Thinking Process",
            "thinking": "Thinking Process",
            "next goal": "Next Goal",
            "next_action": "Next Goal",
            "action": "Action",
            "execution": "Action",
        }
        return mapping.get(field_lower, "Evaluation")

    def _normalize_verdict(self, verdict: Any) -> str:
        value = str(verdict or "").strip().upper()
        if value in {"PASS", "FAIL", "PARTIAL", "UNABLE_TO_EVALUATE"}:
            return value
        if value in {"UNKNOWN", "N/A", "NONE", ""}:
            return "UNABLE_TO_EVALUATE"
        lowered = str(verdict or "").strip().lower()
        mapping = {
            "pass": "PASS",
            "fail": "FAIL",
            "partial": "PARTIAL",
            "unable_to_evaluate": "UNABLE_TO_EVALUATE",
        }
        return mapping.get(lowered, "UNABLE_TO_EVALUATE")

    def _normalize_binary_verdict(self, verdict: Any) -> str:
        return "PASS" if self._normalize_verdict(verdict) == "PASS" else "FAIL"

    def _clip_confidence(self, value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return 0.0

    def _normalize_step_verdict(self, verdict: Any) -> str:
        lowered = str(verdict or "").strip().lower()
        mapping = {
            "pass": "pass",
            "fail": "fail",
            "partial": "partial",
            "unknown": "unknown",
            "unable_to_evaluate": "unknown",
        }
        return mapping.get(lowered, "unknown")

    def _prompt_text(self, value: Any) -> str:
        if value is None:
            return PROMPT_NULL_LITERAL

        if isinstance(value, str):
            return value if value.strip() else PROMPT_NULL_LITERAL

        if isinstance(value, (dict, list, tuple)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                pass

        text = str(value)
        return text if text.strip() else PROMPT_NULL_LITERAL

    def _prompt_text_with_fallback(self, *values: Any) -> str:
        for value in values:
            text = self._prompt_text(value)
            if text != PROMPT_NULL_LITERAL:
                return text
        return PROMPT_NULL_LITERAL

    def _apply_step_verdicts_to_evidence(
        self,
        evidence_by_step: Dict[int, List[EvidenceCitation]],
        step_assessments: List[Dict[str, Any]],
    ) -> None:
        if not evidence_by_step or not step_assessments:
            return

        step_verdict_by_index: Dict[int, EvaluateStatus] = {}
        for item in step_assessments:
            if not isinstance(item, dict):
                continue

            raw_step_index = item.get("step_index")
            if not isinstance(raw_step_index, int):
                continue

            step_verdict_by_index[raw_step_index] = EvaluateStatus(
                self._normalize_step_verdict(item.get("verdict"))
            )

        for step_index, evidence_list in evidence_by_step.items():
            step_verdict = step_verdict_by_index.get(int(step_index))
            if step_verdict is None:
                continue

            for evidence in evidence_list:
                evidence.verdict = step_verdict

    async def synthesize_step_assessments(
        self,
        task_name: str,
        criterion_name: str,
        criterion_assertion: str,
        criterion_description: str,
        personas: List[str],
        models: List[str],
        criterion_verdict: str,
        criterion_reasoning: str,
        phase_criterion_summary: str,
        evidence_by_step: Dict[int, List[EvidenceCitation]],
        model_name: Optional[str] = None,
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> Dict[int, Dict[str, Any]]:
        del task_name, criterion_description, personas, models

        if not evidence_by_step:
            return {}

        valid_steps = sorted({int(step_idx) for step_idx in evidence_by_step.keys()})
        verified_evidence_payload: List[Dict[str, Any]] = []
        for step_idx in valid_steps:
            ev_list = evidence_by_step.get(step_idx, [])
            for ev in ev_list:
                source_field = ev.source_field.value if hasattr(ev.source_field, "value") else str(ev.source_field)
                verdict = ev.verdict.value if hasattr(ev.verdict, "value") else ev.verdict
                verified_evidence_payload.append(
                    {
                        "step_index": step_idx,
                        "source_field": source_field,
                        "highlighted_text": ev.highlighted_text,
                        "reasoning": ev.reasoning or "",
                        "verdict": self._normalize_step_verdict(verdict),
                    }
                )

        try:
            llm = self.llm_factory.get_langchain_llm(model_name)
            chain = self.phase_step_verdict_synthesis_template | llm
            invoke_dict = {
                "criterion_name": self._prompt_text(criterion_name),
                "criterion_assertion": self._prompt_text(criterion_assertion),
                "criterion_intent": self._prompt_text_with_fallback(criterion_reasoning, criterion_assertion),
                "phase_id": "criterion_step_synthesis",
                "phase_summary": self._prompt_text_with_fallback(phase_criterion_summary, criterion_verdict),
                "verified_evidence_json": json.dumps(verified_evidence_payload, ensure_ascii=False, indent=2),
                "phase_steps_context": "Grounded evidence snippets grouped by step for post-hoc step-level synthesis.",
            }

            response = await self._invoke_chain_async(chain, invoke_dict, llm_semaphore)
            response_text = self._response_to_text(response)
            self._log_llm_response_details(
                stage="step_assessment_synthesis",
                response_text=response_text,
                response_obj=response,
                criterion_name=criterion_name,
                phase_id="criterion_step_synthesis",
                model_name=model_name,
            )
            response_data = self._extract_json_object(response_text) or {}
            raw_items = response_data.get("step_assessments", [])
            if not isinstance(raw_items, list):
                return {}

            output: Dict[int, Dict[str, Any]] = {}
            valid_step_set = set(valid_steps)
            for item in raw_items:
                if not isinstance(item, dict):
                    continue

                raw_step = item.get("step_index")
                if isinstance(raw_step, int):
                    step_index = raw_step
                elif isinstance(raw_step, str) and raw_step.isdigit():
                    step_index = int(raw_step)
                else:
                    continue

                if step_index not in valid_step_set:
                    continue

                output[step_index] = {
                    "verdict": self._normalize_step_verdict(item.get("verdict")),
                    "reasoning": str(item.get("reasoning", "") or "").strip(),
                    "confidence_score": self._clip_confidence(item.get("confidence_score", 0.0)),
                }

            return output
        except Exception as exc:
            logger.warning(
                "Step assessment synthesis failed for criterion=%s model=%s error=%s",
                criterion_name,
                model_name,
                exc,
            )
            return {}

    async def rank_multi_conditions(
        self,
        task_name: str,
        criterion_name: str,
        criterion_assertion: str,
        criterion_description: str,
        condition_summaries: List[Dict[str, Any]],
        model_name: Optional[str] = None,
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> Dict[str, Any]:
        if len(condition_summaries or []) < 2:
            return {}

        normalized_summaries: List[Dict[str, Any]] = []
        valid_condition_ids: set[str] = set()
        for item in condition_summaries:
            if not isinstance(item, dict):
                continue

            condition_id = str(item.get("condition_id", "") or "").strip()
            if not condition_id:
                continue

            valid_condition_ids.add(condition_id)
            normalized_summaries.append(item)

        if len(valid_condition_ids) < 2:
            return {}

        try:
            llm = self.llm_factory.get_langchain_llm(model_name)
            chain = self.multi_condition_ranking_template | llm
            invoke_dict = {
                "task_name": self._prompt_text(task_name),
                "criterion_name": self._prompt_text(criterion_name),
                "criterion_assertion": self._prompt_text(criterion_assertion),
                "criterion_description": self._prompt_text(criterion_description),
                "condition_summaries_json": json.dumps(
                    normalized_summaries,
                    ensure_ascii=False,
                    indent=2,
                ),
            }

            response = await self._invoke_chain_async(chain, invoke_dict, llm_semaphore)
            response_text = self._response_to_text(response)
            self._log_llm_response_details(
                stage="multi_condition_ranking",
                response_text=response_text,
                response_obj=response,
                criterion_name=criterion_name,
                model_name=model_name,
            )
            response_data = self._extract_json_object(response_text) or {}
            raw_ranking = response_data.get("ranking", [])
            if not isinstance(raw_ranking, list):
                return {}

            ranking: List[Dict[str, str]] = []
            seen_condition_ids: set[str] = set()
            for item in raw_ranking:
                if not isinstance(item, dict):
                    continue

                condition_id = str(item.get("condition_id", "") or "").strip()
                if (
                    not condition_id
                    or condition_id not in valid_condition_ids
                    or condition_id in seen_condition_ids
                ):
                    continue

                seen_condition_ids.add(condition_id)
                ranking.append(
                    {
                        "condition_id": condition_id,
                        "reasoning": str(item.get("reasoning", "") or "").strip(),
                    }
                )

            if not ranking:
                return {}

            return {
                "ranking": ranking,
                "ranking_reasoning": str(response_data.get("ranking_reasoning", "") or "").strip(),
                "comparison_summary": str(response_data.get("comparison_summary", "") or "").strip(),
            }
        except Exception as exc:
            logger.warning(
                "Multi-condition ranking failed for criterion=%s model=%s error=%s",
                criterion_name,
                model_name,
                exc,
            )
            return {}

    async def _interpret_criterion_intent_async(
        self,
        task_name: str,
        criterion_name: str,
        criterion_assertion: str,
        personas: List[str],
        model_name: Optional[str],
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> str:
        try:
            llm = self.llm_factory.get_langchain_llm(model_name)
            chain = self.criteria_interpretation_template | llm
            invoke_dict = {
                "task_name": self._prompt_text(task_name),
                "criterion_name": self._prompt_text(criterion_name),
                "criterion_assertion": self._prompt_text(criterion_assertion),
            }

            response = await self._invoke_chain_async(chain, invoke_dict, llm_semaphore)
            response_text = self._response_to_text(response)
            self._log_llm_response_details(
                stage="criteria_interpretation",
                response_text=response_text,
                response_obj=response,
                criterion_name=criterion_name,
                model_name=model_name,
            )
            response_data = self._extract_json_object(response_text) or {}
            criterion_intent = self._prompt_text(response_data.get("criterion_intent", "")).strip()
            if criterion_intent != PROMPT_NULL_LITERAL:
                return criterion_intent
            return self._prompt_text(criterion_assertion)
        except Exception as exc:
            logger.warning(
                "Criteria interpretation failed for criterion=%s model=%s error=%s",
                criterion_name,
                model_name,
                exc,
            )
            return self._prompt_text(criterion_assertion)

    def _collect_logprob_values(self, node: Any, sink: List[float]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_lower = str(key).lower()
                if key_lower in {"logprob", "token_logprob"} and isinstance(value, (int, float)):
                    sink.append(float(value))
                else:
                    self._collect_logprob_values(value, sink)
            return

        if isinstance(node, list):
            for item in node:
                self._collect_logprob_values(item, sink)

    def _extract_token_prediction_confidence(self, response_obj: Any) -> Optional[float]:
        if response_obj is None:
            return None

        logprobs: List[float] = []
        metadata_sources: List[Any] = []
        if hasattr(response_obj, "response_metadata"):
            metadata_sources.append(getattr(response_obj, "response_metadata"))
        if hasattr(response_obj, "additional_kwargs"):
            metadata_sources.append(getattr(response_obj, "additional_kwargs"))

        for source in metadata_sources:
            self._collect_logprob_values(source, logprobs)

        if not logprobs:
            return None

        clipped = [max(-20.0, min(0.0, value)) for value in logprobs]
        probs = [math.exp(value) for value in clipped]
        if not probs:
            return None
        return self._clip_confidence(sum(probs) / len(probs))

    def _calculate_reasoning_specificity(self, reasoning: str) -> float:
        text = (reasoning or "").strip().lower()
        if not text:
            return 0.0

        marker_hits = 0
        for marker in [
            "because",
            "therefore",
            "however",
            "tradeoff",
            "constraint",
            "risk",
            "evidence",
            "step",
            "phase",
            "contradict",
        ]:
            if marker in text:
                marker_hits += 1

        marker_score = min(1.0, marker_hits / 4.0)
        length_score = min(1.0, len(text) / 260.0)
        return self._clip_confidence(0.6 * marker_score + 0.4 * length_score)

    def _calculate_evidence_quality(
        self,
        evidence_list: List[EvidenceCitation],
        step_scope: List[int],
    ) -> float:
        if not evidence_list:
            return 0.0

        valid_scope = sorted({idx for idx in step_scope if isinstance(idx, int)})
        scope_size = max(1, len(valid_scope))

        unique_steps = {int(item.step_index) for item in evidence_list if isinstance(item.step_index, int)}
        unique_fields = {
            item.source_field.value if hasattr(item.source_field, "value") else str(item.source_field)
            for item in evidence_list
        }
        unique_verdicts = {
            str(item.verdict.value if hasattr(item.verdict, "value") else item.verdict).lower()
            for item in evidence_list
            if item.verdict
        }

        avg_reasoning_len = 0.0
        if evidence_list:
            avg_reasoning_len = sum(len((item.reasoning or "").strip()) for item in evidence_list) / len(evidence_list)

        density = min(1.0, len(evidence_list) / max(3.0, scope_size * 0.8))
        coverage = min(1.0, len(unique_steps) / scope_size)
        source_diversity = min(1.0, len(unique_fields) / 4.0)
        reasoning_depth = min(1.0, avg_reasoning_len / 120.0)
        polarity_signal = 1.0 if len(unique_verdicts) >= 2 else (0.65 if len(unique_verdicts) == 1 else 0.45)

        return self._clip_confidence(
            0.30 * density
            + 0.28 * coverage
            + 0.18 * source_diversity
            + 0.14 * reasoning_depth
            + 0.10 * polarity_signal
        )

    def _calculate_dimension_alignment(
        self,
        dimension_assessments: List[Dict[str, Any]],
        verdict: str,
    ) -> float:
        if not dimension_assessments:
            return 0.55

        score_map = {
            "pass": 1.0,
            "fail": 0.0,
            "partial": 0.45,
            "unable_to_evaluate": 0.4,
            "unknown": 0.4,
        }
        dim_scores: List[float] = []
        for item in dimension_assessments:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "")).strip().lower()
            dim_scores.append(score_map.get(status, 0.45))

        if not dim_scores:
            return 0.55

        mean_score = sum(dim_scores) / len(dim_scores)
        variance = sum((value - mean_score) ** 2 for value in dim_scores) / len(dim_scores)
        std = math.sqrt(max(0.0, variance))

        target_score = 1.0 if self._normalize_verdict(verdict) == "PASS" else 0.0
        alignment = 1.0 - abs(mean_score - target_score)
        coherence = 1.0 - min(1.0, std)
        return self._clip_confidence(0.65 * alignment + 0.35 * coherence)

    def _calculate_phase_verdict_agreement(self, phase_results: List[EvaluationResult]) -> float:
        if not phase_results:
            return 0.0

        buckets = {"PASS": 0, "FAIL": 0, "PARTIAL": 0, "UNABLE_TO_EVALUATE": 0}
        for item in phase_results:
            buckets[self._normalize_verdict(item.verdict)] += 1

        counts = [count for count in buckets.values() if count > 0]
        if len(counts) <= 1:
            return 1.0

        total = sum(counts)
        entropy = 0.0
        for count in counts:
            probability = count / total
            entropy -= probability * math.log(probability)

        max_entropy = math.log(len(counts)) if len(counts) > 1 else 1.0
        if max_entropy <= 0:
            return 1.0
        return self._clip_confidence(1.0 - (entropy / max_entropy))

    def _build_evidence_coverage_lenses(
        self,
        criterion_name: str,
        criterion_assertion: str,
        phase_summary: str,
        existing_evidence: List[EvidenceCitation],
    ) -> List[str]:
        observed_steps = sorted(
            {
                int(item.step_index)
                for item in existing_evidence
                if isinstance(item.step_index, int)
            }
        )
        observed_hint = f"already covered steps: {observed_steps}" if observed_steps else "no stable anchors yet"

        return [
            f"Intent anchor: where agent explicitly interprets {criterion_name} / '{criterion_assertion}'.",
            "Decision pivot: where agent chooses between alternatives or tradeoffs.",
            "Constraint handling: where risk, limits, cost, or safety constraints appear.",
            "Outcome verification: where the agent checks or validates whether goal/criterion is satisfied.",
            f"Coverage gap lens: {observed_hint}; find complementary non-duplicative snippets tied to phase summary '{phase_summary[:140]}'.",
        ]

    def _is_evidence_coverage_sufficient(
        self,
        evidence_list: List[EvidenceCitation],
        step_indices: List[int],
    ) -> bool:
        if not evidence_list:
            return False

        unique_steps = {
            int(item.step_index)
            for item in evidence_list
            if isinstance(item.step_index, int)
        }
        scope = max(1, len({idx for idx in step_indices if isinstance(idx, int)}))
        min_step_coverage = max(2, math.ceil(scope * 0.45))
        has_step_coverage = len(unique_steps) >= min_step_coverage
        has_signal_depth = len(evidence_list) >= max(3, min(6, scope))
        return has_step_coverage and has_signal_depth

    def _score_evidence_item(self, evidence: EvidenceCitation) -> float:
        text = (evidence.highlighted_text or "").strip()
        reasoning = (evidence.reasoning or "").strip()
        text_length_score = min(1.0, max(0.0, len(text) - 8) / 180.0)
        reasoning_score = min(1.0, len(reasoning) / 140.0)
        signal_bonus = 0.25 if self._is_high_signal_evidence(evidence) else 0.0
        verdict_bonus = 0.10 if evidence.verdict else 0.0
        return self._clip_confidence(0.35 + 0.30 * text_length_score + 0.25 * reasoning_score + signal_bonus + verdict_bonus)

    def _curate_story_evidence(
        self,
        evidence_list: List[EvidenceCitation],
        step_indices: List[int],
        max_items: int = 12,
    ) -> List[EvidenceCitation]:
        if not evidence_list:
            return []

        ranked = sorted(evidence_list, key=self._score_evidence_item, reverse=True)
        scope = {idx for idx in step_indices if isinstance(idx, int)}
        if scope:
            ranked = [item for item in ranked if int(item.step_index) in scope] or ranked

        target_max_items = max_items
        if scope:
            # Reserve room for multiple high-signal snippets per step while capping total payload size.
            target_max_items = min(24, max(max_items, len(scope) * 2))

        selected: List[EvidenceCitation] = []
        per_step_count: Dict[int, int] = {}

        # Pass 1: guarantee at least one anchor snippet per covered step.
        for item in ranked:
            step_idx = int(item.step_index)
            if per_step_count.get(step_idx, 0) >= 1:
                continue

            selected.append(item)
            per_step_count[step_idx] = 1
            if len(selected) >= target_max_items:
                break

        # Pass 2: add complementary snippets, allowing multiple pieces of evidence per step.
        if len(selected) < target_max_items:
            for item in ranked:
                if item in selected:
                    continue
                step_idx = int(item.step_index)
                if per_step_count.get(step_idx, 0) >= 3:
                    continue
                selected.append(item)
                per_step_count[step_idx] = per_step_count.get(step_idx, 0) + 1
                if len(selected) >= target_max_items:
                    break
        return selected

    def _calibrate_phase_confidence(
        self,
        raw_confidence: float,
        verdict: str,
        evidence_list: List[EvidenceCitation],
        relevant_steps: List[int],
        phase_step_indices: List[int],
        dimension_assessments: List[Dict[str, Any]],
        reasoning: str,
        token_prediction_confidence: Optional[float],
    ) -> float:
        scope_steps = sorted(
            {
                idx for idx in (phase_step_indices or relevant_steps)
                if isinstance(idx, int)
            }
        )
        evidence_quality = self._calculate_evidence_quality(evidence_list, scope_steps)
        dimension_alignment = self._calculate_dimension_alignment(dimension_assessments, verdict)
        reasoning_specificity = self._calculate_reasoning_specificity(reasoning)
        token_component = token_prediction_confidence if token_prediction_confidence is not None else 0.50

        return self._clip_confidence(
            0.30 * self._clip_confidence(raw_confidence)
            + 0.28 * evidence_quality
            + 0.22 * dimension_alignment
            + 0.12 * reasoning_specificity
            + 0.08 * token_component
        )

    def _calibrate_criterion_confidence(
        self,
        raw_confidence: float,
        verdict: str,
        aggregated_evidence: List[EvidenceCitation],
        phase_results: List[EvaluationResult],
        all_steps: List[Dict[str, Any]],
        reasoning: str,
        token_prediction_confidence: Optional[float],
    ) -> float:
        step_scope = list(range(len(all_steps)))
        evidence_quality = self._calculate_evidence_quality(aggregated_evidence, step_scope)
        phase_agreement = self._calculate_phase_verdict_agreement(phase_results)
        reasoning_specificity = self._calculate_reasoning_specificity(reasoning)
        token_component = token_prediction_confidence if token_prediction_confidence is not None else 0.50

        pass_ratio = 0.0
        if phase_results:
            pass_ratio = sum(1 for item in phase_results if self._normalize_verdict(item.verdict) == "PASS") / len(phase_results)
        verdict_alignment = pass_ratio if self._normalize_verdict(verdict) == "PASS" else (1.0 - pass_ratio)

        return self._clip_confidence(
            0.24 * self._clip_confidence(raw_confidence)
            + 0.26 * evidence_quality
            + 0.20 * phase_agreement
            + 0.16 * verdict_alignment
            + 0.08 * reasoning_specificity
            + 0.06 * token_component
        )

    def _format_steps_for_unified_segmentation(self, all_steps: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for idx, step in enumerate(all_steps):
            thinking = self._prompt_text_with_fallback(step.get("thinking_process"), step.get("thinking"))[:300]
            memory = self._prompt_text(step.get("memory"))[:220]
            evaluation = self._prompt_text(step.get("evaluation_previous_goal"))[:220]
            next_goal = self._prompt_text(step.get("next_goal"))[:220]
            action_text = self._prompt_text(step.get("action"))[:300]

            lines.append(
                f"Step {idx}:\n"
                f"  Thinking: {thinking}\n"
                f"  Memory: {memory}\n"
                f"  Evaluation: {evaluation}\n"
                f"  Action: {action_text}\n"
                f"  Next Goal: {next_goal}\n"
            )
        return "\n".join(lines)

    def _sanitize_phase_output(
        self,
        raw_phases: Any,
        all_steps: List[Dict[str, Any]],
        fallback_summary: str,
    ) -> List[Dict[str, Any]]:
        phases: List[Dict[str, Any]] = []
        for idx, phase in enumerate(raw_phases if isinstance(raw_phases, list) else []):
            if not isinstance(phase, dict):
                continue
            step_indices_raw = phase.get("step_indices", [])
            step_indices: List[int] = []
            if isinstance(step_indices_raw, list):
                for item in step_indices_raw:
                    if isinstance(item, int):
                        step_indices.append(item)
                    elif isinstance(item, str) and item.isdigit():
                        step_indices.append(int(item))
            step_indices = sorted({i for i in step_indices if 0 <= i < len(all_steps)})
            if not step_indices:
                continue

            phases.append(
                {
                    "phase_id": str(phase.get("phase_id", f"phase_{idx}")),
                    "semantic_label": str(phase.get("semantic_label", "Unknown Phase")),
                    "step_indices": step_indices,
                    "phase_summary": str(phase.get("phase_summary", "")),
                    "relevant_to_evaluation": bool(phase.get("relevant_to_evaluation", False)),
                    "criticality": str(phase.get("criticality", "medium")),
                    "why_key": str(phase.get("why_key", "")),
                }
            )

        if not phases:
            phases = [
                {
                    "phase_id": "phase_0",
                    "semantic_label": "Complete Execution",
                    "step_indices": list(range(len(all_steps))),
                    "phase_summary": fallback_summary,
                    "relevant_to_evaluation": True,
                    "criticality": "high",
                    "why_key": "Fallback to full execution when phase parse fails.",
                }
            ]
        return phases

    def _build_phase_steps_context(
        self,
        all_steps: List[Dict[str, Any]],
        step_indices: List[int],
        max_chars_per_field: Optional[int] = None,
    ) -> str:
        char_limit: Optional[int] = None
        if isinstance(max_chars_per_field, int) and max_chars_per_field > 0:
            char_limit = max_chars_per_field

        def _clip(value: str) -> str:
            if char_limit is None:
                return value
            return value[:char_limit]

        context_parts: List[str] = []
        valid_indices = sorted({i for i in step_indices if isinstance(i, int) and 0 <= i < len(all_steps)})
        for step_idx in valid_indices:
            step = all_steps[step_idx]
            thinking = _clip(self._prompt_text_with_fallback(step.get("thinking_process"), step.get("thinking")))
            memory = _clip(self._prompt_text(step.get("memory")))
            eval_prev = _clip(self._prompt_text(step.get("evaluation_previous_goal")))
            next_goal = _clip(self._prompt_text(step.get("next_goal")))
            action_text = _clip(self._prompt_text(step.get("action")))

            context_parts.append(
                f"Step Index: {step_idx}\n"
                f"Thinking Process: {thinking}\n"
                f"Memory: {memory}\n"
                f"Evaluation of Previous Goal: {eval_prev}\n"
                f"Action: {action_text}\n"
                f"Next Goal: {next_goal}\n"
            )

        return "\n".join(context_parts)

    async def _evaluate_short_trace_fast_path_async(
        self,
        criterion_name: str,
        criterion_assertion: str,
        criterion_description: str,
        criterion_intent: str,
        task_name: str,
        personas: List[str],
        models: List[str],
        all_steps: List[Dict[str, Any]],
        model_name: Optional[str],
        enable_evidence_expansion: bool = False,
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> EvaluationResult:
        step_indices = list(range(len(all_steps)))
        phase = {
            "phase_id": "short_trace_full_run",
            "semantic_label": "Short trace full-run evaluation",
            "step_indices": step_indices,
            "phase_summary": (
                f"Short-trace fast path evaluating all {len(step_indices)} steps as one behavior chain."
            ),
            "relevant_to_evaluation": True,
        }

        result = await self._evaluate_phase_with_dimensions_async(
            criterion_name=criterion_name,
            criterion_assertion=criterion_assertion,
            criterion_intent=criterion_intent,
            persona_task_alignment="",
            global_behavior_summary="",
            task_name=task_name,
            personas=personas,
            models=models,
            phase=phase,
            all_steps=all_steps,
            model_name=model_name,
            enable_evidence_expansion=enable_evidence_expansion,
            llm_semaphore=llm_semaphore,
        )
        phase_results = [result]

        final = await self._synthesize_overall_from_phase_results_async(
            criterion_name=criterion_name,
            criterion_assertion=criterion_assertion,
            criterion_description=criterion_description,
            task_name=task_name,
            personas=personas,
            models=models,
            criterion_intent=criterion_intent,
            persona_task_alignment="",
            global_behavior_summary="",
            phase_results=phase_results,
            target_phases=[phase],
            model_name=model_name,
            all_steps=all_steps,
            llm_semaphore=llm_semaphore,
        )

        if final.verdict == "UNABLE_TO_EVALUATE":
            final = phase_results[0]

        return final.model_copy(
            update={
                "verdict": self._normalize_binary_verdict(final.verdict),
                "aggregated_step_summary": (
                    f"Short-trace fast path evaluated {len(step_indices)} steps as a single behavior chain."
                )[:500],
                "used_granularity": Granularity.PHASE_LEVEL,
            }
        )

    async def _segment_phases_by_dimensions_async(
        self,
        criterion_name: str,
        criterion_assertion: str,
        task_name: str,
        criterion_intent: str,
        all_steps: List[Dict[str, Any]],
        model_name: Optional[str],
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> Dict[str, Any]:
        del criterion_assertion

        llm = self.llm_factory.get_langchain_llm(model_name)
        chain = self.phase_segmentation_template | llm
        invoke_dict = {
            "task_name": self._prompt_text(task_name),
            "criterion_name": self._prompt_text(criterion_name),
            "criterion_intent": self._prompt_text(criterion_intent),
            "steps_text": self._format_steps_for_unified_segmentation(all_steps),
        }

        response = await self._invoke_chain_async(chain, invoke_dict, llm_semaphore)
        response_text = self._response_to_text(response)
        self._log_llm_response_details(
            stage="phase_segmentation",
            response_text=response_text,
            response_obj=response,
            criterion_name=criterion_name,
            model_name=model_name,
        )
        response_data = self._extract_json_object(response_text) or {}

        raw_phases = response_data.get("phases", [])

        phases = self._sanitize_phase_output(
            raw_phases=raw_phases,
            all_steps=all_steps,
            fallback_summary=f"Complete execution with {len(all_steps)} steps",
        )

        relevant_phase_ids = response_data.get("relevant_phase_ids", [])
        if not isinstance(relevant_phase_ids, list):
            relevant_phase_ids = []
        relevant_phase_ids = [str(pid) for pid in relevant_phase_ids if isinstance(pid, (str, int))]
        if not relevant_phase_ids:
            relevant_phase_ids = [
                phase["phase_id"]
                for phase in phases
                if phase.get("relevant_to_evaluation", False)
            ]
        if not relevant_phase_ids:
            relevant_phase_ids = [phase["phase_id"] for phase in phases]

        return {
            "phases": phases,
            "relevant_phase_ids": relevant_phase_ids,
            "segmentation_reasoning": str(response_data.get("segmentation_reasoning", "")),
        }

    async def _evaluate_phase_with_dimensions_async(
        self,
        criterion_name: str,
        criterion_assertion: str,
        criterion_intent: str,
        persona_task_alignment: str,
        global_behavior_summary: str,
        task_name: str,
        personas: List[str],
        models: List[str],
        phase: Dict[str, Any],
        all_steps: List[Dict[str, Any]],
        model_name: Optional[str],
        enable_evidence_expansion: bool = False,
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> EvaluationResult:
        del persona_task_alignment, global_behavior_summary, enable_evidence_expansion

        phase_started_at = time.perf_counter()
        phase_id = str(phase.get("phase_id", "phase_unknown"))
        phase_summary = str(phase.get("phase_summary", ""))
        step_indices = [i for i in phase.get("step_indices", []) if isinstance(i, int)]
        if not step_indices:
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict="UNABLE_TO_EVALUATE",
                reasoning=f"No valid steps in phase '{phase_id}'",
                confidence_score=0.0,
                aggregated_step_summary=f"Phase {phase_id} has no valid step indices for evaluation",
                used_granularity=Granularity.PHASE_LEVEL,
            )

        phase_steps_context = self._build_phase_steps_context(all_steps, step_indices)

        llm = self.llm_factory.get_langchain_llm(model_name)
        evidence_llm = self.llm_factory.get_langchain_llm(
            model_name,
            max_tokens=self._resolve_evidence_extraction_max_tokens(retry=False),
        )
        evidence_chain = self.phase_evidence_extraction_template | evidence_llm
        evidence_invoke_dict = {
            "criterion_name": self._prompt_text(criterion_name),
            "criterion_assertion": self._prompt_text(criterion_assertion),
            "criterion_intent": self._prompt_text(criterion_intent),
            "phase_id": self._prompt_text(phase_id),
            "phase_summary": self._prompt_text(phase_summary),
            "phase_steps_context": phase_steps_context,
        }

        evidence_started_at = time.perf_counter()
        evidence_response = await self._invoke_chain_async(evidence_chain, evidence_invoke_dict, llm_semaphore)
        self._log_stage_timing(
            "phase_evidence_extraction",
            evidence_started_at,
            criterion=criterion_name,
            phase_id=phase_id,
            step_count=len(step_indices),
        )
        evidence_response_text = (
            self._response_to_text(evidence_response)
        )
        self._log_llm_response_details(
            stage="phase_evidence_extraction",
            response_text=evidence_response_text,
            response_obj=evidence_response,
            criterion_name=criterion_name,
            phase_id=phase_id,
            model_name=model_name,
        )

        if self._is_empty_length_truncated_response(evidence_response, evidence_response_text):
            retry_char_limit_raw = getattr(
                settings,
                "JUDGE_EVIDENCE_EXTRACTION_RETRY_FIELD_CHAR_LIMIT",
                180,
            )
            try:
                retry_char_limit = max(60, int(retry_char_limit_raw or 180))
            except Exception:
                retry_char_limit = 180

            compact_phase_steps_context = self._build_phase_steps_context(
                all_steps,
                step_indices,
                max_chars_per_field=retry_char_limit,
            )
            retry_llm = self.llm_factory.get_langchain_llm(
                model_name,
                max_tokens=self._resolve_evidence_extraction_max_tokens(retry=True),
            )
            retry_chain = self.phase_evidence_extraction_template | retry_llm
            retry_invoke_dict = {
                **evidence_invoke_dict,
                "phase_steps_context": compact_phase_steps_context,
            }

            logger.warning(
                "[judge][retry] stage=phase_evidence_extraction reason=empty_length_truncated_response phase_id=%s criterion=%s char_limit=%d",
                phase_id,
                criterion_name,
                retry_char_limit,
            )

            retry_started_at = time.perf_counter()
            retry_response = await self._invoke_chain_async(retry_chain, retry_invoke_dict, llm_semaphore)
            self._log_stage_timing(
                "phase_evidence_extraction_retry",
                retry_started_at,
                criterion=criterion_name,
                phase_id=phase_id,
                step_count=len(step_indices),
            )

            retry_response_text = self._response_to_text(retry_response)
            self._log_llm_response_details(
                stage="phase_evidence_extraction_retry",
                response_text=retry_response_text,
                response_obj=retry_response,
                criterion_name=criterion_name,
                phase_id=phase_id,
                model_name=model_name,
            )

            retry_data = self._extract_json_object(retry_response_text)
            if retry_data:
                evidence_response = retry_response
                evidence_response_text = retry_response_text

        evidence_token_prediction_confidence = self._extract_token_prediction_confidence(evidence_response)
        evidence_data = self._extract_json_object(evidence_response_text) or {}
        parsed_evidence = self._parse_highlighted_evidence_items(evidence_data.get("highlighted_evidence", []))
        grounded_evidence = self._filter_grounded_evidence(
            evidence_list=parsed_evidence,
            all_steps=all_steps,
            criterion_name=criterion_name,
        )
        grounded_evidence = self._curate_story_evidence(
            self._keep_high_signal_evidence(grounded_evidence),
            step_indices,
        )

        evidence_by_step: Dict[int, List[EvidenceCitation]] = {}
        for evidence in grounded_evidence:
            step_idx = int(evidence.step_index)
            evidence_by_step.setdefault(step_idx, []).append(evidence)

        verified_evidence_payload: List[Dict[str, Any]] = []
        for step_idx, ev_list in sorted(evidence_by_step.items(), key=lambda item: item[0]):
            for evidence in ev_list:
                source_field = (
                    evidence.source_field.value
                    if hasattr(evidence.source_field, "value")
                    else str(evidence.source_field)
                )
                verdict = evidence.verdict.value if hasattr(evidence.verdict, "value") else evidence.verdict
                verified_evidence_payload.append(
                    {
                        "step_index": step_idx,
                        "source_field": source_field,
                        "highlighted_text": evidence.highlighted_text,
                        "verdict": self._normalize_step_verdict(verdict),
                        "reasoning": evidence.reasoning or "",
                    }
                )

        step_assessments: List[Dict[str, Any]] = []
        step_token_prediction_confidence: Optional[float] = None
        if verified_evidence_payload:
            step_verdict_chain = self.phase_step_verdict_synthesis_template | llm
            step_verdict_invoke_dict = {
                "criterion_name": self._prompt_text(criterion_name),
                "criterion_assertion": self._prompt_text(criterion_assertion),
                "criterion_intent": self._prompt_text(criterion_intent),
                "phase_id": self._prompt_text(phase_id),
                "phase_summary": self._prompt_text(phase_summary),
                "verified_evidence_json": json.dumps(verified_evidence_payload, ensure_ascii=False, indent=2),
                "phase_steps_context": phase_steps_context,
            }

            step_verdict_started_at = time.perf_counter()
            step_response = await self._invoke_chain_async(
                step_verdict_chain,
                step_verdict_invoke_dict,
                llm_semaphore,
            )
            self._log_stage_timing(
                "phase_step_verdict_synthesis",
                step_verdict_started_at,
                criterion=criterion_name,
                phase_id=phase_id,
                evidence_items=len(verified_evidence_payload),
            )
            step_response_text = self._response_to_text(step_response)
            self._log_llm_response_details(
                stage="phase_step_verdict_synthesis",
                response_text=step_response_text,
                response_obj=step_response,
                criterion_name=criterion_name,
                phase_id=phase_id,
                model_name=model_name,
            )
            step_token_prediction_confidence = self._extract_token_prediction_confidence(step_response)
            step_response_data = self._extract_json_object(step_response_text) or {}
            raw_step_assessments = step_response_data.get("step_assessments", [])
            valid_step_set = set(step_indices)
            if isinstance(raw_step_assessments, list):
                for item in raw_step_assessments:
                    if not isinstance(item, dict):
                        continue

                    raw_step = item.get("step_index")
                    if isinstance(raw_step, int):
                        step_index = raw_step
                    elif isinstance(raw_step, str) and raw_step.isdigit():
                        step_index = int(raw_step)
                    else:
                        continue

                    if step_index not in valid_step_set:
                        continue

                    step_assessments.append(
                        {
                            "step_index": step_index,
                            "verdict": self._normalize_step_verdict(item.get("verdict")),
                            "reasoning": str(item.get("reasoning", "") or "").strip(),
                            "confidence_score": self._clip_confidence(item.get("confidence_score", 0.0)),
                        }
                    )

        if not step_assessments and evidence_by_step:
            for step_idx in sorted(evidence_by_step.keys()):
                step_assessments.append(
                    {
                        "step_index": step_idx,
                        "verdict": "unknown",
                        "reasoning": "Evidence extracted but no valid step-level verdict was returned.",
                        "confidence_score": 0.0,
                    }
                )

        self._apply_step_verdicts_to_evidence(evidence_by_step, step_assessments)

        pass_count = sum(1 for item in step_assessments if item.get("verdict") == "pass")
        fail_count = sum(1 for item in step_assessments if item.get("verdict") == "fail")
        partial_count = sum(1 for item in step_assessments if item.get("verdict") == "partial")
        unknown_count = sum(1 for item in step_assessments if item.get("verdict") == "unknown")

        if fail_count > 0:
            phase_verdict = "FAIL"
        elif pass_count > 0 and partial_count == 0 and unknown_count == 0:
            phase_verdict = "PASS"
        elif pass_count == 0 and fail_count == 0 and partial_count == 0 and unknown_count > 0:
            phase_verdict = "UNABLE_TO_EVALUATE"
        else:
            phase_verdict = "PARTIAL"

        if step_assessments:
            sorted_assessments = sorted(step_assessments, key=lambda item: item["step_index"])
            reasoning_lines = [
                (
                    f"Step {item['step_index']}: {item['verdict']}"
                    + (f" ({item['reasoning']})" if item.get("reasoning") else "")
                )
                for item in sorted_assessments[:6]
            ]
            phase_reasoning = " ".join(reasoning_lines)
        elif grounded_evidence:
            phase_reasoning = "Evidence was extracted but did not yield stable step verdicts."
        else:
            phase_reasoning = "No grounded high-signal evidence was extracted for this phase."

        if step_assessments:
            raw_phase_confidence = sum(
                float(item.get("confidence_score", 0.0)) for item in step_assessments
            ) / len(step_assessments)
        elif grounded_evidence:
            raw_phase_confidence = 0.35
        else:
            raw_phase_confidence = 0.0

        relevant_steps = sorted(
            {
                int(item.get("step_index"))
                for item in step_assessments
                if isinstance(item.get("step_index"), int)
            }
        )
        if not relevant_steps:
            relevant_steps = sorted(evidence_by_step.keys())

        dimension_assessments = [
            {
                "status": item.get("verdict", "unknown"),
                "reasoning": item.get("reasoning", ""),
            }
            for item in step_assessments
        ]

        calibrated_confidence = self._calibrate_phase_confidence(
            raw_confidence=raw_phase_confidence,
            verdict=phase_verdict,
            evidence_list=grounded_evidence,
            relevant_steps=relevant_steps,
            phase_step_indices=step_indices,
            dimension_assessments=dimension_assessments,
            reasoning=phase_reasoning,
            token_prediction_confidence=(
                step_token_prediction_confidence
                if step_token_prediction_confidence is not None
                else evidence_token_prediction_confidence
            ),
        )

        supporting_evidence = "\n".join(
            [
                f"Step {int(ev.step_index)} [{ev.source_field.value if hasattr(ev.source_field, 'value') else ev.source_field}]: {ev.highlighted_text}"
                for ev in grounded_evidence[:8]
            ]
        )
        aggregated_summary = (
            f"{phase_id}: pass={pass_count}, fail={fail_count}, partial={partial_count}, unknown={unknown_count}"
        )

        self._log_stage_timing(
            "phase_total",
            phase_started_at,
            criterion=criterion_name,
            phase_id=phase_id,
            step_count=len(step_indices),
            grounded_evidence=len(grounded_evidence),
        )

        return EvaluationResult(
            criterion_name=criterion_name,
            verdict=self._normalize_verdict(phase_verdict),
            reasoning=phase_reasoning,
            confidence_score=calibrated_confidence,
            relevant_steps=relevant_steps,
            aggregated_step_summary=aggregated_summary[:500],
            used_granularity=Granularity.PHASE_LEVEL,
            supporting_evidence=supporting_evidence,
            highlighted_evidence=grounded_evidence,
            dimension_assessments=dimension_assessments,
            llm_token_prediction_confidence=(
                step_token_prediction_confidence
                if step_token_prediction_confidence is not None
                else evidence_token_prediction_confidence
            ),
        )

    async def evaluate_criterion_unified(
        self,
        criterion_name: str,
        criterion_assertion: str,
        task_name: str,
        personas: List[str],
        models: List[str],
        all_steps: List[Dict[str, Any]],
        model_name: Optional[str] = None,
        criterion_description: Optional[str] = None,
        step_max_concurrency: Optional[int] = None,
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> EvaluationResult:
        if not all_steps:
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict="UNABLE_TO_EVALUATE",
                reasoning="No execution steps available for unified evaluation",
                confidence_score=0.0,
                aggregated_step_summary="No execution steps available",
                used_granularity=Granularity.PHASE_LEVEL,
            )

        try:
            criterion_started_at = time.perf_counter()
            logger.info(
                "[judge][criterion-start] task=%s criterion=%s model=%s total_steps=%d",
                task_name,
                criterion_name,
                model_name,
                len(all_steps),
            )

            criterion_intent_started_at = time.perf_counter()
            criterion_intent = await self._interpret_criterion_intent_async(
                task_name=task_name,
                criterion_name=criterion_name,
                criterion_assertion=criterion_assertion,
                personas=personas,
                model_name=model_name,
                llm_semaphore=llm_semaphore,
            )
            self._log_stage_timing(
                "criterion_intent",
                criterion_intent_started_at,
                task=task_name,
                criterion=criterion_name,
                model=model_name,
            )
            persona_task_alignment = ""
            global_behavior_summary = ""
            enable_evidence_expansion = bool(
                getattr(settings, "JUDGE_ENABLE_PHASE_EVIDENCE_EXPANSION", False)
            )

            if len(all_steps) <= SHORT_TRACE_FAST_PATH_MAX_STEPS:
                logger.info(
                    "[judge][fast-path] task=%s criterion=%s total_steps=%d threshold=%d",
                    task_name,
                    criterion_name,
                    len(all_steps),
                    SHORT_TRACE_FAST_PATH_MAX_STEPS,
                )
                fast_path_started_at = time.perf_counter()
                final = await self._evaluate_short_trace_fast_path_async(
                    criterion_name=criterion_name,
                    criterion_assertion=criterion_assertion,
                    criterion_description=criterion_description or "",
                    criterion_intent=criterion_intent,
                    task_name=task_name,
                    personas=personas,
                    models=models,
                    all_steps=all_steps,
                    model_name=model_name,
                    enable_evidence_expansion=enable_evidence_expansion,
                    llm_semaphore=llm_semaphore,
                )
                self._log_stage_timing(
                    "short_trace_fast_path",
                    fast_path_started_at,
                    task=task_name,
                    criterion=criterion_name,
                    total_steps=len(all_steps),
                )
                logger.info(
                    "[judge][criterion-end] task=%s criterion=%s final_verdict=%s final_confidence=%.2f",
                    task_name,
                    criterion_name,
                    final.verdict,
                    float(final.confidence_score or 0.0),
                )
                self._log_stage_timing(
                    "criterion_total",
                    criterion_started_at,
                    task=task_name,
                    criterion=criterion_name,
                    verdict=final.verdict,
                )
                return final

            phase_segmentation_started_at = time.perf_counter()
            segmentation = await self._segment_phases_by_dimensions_async(
                criterion_name=criterion_name,
                criterion_assertion=criterion_assertion,
                task_name=task_name,
                criterion_intent=criterion_intent,
                all_steps=all_steps,
                model_name=model_name,
                llm_semaphore=llm_semaphore,
            )
            self._log_stage_timing(
                "phase_segmentation",
                phase_segmentation_started_at,
                task=task_name,
                criterion=criterion_name,
                total_steps=len(all_steps),
            )
            phases = segmentation.get("phases", [])
            relevant_ids = set(segmentation.get("relevant_phase_ids", []))
            target_phases = [phase for phase in phases if str(phase.get("phase_id")) in relevant_ids]
            if not target_phases:
                target_phases = phases
            logger.info(
                "[judge][phase-selection] criterion=%s total_phases=%d selected_phase_ids=%s target_phases=%d",
                criterion_name,
                len(phases) if isinstance(phases, list) else 0,
                sorted(str(pid) for pid in relevant_ids),
                len(target_phases),
            )

            configured_step_limit = (
                int(step_max_concurrency)
                if step_max_concurrency is not None
                else int(getattr(settings, "JUDGE_EVALUATION_STEP_MAX_CONCURRENCY", 8) or 8)
            )
            semaphore = asyncio.Semaphore(max(1, configured_step_limit))
            logger.info(
                "[judge][phase-eval] criterion=%s step_max_concurrency=%d",
                criterion_name,
                max(1, configured_step_limit),
            )

            async def _run(phase: Dict[str, Any]) -> EvaluationResult:
                async with semaphore:
                    phase_id = str(phase.get("phase_id", "unknown"))
                    step_indices = [
                        i for i in phase.get("step_indices", [])
                        if isinstance(i, int)
                    ] if isinstance(phase, dict) else []
                    logger.info(
                        "[judge][phase-start] criterion=%s phase_id=%s step_count=%d step_indices=%s",
                        criterion_name,
                        phase_id,
                        len(step_indices),
                        step_indices,
                    )
                    phase_result = await self._evaluate_phase_with_dimensions_async(
                        criterion_name=criterion_name,
                        criterion_assertion=criterion_assertion,
                        criterion_intent=criterion_intent,
                        persona_task_alignment=persona_task_alignment,
                        global_behavior_summary=global_behavior_summary,
                        task_name=task_name,
                        personas=personas,
                        models=models,
                        phase=phase,
                        all_steps=all_steps,
                        model_name=model_name,
                        enable_evidence_expansion=enable_evidence_expansion,
                        llm_semaphore=llm_semaphore,
                    )
                    logger.info(
                        "[judge][phase-end] criterion=%s phase_id=%s verdict=%s confidence=%.2f evidence=%d",
                        criterion_name,
                        phase_id,
                        phase_result.verdict,
                        float(phase_result.confidence_score or 0.0),
                        len(phase_result.highlighted_evidence or []),
                    )
                    return phase_result

            phase_eval_started_at = time.perf_counter()
            phase_results = await asyncio.gather(*[_run(p) for p in target_phases])
            self._log_stage_timing(
                "all_phase_evaluations",
                phase_eval_started_at,
                task=task_name,
                criterion=criterion_name,
                phase_count=len(target_phases),
            )
            phase_results = [r for r in phase_results if isinstance(r, EvaluationResult)]
            if not phase_results:
                return EvaluationResult(
                    criterion_name=criterion_name,
                    verdict="UNABLE_TO_EVALUATE",
                    reasoning="No phase evaluation results were produced",
                    confidence_score=0.0,
                    aggregated_step_summary="Phase evaluation produced no results",
                    used_granularity=Granularity.PHASE_LEVEL,
                )

            overall_synthesis_started_at = time.perf_counter()
            final = await self._synthesize_overall_from_phase_results_async(
                criterion_name=criterion_name,
                criterion_assertion=criterion_assertion,
                criterion_description=criterion_description or "",
                task_name=task_name,
                personas=personas,
                models=models,
                criterion_intent=criterion_intent,
                persona_task_alignment=persona_task_alignment,
                global_behavior_summary=global_behavior_summary,
                phase_results=phase_results,
                target_phases=target_phases,
                model_name=model_name,
                all_steps=all_steps,
                llm_semaphore=llm_semaphore,
            )
            self._log_stage_timing(
                "overall_synthesis",
                overall_synthesis_started_at,
                task=task_name,
                criterion=criterion_name,
                phase_count=len(phase_results),
            )

            if final.verdict == "UNABLE_TO_EVALUATE" and len(phase_results) > 1:
                final = self._simple_merge_results(phase_results, criterion_name, Granularity.PHASE_LEVEL)
            elif final.verdict == "UNABLE_TO_EVALUATE" and len(phase_results) == 1:
                final = phase_results[0]

            final.aggregated_step_summary = (
                f"Criterion-specific phase evaluation. Relevant phases: {list(relevant_ids)}. "
                f"Segmentation reasoning: {segmentation.get('segmentation_reasoning', '')}"
            )[:500]
            final.used_granularity = Granularity.PHASE_LEVEL
            final = final.model_copy(update={"verdict": self._normalize_binary_verdict(final.verdict)})
            logger.info(
                "[judge][criterion-end] task=%s criterion=%s final_verdict=%s final_confidence=%.2f",
                task_name,
                criterion_name,
                final.verdict,
                float(final.confidence_score or 0.0),
            )
            self._log_stage_timing(
                "criterion_total",
                criterion_started_at,
                task=task_name,
                criterion=criterion_name,
                verdict=final.verdict,
            )
            return final
        except Exception as exc:
            logger.error("Unified criterion evaluation failed for '%s': %s", criterion_name, exc)
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict="UNABLE_TO_EVALUATE",
                reasoning=f"Unified evaluation failed: {str(exc)}",
                confidence_score=0.0,
                aggregated_step_summary=f"Unified evaluation failed: {str(exc)}",
                used_granularity=Granularity.PHASE_LEVEL,
            )

    async def evaluate_criterion(
        self,
        criterion_name: str,
        criterion_assertion: str,
        aggregated_steps: AggregatedSteps,
        task_name: str,
        personas: List[str],
        models: List[str],
        all_steps: Optional[List[Dict[str, Any]]] = None,
        model_name: Optional[str] = None,
        criterion_description: Optional[str] = None,
        step_max_concurrency: Optional[int] = None,
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> EvaluationResult:
        del aggregated_steps
        return await self.evaluate_criterion_unified(
            criterion_name=criterion_name,
            criterion_assertion=criterion_assertion,
            task_name=task_name,
            personas=personas,
            models=models,
            all_steps=all_steps or [],
            model_name=model_name,
            criterion_description=criterion_description,
            step_max_concurrency=step_max_concurrency,
            llm_semaphore=llm_semaphore,
        )

    def _normalize_text_for_match(self, value: Any) -> str:
        if value is None:
            return ""
        return " ".join(str(value).lower().split())

    def _extract_field_candidates(self, step_obj: Dict[str, Any], source_field: str) -> List[str]:
        normalized = (source_field or "").lower().strip()
        values: List[Any] = []

        if normalized == "evaluation":
            values.extend([step_obj.get("evaluation_previous_goal"), step_obj.get("evaluation")])
        elif normalized == "memory":
            values.append(step_obj.get("memory"))
        elif normalized in {"thinking process", "thinking_process", "thinking"}:
            values.extend([step_obj.get("thinking_process"), step_obj.get("thinking")])
        elif normalized in {"next goal", "next_goal"}:
            values.append(step_obj.get("next_goal"))
        elif normalized == "action":
            values.append(step_obj.get("action"))
        else:
            values.extend(step_obj.values())

        candidates: List[str] = []
        for item in values:
            if item is None:
                continue
            if isinstance(item, str):
                candidates.append(item)
            else:
                try:
                    candidates.append(json.dumps(item, ensure_ascii=False))
                except Exception:
                    candidates.append(str(item))
        return candidates

    def _find_exact_original_snippet(self, candidate: str, requested_text: str) -> Optional[str]:
        if not candidate or not requested_text:
            return None

        exact_pos = candidate.find(requested_text)
        if exact_pos != -1:
            return candidate[exact_pos:exact_pos + len(requested_text)]

        lower_candidate = candidate.lower()
        lower_requested = requested_text.lower()
        ci_pos = lower_candidate.find(lower_requested)
        if ci_pos != -1:
            return candidate[ci_pos:ci_pos + len(requested_text)]

        return None

    def _locate_unique_evidence_match(
        self,
        requested_text: str,
        source_field: str,
        all_steps: List[Dict[str, Any]],
    ) -> Optional[tuple[int, str]]:
        if not requested_text:
            return None

        matches: List[tuple[int, str]] = []
        for step_index, step_obj in enumerate(all_steps):
            candidates = self._extract_field_candidates(step_obj, source_field)
            for candidate in candidates:
                matched = self._find_exact_original_snippet(candidate, requested_text)
                if matched:
                    matches.append((step_index, matched))

        if len(matches) == 1:
            return matches[0]
        return None

    def _ground_evidence_to_original_text(
        self,
        evidence: EvidenceCitation,
        all_steps: List[Dict[str, Any]],
        criterion_name: str,
    ) -> Optional[EvidenceCitation]:
        requested = (evidence.highlighted_text or "").strip()
        if not requested:
            return None

        source_field = evidence.source_field.value if hasattr(evidence.source_field, "value") else str(evidence.source_field)
        declared_step_index = int(evidence.step_index)

        candidate_step_indices: List[int] = []
        if 0 <= declared_step_index < len(all_steps):
            candidate_step_indices.append(declared_step_index)

        if 1 <= declared_step_index <= len(all_steps):
            one_based_zero_index = declared_step_index - 1
            if one_based_zero_index not in candidate_step_indices:
                candidate_step_indices.append(one_based_zero_index)

        for candidate_step_index in candidate_step_indices:
            candidates = self._extract_field_candidates(all_steps[candidate_step_index], source_field)
            for candidate in candidates:
                matched = self._find_exact_original_snippet(candidate, requested)
                if matched:
                    return evidence.model_copy(update={"step_index": candidate_step_index, "highlighted_text": matched})

        unique_match = self._locate_unique_evidence_match(requested, source_field, all_steps)
        if unique_match is None:
            unique_match = self._locate_unique_evidence_match(requested, "", all_steps)
        if unique_match is None:
            return None

        matched_step_index, matched_text = unique_match
        return evidence.model_copy(update={"step_index": matched_step_index, "highlighted_text": matched_text})

    def _filter_grounded_evidence(
        self,
        evidence_list: List[EvidenceCitation],
        all_steps: List[Dict[str, Any]],
        criterion_name: str,
    ) -> List[EvidenceCitation]:
        grounded: List[EvidenceCitation] = []
        seen_keys = set()

        for evidence in evidence_list:
            try:
                grounded_item = self._ground_evidence_to_original_text(
                    evidence,
                    all_steps,
                    criterion_name=criterion_name,
                )
                if grounded_item is None:
                    continue

                text = (grounded_item.highlighted_text or "").strip()
                if not text:
                    continue

                source_field = grounded_item.source_field.value if hasattr(grounded_item.source_field, "value") else str(grounded_item.source_field)
                key = (int(grounded_item.step_index), source_field, self._normalize_text_for_match(text))
                if key in seen_keys:
                    continue

                seen_keys.add(key)
                grounded.append(grounded_item)
            except Exception as exc:
                logger.debug("Evidence grounding failed for one item: %s", exc)

        return grounded

    def _create_default_evaluation_result(
        self,
        criterion_name: str,
        aggregated_steps: AggregatedSteps,
    ) -> EvaluationResult:
        return EvaluationResult(
            criterion_name=criterion_name,
            verdict="UNABLE_TO_EVALUATE",
            reasoning="Evaluation parsing failed",
            confidence_score=0.0,
            aggregated_step_summary=aggregated_steps.aggregated_content[:200],
            used_granularity=aggregated_steps.granularity,
        )

    def _parse_highlighted_evidence_items(self, raw_items: Any) -> List[EvidenceCitation]:
        highlighted_evidence: List[EvidenceCitation] = []
        if not isinstance(raw_items, list):
            return highlighted_evidence

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                evidence_item = dict(item)
                if isinstance(evidence_item.get("source_field"), str):
                    evidence_item["source_field"] = self._normalize_source_field(evidence_item["source_field"])
                if isinstance(evidence_item.get("verdict"), str):
                    evidence_item["verdict"] = evidence_item["verdict"].lower()
                highlighted_evidence.append(EvidenceCitation(**evidence_item))
            except Exception as exc:
                logger.debug("Skip malformed evidence item: %s", exc)

        return highlighted_evidence

    def _is_high_signal_evidence(self, evidence: EvidenceCitation) -> bool:
        text = (evidence.highlighted_text or "").strip()
        reasoning = (evidence.reasoning or "").strip().lower()
        if len(text) < 8:
            return False

        generic_markers = [
            "next step",
            "continue",
            "proceed",
            "let's",
            "i will",
            "done",
            "completed",
            "ok",
        ]
        lowered_text = text.lower()
        if any(marker in lowered_text for marker in generic_markers) and len(text) < 40:
            return False

        if reasoning:
            strong_markers = [
                "criterion",
                "tradeoff",
                "constraint",
                "risk",
                "failure",
                "success",
                "evidence",
                "supports",
                "contradicts",
            ]
            if any(marker in reasoning for marker in strong_markers):
                return True

        return len(text) >= 15

    def _keep_high_signal_evidence(self, evidence_list: List[EvidenceCitation]) -> List[EvidenceCitation]:
        if not evidence_list:
            return []
        high_signal = [item for item in evidence_list if self._is_high_signal_evidence(item)]
        return high_signal or evidence_list

    async def _expand_phase_evidence_if_needed_async(
        self,
        base_evidence: List[EvidenceCitation],
        criterion_name: str,
        criterion_assertion: str,
        task_name: str,
        phase_id: str,
        phase_summary: str,
        step_indices: List[int],
        all_steps: List[Dict[str, Any]],
        model_name: Optional[str],
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> List[EvidenceCitation]:
        del (
            criterion_name,
            criterion_assertion,
            task_name,
            phase_id,
            phase_summary,
            all_steps,
            model_name,
            llm_semaphore,
        )

        current_evidence = list(base_evidence or [])
        curated_current = self._curate_story_evidence(
            self._keep_high_signal_evidence(current_evidence),
            step_indices,
        )
        return curated_current

    def _parse_evaluation_response(
        self,
        response_text: str,
        criterion_name: str,
        aggregated_steps: AggregatedSteps,
        all_steps: Optional[List[Dict[str, Any]]] = None,
    ) -> EvaluationResult:
        response_data = self._extract_json_object(response_text)
        if not response_data:
            logger.warning("Could not parse JSON in evaluation response")
            return self._create_default_evaluation_result(criterion_name, aggregated_steps)

        highlighted_evidence: List[EvidenceCitation] = self._parse_highlighted_evidence_items(
            response_data.get("highlighted_evidence", [])
        )

        if all_steps and highlighted_evidence:
            highlighted_evidence = self._filter_grounded_evidence(
                evidence_list=highlighted_evidence,
                all_steps=all_steps,
                criterion_name=criterion_name,
            )
            highlighted_evidence = self._keep_high_signal_evidence(highlighted_evidence)

        phase_scope: List[int] = []
        if isinstance(aggregated_steps.step_mapping, dict):
            for value in aggregated_steps.step_mapping.values():
                if isinstance(value, list):
                    phase_scope.extend([idx for idx in value if isinstance(idx, int)])
        phase_scope = sorted(set(phase_scope))
        highlighted_evidence = self._curate_story_evidence(highlighted_evidence, phase_scope)

        dimension_assessments = response_data.get("dimension_assessments", [])
        if not isinstance(dimension_assessments, list):
            dimension_assessments = []

        raw_relevant_steps = response_data.get("relevant_steps", [])
        normalized_relevant_steps: List[int] = []
        if isinstance(raw_relevant_steps, list):
            for item in raw_relevant_steps:
                if isinstance(item, int):
                    normalized_relevant_steps.append(item)
                elif isinstance(item, str) and item.isdigit():
                    normalized_relevant_steps.append(int(item))

        evidence_step_indices = sorted(
            {
                int(item.step_index)
                for item in highlighted_evidence
                if isinstance(item.step_index, int)
            }
        )
        if evidence_step_indices:
            relevant_steps = [
                step_idx
                for step_idx in normalized_relevant_steps
                if step_idx in evidence_step_indices
            ]
            if not relevant_steps:
                relevant_steps = evidence_step_indices
        else:
            relevant_steps = []

        return EvaluationResult(
            criterion_name=criterion_name,
            verdict=self._normalize_verdict(response_data.get("verdict", "UNABLE_TO_EVALUATE")),
            reasoning=response_data.get("reasoning", ""),
            confidence_score=float(response_data.get("confidence_score", 0.5)),
            relevant_steps=relevant_steps,
            aggregated_step_summary=aggregated_steps.aggregated_content[:500],
            used_granularity=aggregated_steps.granularity,
            supporting_evidence=response_data.get("supporting_evidence", ""),
            highlighted_evidence=highlighted_evidence,
            dimension_assessments=dimension_assessments,
        )

    async def _synthesize_overall_from_phase_results_async(
        self,
        criterion_name: str,
        criterion_assertion: str,
        criterion_description: str,
        task_name: str,
        personas: List[str],
        models: List[str],
        criterion_intent: str,
        persona_task_alignment: str,
        global_behavior_summary: str,
        phase_results: List[EvaluationResult],
        target_phases: List[Dict[str, Any]],
        model_name: Optional[str],
        all_steps: List[Dict[str, Any]],
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> EvaluationResult:
        del criterion_description, models, persona_task_alignment, global_behavior_summary, criterion_intent

        if not phase_results:
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict="UNABLE_TO_EVALUATE",
                reasoning="No phase results available for criterion synthesis",
                confidence_score=0.0,
                aggregated_step_summary="No phase results available for synthesis",
                used_granularity=Granularity.PHASE_LEVEL,
            )

        phase_chunks: List[str] = []
        for idx, result in enumerate(phase_results):
            phase_meta = target_phases[idx] if idx < len(target_phases) else {}
            phase_id = str(phase_meta.get("phase_id", f"phase_{idx}"))
            step_indices = phase_meta.get("step_indices", [])
            phase_summary = str(phase_meta.get("phase_summary", ""))
            phase_evidence = result.highlighted_evidence or []
            pass_evidence = 0
            partial_evidence = 0
            fail_evidence = 0
            for evidence in phase_evidence:
                evidence_verdict = evidence.verdict.value if hasattr(evidence.verdict, "value") else evidence.verdict
                normalized_evidence_verdict = self._normalize_step_verdict(evidence_verdict)
                if normalized_evidence_verdict == "pass":
                    pass_evidence += 1
                elif normalized_evidence_verdict == "partial":
                    partial_evidence += 1
                elif normalized_evidence_verdict == "fail":
                    fail_evidence += 1
            unknown_evidence = max(0, len(phase_evidence) - pass_evidence - partial_evidence - fail_evidence)
            phase_chunks.append(
                (
                    f"Phase: {phase_id}\n"
                    f"  Steps: {step_indices}\n"
                    f"  Phase Summary: {phase_summary}\n"
                    f"  Evidence Verdict Distribution: pass={pass_evidence}, partial={partial_evidence}, fail={fail_evidence}, unknown={unknown_evidence}\n"
                    f"  Evidence Count: {len(phase_evidence)}\n"
                    f"  Phase Notes: {result.reasoning}\n"
                )
            )
        phase_evaluations_summary = "\n".join(phase_chunks)

        aggregated_evidence: List[EvidenceCitation] = []
        for result in phase_results:
            if result.highlighted_evidence:
                aggregated_evidence.extend(result.highlighted_evidence)
        if aggregated_evidence:
            aggregated_evidence = self._filter_grounded_evidence(
                evidence_list=aggregated_evidence,
                all_steps=all_steps,
                criterion_name=criterion_name,
            )

        aggregated_evidence_payload: List[Dict[str, Any]] = []
        for evidence in aggregated_evidence:
            source_field = evidence.source_field.value if hasattr(evidence.source_field, "value") else str(evidence.source_field)
            verdict = evidence.verdict.value if hasattr(evidence.verdict, "value") else evidence.verdict
            aggregated_evidence_payload.append(
                {
                    "step_index": int(evidence.step_index),
                    "source_field": source_field,
                    "highlighted_text": evidence.highlighted_text,
                    "reasoning": evidence.reasoning or "",
                    "verdict": str(verdict or ""),
                }
            )

        try:
            llm = self.llm_factory.get_langchain_llm(model_name)
            chain = self.phase_overall_synthesis_template | llm
            invoke_dict = {
                "task_name": self._prompt_text(task_name),
                "criterion_name": self._prompt_text(criterion_name),
                "criterion_assertion": self._prompt_text(criterion_assertion),
                "phase_evaluations_summary": self._prompt_text(phase_evaluations_summary),
                "aggregated_evidence_json": json.dumps(aggregated_evidence_payload, ensure_ascii=False, indent=2),
            }
            response = await self._invoke_chain_async(chain, invoke_dict, llm_semaphore)
            response_text = self._response_to_text(response)
            self._log_llm_response_details(
                stage="phase_overall_synthesis",
                response_text=response_text,
                response_obj=response,
                criterion_name=criterion_name,
                model_name=model_name,
            )
            token_prediction_confidence = self._extract_token_prediction_confidence(response)
            response_data = self._extract_json_object(response_text)
            if not response_data:
                return self._simple_merge_results(phase_results, criterion_name, Granularity.PHASE_LEVEL)

            relevant_steps = sorted(
                {
                    step
                    for result in phase_results
                    for step in (result.relevant_steps or [])
                    if isinstance(step, int)
                }
            )
            if not relevant_steps:
                relevant_steps = sorted(
                    {
                        int(ev.step_index)
                        for ev in aggregated_evidence
                        if isinstance(ev.step_index, int)
                    }
                )

            aggregated_evidence = self._curate_story_evidence(aggregated_evidence, relevant_steps)

            reasoning_text = str(response_data.get("reasoning", ""))
            raw_confidence = float(response_data.get("confidence_score", 0.5))
            normalized_verdict = self._normalize_binary_verdict(response_data.get("verdict", "FAIL"))
            calibrated_confidence = self._calibrate_criterion_confidence(
                raw_confidence=raw_confidence,
                verdict=normalized_verdict,
                aggregated_evidence=aggregated_evidence,
                phase_results=phase_results,
                all_steps=all_steps,
                reasoning=reasoning_text,
                token_prediction_confidence=token_prediction_confidence,
            )

            return EvaluationResult(
                criterion_name=criterion_name,
                verdict=normalized_verdict,
                reasoning=reasoning_text,
                confidence_score=calibrated_confidence,
                relevant_steps=relevant_steps,
                aggregated_step_summary=str(response_data.get("aggregation_summary", ""))[:500],
                used_granularity=Granularity.PHASE_LEVEL,
                supporting_evidence=str(response_data.get("supporting_evidence", "")),
                highlighted_evidence=aggregated_evidence,
                llm_token_prediction_confidence=token_prediction_confidence,
            )
        except Exception as exc:
            logger.warning("Phase overall synthesis failed: %s", exc)
            return self._simple_merge_results(phase_results, criterion_name, Granularity.PHASE_LEVEL)

    def _simple_merge_results(
        self,
        results: List[EvaluationResult],
        criterion_name: str,
        granularity: Granularity,
    ) -> EvaluationResult:
        verdicts = [r.verdict for r in results]
        passed = verdicts.count("PASS")
        failed = verdicts.count("FAIL")
        partial = verdicts.count("PARTIAL")
        total = len(results)

        if failed > 0:
            final_verdict = "FAIL"
        elif partial > 0:
            final_verdict = "PARTIAL"
        elif passed == total:
            final_verdict = "PASS"
        else:
            final_verdict = "UNABLE_TO_EVALUATE"

        avg_confidence = sum(r.confidence_score for r in results) / total if total else 0.0
        reasoning = f"Merged {total} evaluations: {passed} passed, {failed} failed, {partial} partial."

        aggregated_evidence: List[EvidenceCitation] = []
        for result in results:
            if result.highlighted_evidence:
                aggregated_evidence.extend(result.highlighted_evidence)

        return EvaluationResult(
            criterion_name=criterion_name,
            verdict=final_verdict,
            reasoning=reasoning,
            confidence_score=avg_confidence,
            aggregated_step_summary=f"Merged {total} phase evaluations",
            used_granularity=granularity,
            highlighted_evidence=aggregated_evidence,
        )

    def _create_overall_assessment(self, evaluation_results: List[EvaluationResult]) -> OverallAssessment:
        total = len(evaluation_results)
        passed = sum(1 for r in evaluation_results if r.verdict == "PASS")
        failed = sum(1 for r in evaluation_results if r.verdict == "FAIL")
        partial = sum(1 for r in evaluation_results if r.verdict == "PARTIAL")
        unable = sum(1 for r in evaluation_results if r.verdict == "UNABLE_TO_EVALUATE")
        avg_confidence = sum(r.confidence_score for r in evaluation_results) / total if total else 0.0
        pass_rate = (passed / total * 100) if total else 0.0
        summary = (
            f"Evaluation completed with {passed} passed, {failed} failed, {partial} partial, "
            f"and {unable} unable to evaluate out of {total} criteria "
            f"(pass rate: {pass_rate:.1f}%). Average confidence: {avg_confidence:.2f}"
        )
        return OverallAssessment(
            total_criteria=total,
            passed_count=passed,
            failed_count=failed,
            partial_count=partial,
            unable_to_evaluate_count=unable,
            average_confidence=avg_confidence,
            overall_summary=summary,
        )

    async def evaluate_batch(
        self,
        run_id: str,
        criteria: List[Dict[str, str]],
        task: BrowserAgentTask,
        all_steps: List[Dict[str, Any]],
        personas: List[str],
        models: List[str],
        decomposer_model: str = "deepseek-chat",
        evaluator_model: str = "deepseek-chat",
        cache_decomposition: bool = True,
    ) -> JudgeEvaluationReport:
        del decomposer_model, cache_decomposition
        logger.info(
            "Starting criterion-segmentation batch evaluation for run: %s with %d criteria",
            run_id,
            len(criteria),
        )

        criterion_tasks = [
            self.evaluate_criterion_unified(
                criterion_name=criterion.get("name", "unknown"),
                criterion_assertion=criterion.get("assertion", ""),
                task_name=task.name,
                personas=personas,
                models=models,
                all_steps=all_steps,
                model_name=evaluator_model,
                criterion_description=criterion.get("description", ""),
            )
            for criterion in criteria
        ]
        evaluation_results = await asyncio.gather(*criterion_tasks)
        overall_assessment = self._create_overall_assessment(evaluation_results)

        subtask_clusters = [
            StepCluster(
                cluster_id="phase_0",
                semantic_label="Unified Execution",
                step_indices=list(range(len(all_steps))),
                cluster_summary="Criterion-based segmentation is executed independently per criterion.",
                key_decisions=[],
                dependencies=[],
            )
        ]

        task_decomposition = TaskDecomposition(
            task_name=task.name,
            subtask_clusters=subtask_clusters,
            total_steps=len(all_steps),
        )

        granularity_analysis = [
            GranularityRequirement(
                criterion_name=criterion.get("name", "unknown"),
                required_granularity=Granularity.PHASE_LEVEL,
                rationale="Unified architecture uses single dimension-driven phase evaluation path.",
                target_cluster_indices=[],
                target_step_indices=[],
            )
            for criterion in criteria
        ]

        report = JudgeEvaluationReport(
            run_id=run_id,
            evaluation_timestamp=datetime.utcnow(),
            task_decomposition=task_decomposition,
            evaluation_results=evaluation_results,
            granularity_analysis=granularity_analysis,
            overall_assessment=overall_assessment,
            metadata={
                "evaluator_model": evaluator_model,
                "total_steps": len(all_steps),
                "architecture": "unified",
                "pipeline_style": "criterion-phase-criterion",
                "global_behavior_summary": "",
            },
        )
        logger.info("Criterion-segmentation batch evaluation complete for run: %s", run_id)
        return report
