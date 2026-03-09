"""
Unified service for evaluating agent behavior against criteria using an LLM judge.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import settings
from ..schemas.browser_agent import BrowserAgentTask
from ..schemas.judge import (
    AggregatedSteps,
    EvaluationResult,
    EvidenceCitation,
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


class JudgeEvaluatorService:
    """Unified evaluator service (dimension interpretation -> phase segmentation -> phase evaluation)."""

    def __init__(
        self,
        llm_factory: ChatLLMFactory,
        decomposer: Any = None,
        granularity_analyzer: Any = None,
        step_aggregator: Any = None,
    ):
        self.llm_factory = llm_factory
        self.decomposer = decomposer
        self.granularity_analyzer = granularity_analyzer
        self.step_aggregator = step_aggregator
        self._setup_templates()

    def _setup_templates(self) -> None:
        self.global_behavior_overview_template = EvaluationPrompts.get_global_behavior_overview_prompt()
        self.criterion_interpretation_template = EvaluationPrompts.get_criterion_interpretation_prompt()
        self.phase_segmentation_template = EvaluationPrompts.get_phase_segmentation_prompt()
        self.unified_phase_evaluation_template = EvaluationPrompts.get_unified_phase_evaluation_prompt()
        self.phase_evidence_expansion_template = EvaluationPrompts.get_phase_evidence_expansion_prompt()
        self.phase_overall_synthesis_template = EvaluationPrompts.get_phase_overall_synthesis_prompt()
        self.evidence_reextract_template = EvaluationPrompts.get_evidence_reextract_prompt()
        self.merge_template = EvaluationPrompts.get_merge_results_prompt()

    def _extract_json_object(self, response_text: str) -> Optional[Dict[str, Any]]:
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
        field_lower = (field_name or "").lower().strip()
        mapping = {
            "evaluation": "Evaluation",
            "memory": "Memory",
            "thinking_process": "Thinking Process",
            "thinking": "Thinking Process",
            "next_goal": "Next Goal",
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
        max_items: int = 9,
    ) -> List[EvidenceCitation]:
        if not evidence_list:
            return []

        ranked = sorted(evidence_list, key=self._score_evidence_item, reverse=True)
        selected: List[EvidenceCitation] = []
        per_step_count: Dict[int, int] = {}

        for item in ranked:
            step_idx = int(item.step_index)
            if per_step_count.get(step_idx, 0) >= 2:
                continue

            if step_idx not in per_step_count:
                selected.append(item)
                per_step_count[step_idx] = 1
            if len(selected) >= max_items:
                break

        if len(selected) < max_items:
            for item in ranked:
                if item in selected:
                    continue
                step_idx = int(item.step_index)
                if per_step_count.get(step_idx, 0) >= 3:
                    continue
                selected.append(item)
                per_step_count[step_idx] = per_step_count.get(step_idx, 0) + 1
                if len(selected) >= max_items:
                    break

        scope = {idx for idx in step_indices if isinstance(idx, int)}
        if scope:
            selected = [item for item in selected if int(item.step_index) in scope] or selected
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
            thinking = str(step.get("thinking_process") or step.get("thinking") or "")[:300]
            memory = str(step.get("memory") or "")[:220]
            evaluation = str(step.get("evaluation_previous_goal") or "")[:220]
            next_goal = str(step.get("next_goal") or "")[:220]
            try:
                action_text = json.dumps(step.get("action"), ensure_ascii=False)
            except Exception:
                action_text = str(step.get("action"))
            action_text = action_text[:300]

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

    async def _build_global_behavior_overview_async(
        self,
        task_name: str,
        personas: List[str],
        models: List[str],
        all_steps: List[Dict[str, Any]],
        model_name: Optional[str],
    ) -> Dict[str, Any]:
        llm = self.llm_factory.get_langchain_llm(model_name)
        chain = self.global_behavior_overview_template | llm
        invoke_dict = {
            "task_name": task_name,
            "personas": ", ".join(personas) if personas else "None",
            "models": ", ".join(models) if models else "None",
            "steps_text": self._format_steps_for_unified_segmentation(all_steps),
        }

        response = await asyncio.to_thread(chain.invoke, invoke_dict)
        response_text = response.content if hasattr(response, "content") else str(response)
        token_prediction_confidence = self._extract_token_prediction_confidence(response)
        response_data = self._extract_json_object(response_text) or {}

        phases = self._sanitize_phase_output(
            raw_phases=response_data.get("phases", []),
            all_steps=all_steps,
            fallback_summary=f"Complete execution with {len(all_steps)} steps",
        )
        key_phase_ids = response_data.get("key_phase_ids", [])
        if not isinstance(key_phase_ids, list):
            key_phase_ids = []
        key_phase_ids = [str(pid) for pid in key_phase_ids if isinstance(pid, (str, int))]
        if not key_phase_ids:
            key_phase_ids = [
                str(phase.get("phase_id"))
                for phase in phases
                if str(phase.get("criticality", "")).lower() == "high"
            ]
        if not key_phase_ids:
            key_phase_ids = [str(phase.get("phase_id")) for phase in phases]

        return {
            "overall_behavior_summary": str(response_data.get("overall_behavior_summary", "")),
            "phases": phases,
            "key_phase_ids": key_phase_ids,
            "global_reasoning": str(response_data.get("global_reasoning", "")),
        }

    async def build_global_behavior_overview(
        self,
        task_name: str,
        personas: List[str],
        models: List[str],
        all_steps: List[Dict[str, Any]],
        model_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not all_steps:
            return {
                "overall_behavior_summary": "",
                "phases": [
                    {
                        "phase_id": "phase_0",
                        "semantic_label": "Complete Execution",
                        "step_indices": [],
                        "phase_summary": "No execution steps available",
                        "relevant_to_evaluation": True,
                        "criticality": "high",
                        "why_key": "Fallback due to empty execution steps.",
                    }
                ],
                "key_phase_ids": ["phase_0"],
                "global_reasoning": "Fallback global overview due to empty execution steps.",
            }

        try:
            return await self._build_global_behavior_overview_async(
                task_name=task_name,
                personas=personas,
                models=models,
                all_steps=all_steps,
                model_name=model_name,
            )
        except Exception as exc:
            logger.warning("Global behavior overview failed, using fallback summary: %s", exc)
            return {
                "overall_behavior_summary": "",
                "phases": [
                    {
                        "phase_id": "phase_0",
                        "semantic_label": "Complete Execution",
                        "step_indices": list(range(len(all_steps))),
                        "phase_summary": f"Complete execution with {len(all_steps)} steps",
                        "relevant_to_evaluation": True,
                        "criticality": "high",
                        "why_key": "Fallback due to global overview failure.",
                    }
                ],
                "key_phase_ids": ["phase_0"],
                "global_reasoning": "Fallback global overview due to upstream error.",
            }

    def _build_phase_steps_context(self, all_steps: List[Dict[str, Any]], step_indices: List[int]) -> str:
        context_parts: List[str] = []
        valid_indices = sorted({i for i in step_indices if isinstance(i, int) and 0 <= i < len(all_steps)})
        for step_idx in valid_indices:
            step = all_steps[step_idx]
            thinking = step.get("thinking_process") or step.get("thinking") or "N/A"
            memory = step.get("memory", "N/A")
            eval_prev = step.get("evaluation_previous_goal", "N/A")
            next_goal = step.get("next_goal", "N/A")
            try:
                action_text = json.dumps(step.get("action"), ensure_ascii=False)
            except Exception:
                action_text = str(step.get("action"))

            context_parts.append(
                f"Step Index: {step_idx}\n"
                f"Thinking Process: {thinking}\n"
                f"Memory: {memory}\n"
                f"Evaluation of Previous Goal: {eval_prev}\n"
                f"Action: {action_text}\n"
                f"Next Goal: {next_goal}\n"
            )

        return "\n".join(context_parts)

    async def _interpret_criterion_dimensions_async(
        self,
        criterion_name: str,
        criterion_assertion: str,
        criterion_description: str,
        task_name: str,
        personas: List[str],
        models: List[str],
        global_overview: Dict[str, Any],
        model_name: Optional[str],
    ) -> Dict[str, Any]:
        llm = self.llm_factory.get_langchain_llm(model_name)
        chain = self.criterion_interpretation_template | llm
        invoke_dict = {
            "task_name": task_name,
            "criterion_name": criterion_name,
            "criterion_assertion": criterion_assertion,
            "criterion_description": criterion_description or "",
            "personas": ", ".join(personas) if personas else "None",
            "models": ", ".join(models) if models else "None",
            "global_behavior_summary": str(global_overview.get("overall_behavior_summary", "")),
            "global_key_phases": json.dumps(global_overview.get("phases", []), ensure_ascii=False, indent=2),
        }

        response = await asyncio.to_thread(chain.invoke, invoke_dict)
        response_text = response.content if hasattr(response, "content") else str(response)
        response_data = self._extract_json_object(response_text) or {}

        dimensions = response_data.get("evaluation_dimensions", [])
        if not isinstance(dimensions, list) or not dimensions:
            dimensions = [
                {
                    "dimension_name": "Criterion Alignment",
                    "description": criterion_assertion,
                    "why_relevant": "Directly derived from criterion assertion",
                }
            ]

        focus_points = response_data.get("focus_points", [])
        if not isinstance(focus_points, list):
            focus_points = []

        phase_selection_heuristics = response_data.get("phase_selection_heuristics", [])
        if not isinstance(phase_selection_heuristics, list):
            phase_selection_heuristics = []

        pass_signals = response_data.get("pass_signals", [])
        if not isinstance(pass_signals, list):
            pass_signals = []

        fail_signals = response_data.get("fail_signals", [])
        if not isinstance(fail_signals, list):
            fail_signals = []

        return {
            "criterion_intent": str(response_data.get("criterion_intent", criterion_assertion)),
            "persona_task_alignment": str(response_data.get("persona_task_alignment", "")),
            "evaluation_dimensions": dimensions,
            "focus_points": focus_points,
            "phase_selection_heuristics": phase_selection_heuristics,
            "pass_signals": pass_signals,
            "fail_signals": fail_signals,
        }

    async def _segment_phases_by_dimensions_async(
        self,
        criterion_name: str,
        criterion_assertion: str,
        task_name: str,
        criterion_intent: str,
        phase_selection_heuristics: List[str],
        global_overview: Dict[str, Any],
        evaluation_dimensions: List[Dict[str, Any]],
        all_steps: List[Dict[str, Any]],
        model_name: Optional[str],
    ) -> Dict[str, Any]:
        llm = self.llm_factory.get_langchain_llm(model_name)
        chain = self.phase_segmentation_template | llm
        invoke_dict = {
            "task_name": task_name,
            "criterion_name": criterion_name,
            "criterion_assertion": criterion_assertion,
            "criterion_intent": criterion_intent,
            "phase_selection_heuristics": json.dumps(phase_selection_heuristics, ensure_ascii=False),
            "global_phases_overview": json.dumps(global_overview.get("phases", []), ensure_ascii=False, indent=2),
            "evaluation_dimensions": json.dumps(evaluation_dimensions, ensure_ascii=False, indent=2),
            "steps_text": self._format_steps_for_unified_segmentation(all_steps),
        }

        response = await asyncio.to_thread(chain.invoke, invoke_dict)
        response_text = response.content if hasattr(response, "content") else str(response)
        response_data = self._extract_json_object(response_text) or {}

        raw_phases = response_data.get("phases", [])
        if (not isinstance(raw_phases, list) or not raw_phases) and isinstance(global_overview.get("phases"), list):
            raw_phases = global_overview.get("phases", [])

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
            key_phase_ids = global_overview.get("key_phase_ids", [])
            if isinstance(key_phase_ids, list):
                relevant_phase_ids = [str(pid) for pid in key_phase_ids if isinstance(pid, (str, int))]
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
        pass_signals: List[str],
        fail_signals: List[str],
        global_behavior_summary: str,
        task_name: str,
        personas: List[str],
        models: List[str],
        evaluation_dimensions: List[Dict[str, Any]],
        phase: Dict[str, Any],
        all_steps: List[Dict[str, Any]],
        model_name: Optional[str],
    ) -> EvaluationResult:
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

        llm = self.llm_factory.get_langchain_llm(model_name)
        chain = self.unified_phase_evaluation_template | llm
        invoke_dict = {
            "task_name": task_name,
            "criterion_name": criterion_name,
            "criterion_assertion": criterion_assertion,
            "criterion_intent": criterion_intent,
            "persona_task_alignment": persona_task_alignment,
            "pass_signals": json.dumps(pass_signals, ensure_ascii=False),
            "fail_signals": json.dumps(fail_signals, ensure_ascii=False),
            "global_behavior_summary": global_behavior_summary,
            "evaluation_dimensions": json.dumps(evaluation_dimensions, ensure_ascii=False, indent=2),
            "phase_id": phase_id,
            "phase_summary": phase_summary,
            "phase_steps_context": self._build_phase_steps_context(all_steps, step_indices),
            "personas": ", ".join(personas) if personas else "None",
            "models": ", ".join(models) if models else "None",
        }

        response = await asyncio.to_thread(chain.invoke, invoke_dict)
        response_text = response.content if hasattr(response, "content") else str(response)

        phase_agg = AggregatedSteps(
            granularity=Granularity.PHASE_LEVEL,
            aggregated_content=f"{phase_id}: {phase_summary}",
            step_mapping={phase_id: step_indices},
            summary_metadata={"phase_id": phase_id, "step_count": len(step_indices)},
        )
        result = self._parse_evaluation_response(
            response_text=response_text,
            criterion_name=criterion_name,
            aggregated_steps=phase_agg,
            all_steps=all_steps,
            model_name=model_name,
        )
        result.highlighted_evidence = await self._expand_phase_evidence_if_needed_async(
            base_evidence=result.highlighted_evidence or [],
            criterion_name=criterion_name,
            criterion_assertion=criterion_assertion,
            task_name=task_name,
            phase_id=phase_id,
            phase_summary=phase_summary,
            step_indices=step_indices,
            all_steps=all_steps,
            model_name=model_name,
        )
        dimension_assessments: List[Dict[str, Any]] = []
        if isinstance(result.model_extra, dict):
            raw_dimensions = result.model_extra.get("dimension_assessments", [])
            if isinstance(raw_dimensions, list):
                dimension_assessments = [item for item in raw_dimensions if isinstance(item, dict)]

        calibrated_confidence = self._calibrate_phase_confidence(
            raw_confidence=float(result.confidence_score or 0.0),
            verdict=result.verdict,
            evidence_list=result.highlighted_evidence or [],
            relevant_steps=[s for s in (result.relevant_steps or []) if isinstance(s, int)],
            phase_step_indices=step_indices,
            dimension_assessments=dimension_assessments,
            reasoning=result.reasoning,
            token_prediction_confidence=token_prediction_confidence,
        )

        update_payload: Dict[str, Any] = {
            "confidence_score": calibrated_confidence,
            "highlighted_evidence": self._curate_story_evidence(result.highlighted_evidence or [], step_indices),
        }
        if token_prediction_confidence is not None:
            update_payload["llm_token_prediction_confidence"] = token_prediction_confidence

        result = result.model_copy(update=update_payload)
        result.used_granularity = Granularity.PHASE_LEVEL
        return result

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
        global_overview: Optional[Dict[str, Any]] = None,
        step_max_concurrency: Optional[int] = None,
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
            if not global_overview:
                global_overview = await self._build_global_behavior_overview_async(
                    task_name=task_name,
                    personas=personas,
                    models=models,
                    all_steps=all_steps,
                    model_name=model_name,
                )

            interpreted = await self._interpret_criterion_dimensions_async(
                criterion_name=criterion_name,
                criterion_assertion=criterion_assertion,
                criterion_description=criterion_description or "",
                task_name=task_name,
                personas=personas,
                models=models,
                global_overview=global_overview,
                model_name=model_name,
            )
            dimensions = interpreted.get("evaluation_dimensions", [])
            criterion_intent = str(interpreted.get("criterion_intent", criterion_assertion))
            persona_task_alignment = str(interpreted.get("persona_task_alignment", ""))
            pass_signals = interpreted.get("pass_signals", [])
            fail_signals = interpreted.get("fail_signals", [])
            phase_selection_heuristics = interpreted.get("phase_selection_heuristics", [])

            segmentation = await self._segment_phases_by_dimensions_async(
                criterion_name=criterion_name,
                criterion_assertion=criterion_assertion,
                task_name=task_name,
                criterion_intent=criterion_intent,
                phase_selection_heuristics=phase_selection_heuristics,
                global_overview=global_overview,
                evaluation_dimensions=dimensions,
                all_steps=all_steps,
                model_name=model_name,
            )
            phases = segmentation.get("phases", [])
            relevant_ids = set(segmentation.get("relevant_phase_ids", []))
            target_phases = [phase for phase in phases if str(phase.get("phase_id")) in relevant_ids]
            if not target_phases:
                target_phases = phases

            configured_step_limit = (
                int(step_max_concurrency)
                if step_max_concurrency is not None
                else int(getattr(settings, "JUDGE_EVALUATION_STEP_MAX_CONCURRENCY", 8) or 8)
            )
            semaphore = asyncio.Semaphore(max(1, configured_step_limit))

            async def _run(phase: Dict[str, Any]) -> EvaluationResult:
                async with semaphore:
                    return await self._evaluate_phase_with_dimensions_async(
                        criterion_name=criterion_name,
                        criterion_assertion=criterion_assertion,
                        criterion_intent=criterion_intent,
                        persona_task_alignment=persona_task_alignment,
                        pass_signals=pass_signals if isinstance(pass_signals, list) else [],
                        fail_signals=fail_signals if isinstance(fail_signals, list) else [],
                        global_behavior_summary=str(global_overview.get("overall_behavior_summary", "")),
                        task_name=task_name,
                        personas=personas,
                        models=models,
                        evaluation_dimensions=dimensions,
                        phase=phase,
                        all_steps=all_steps,
                        model_name=model_name,
                    )

            phase_results = await asyncio.gather(*[_run(p) for p in target_phases])
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

            final = await self._synthesize_overall_from_phase_results_async(
                criterion_name=criterion_name,
                criterion_assertion=criterion_assertion,
                criterion_description=criterion_description or "",
                task_name=task_name,
                personas=personas,
                models=models,
                criterion_intent=criterion_intent,
                persona_task_alignment=persona_task_alignment,
                evaluation_dimensions=dimensions,
                global_behavior_summary=str(global_overview.get("overall_behavior_summary", "")),
                phase_results=phase_results,
                target_phases=target_phases,
                model_name=model_name or "gpt-4o-mini",
                all_steps=all_steps,
            )

            if final.verdict == "UNABLE_TO_EVALUATE" and len(phase_results) > 1:
                final = self._merge_evaluation_results(
                    results=phase_results,
                    criterion_name=criterion_name,
                    granularity=Granularity.PHASE_LEVEL,
                    criterion_assertion=criterion_assertion,
                    model_name=model_name or "gpt-4o-mini",
                )
            elif final.verdict == "UNABLE_TO_EVALUATE" and len(phase_results) == 1:
                final = phase_results[0]

            final.aggregated_step_summary = (
                f"Global-first phase evaluation. Relevant phases: {list(relevant_ids)}. "
                f"Global reasoning: {str(global_overview.get('global_reasoning', ''))}. "
                f"Segmentation reasoning: {segmentation.get('segmentation_reasoning', '')}"
            )[:500]
            final.used_granularity = Granularity.PHASE_LEVEL
            final = final.model_copy(update={"verdict": self._normalize_binary_verdict(final.verdict)})
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
        global_overview: Optional[Dict[str, Any]] = None,
        step_max_concurrency: Optional[int] = None,
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
            global_overview=global_overview,
            step_max_concurrency=step_max_concurrency,
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

    def _repair_evidence_with_llm(
        self,
        evidence: EvidenceCitation,
        step_obj: Dict[str, Any],
        criterion_name: str,
        model_name: Optional[str] = None,
    ) -> Optional[EvidenceCitation]:
        try:
            source_field = evidence.source_field.value if hasattr(evidence.source_field, "value") else str(evidence.source_field)
            llm = self.llm_factory.get_langchain_llm(model_name or "gpt-4o-mini")
            chain = self.evidence_reextract_template | llm
            invoke_dict = {
                "criterion_name": criterion_name,
                "source_field": source_field,
                "requested_text": evidence.highlighted_text or "",
                "step_index": int(evidence.step_index),
                "step_json": json.dumps(step_obj, ensure_ascii=False, indent=2),
            }
            response = chain.invoke(invoke_dict)
            response_text = response.content if hasattr(response, "content") else str(response)
            response_data = self._extract_json_object(response_text)
            if not response_data:
                return None

            candidate_text = str(response_data.get("highlighted_text", "") or "").strip()
            if not candidate_text:
                return None

            repaired_source_field = self._normalize_source_field(str(response_data.get("source_field", source_field)))
            candidates = self._extract_field_candidates(step_obj, repaired_source_field)

            matched_original = None
            for candidate in candidates:
                found = self._find_exact_original_snippet(candidate, candidate_text)
                if found:
                    matched_original = found
                    break

            if not matched_original:
                return None

            update_data: Dict[str, Any] = {
                "step_index": int(evidence.step_index),
                "highlighted_text": matched_original,
                "source_field": repaired_source_field,
            }

            reasoning = response_data.get("reasoning")
            if isinstance(reasoning, str) and reasoning:
                update_data["reasoning"] = reasoning

            verdict = response_data.get("verdict")
            if isinstance(verdict, str) and verdict.lower() in {"pass", "fail", "partial", "unknown"}:
                update_data["verdict"] = verdict.lower()

            return evidence.model_copy(update=update_data)
        except Exception as exc:
            logger.debug("Evidence re-extraction failed: %s", exc)
            return None

    def _ground_evidence_to_original_text(
        self,
        evidence: EvidenceCitation,
        all_steps: List[Dict[str, Any]],
        criterion_name: str,
        model_name: Optional[str] = None,
    ) -> Optional[EvidenceCitation]:
        requested = (evidence.highlighted_text or "").strip()
        if not requested:
            return None

        source_field = evidence.source_field.value if hasattr(evidence.source_field, "value") else str(evidence.source_field)
        declared_step_index = int(evidence.step_index)

        if 0 <= declared_step_index < len(all_steps):
            candidates = self._extract_field_candidates(all_steps[declared_step_index], source_field)
            for candidate in candidates:
                matched = self._find_exact_original_snippet(candidate, requested)
                if matched:
                    return evidence.model_copy(update={"step_index": declared_step_index, "highlighted_text": matched})

            repaired = self._repair_evidence_with_llm(
                evidence=evidence,
                step_obj=all_steps[declared_step_index],
                criterion_name=criterion_name,
                model_name=model_name,
            )
            if repaired is not None:
                return repaired

        unique_match = self._locate_unique_evidence_match(requested, source_field, all_steps)
        if unique_match is None:
            return None

        matched_step_index, matched_text = unique_match
        return evidence.model_copy(update={"step_index": matched_step_index, "highlighted_text": matched_text})

    def _filter_grounded_evidence(
        self,
        evidence_list: List[EvidenceCitation],
        all_steps: List[Dict[str, Any]],
        criterion_name: str,
        model_name: Optional[str] = None,
    ) -> List[EvidenceCitation]:
        grounded: List[EvidenceCitation] = []
        seen_keys = set()

        for evidence in evidence_list:
            try:
                grounded_item = self._ground_evidence_to_original_text(
                    evidence,
                    all_steps,
                    criterion_name=criterion_name,
                    model_name=model_name,
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
    ) -> List[EvidenceCitation]:
        current_evidence = list(base_evidence or [])
        curated_current = self._curate_story_evidence(
            self._keep_high_signal_evidence(current_evidence),
            step_indices,
        )

        if curated_current and self._is_evidence_coverage_sufficient(curated_current, step_indices):
            return curated_current
        if not all_steps or not step_indices:
            return curated_current

        try:
            llm = self.llm_factory.get_langchain_llm(model_name)
            chain = self.phase_evidence_expansion_template | llm

            existing_evidence_payload: List[Dict[str, Any]] = []
            for evidence in current_evidence:
                payload = evidence.model_dump()
                source_field = payload.get("source_field")
                if hasattr(source_field, "value"):
                    payload["source_field"] = source_field.value
                existing_evidence_payload.append(payload)

            invoke_dict = {
                "task_name": task_name,
                "criterion_name": criterion_name,
                "criterion_assertion": criterion_assertion,
                "phase_id": phase_id,
                "phase_summary": phase_summary,
                "phase_steps_context": self._build_phase_steps_context(all_steps, step_indices),
                "existing_evidence_json": json.dumps(existing_evidence_payload, ensure_ascii=False, indent=2),
                "coverage_lenses": json.dumps(
                    self._build_evidence_coverage_lenses(
                        criterion_name=criterion_name,
                        criterion_assertion=criterion_assertion,
                        phase_summary=phase_summary,
                        existing_evidence=curated_current,
                    ),
                    ensure_ascii=False,
                    indent=2,
                ),
            }

            response = await asyncio.to_thread(chain.invoke, invoke_dict)
            response_text = response.content if hasattr(response, "content") else str(response)
            response_data = self._extract_json_object(response_text) or {}
            additional_items = self._parse_highlighted_evidence_items(
                response_data.get("additional_highlighted_evidence", [])
            )
            if not additional_items:
                return curated_current

            merged = current_evidence + additional_items
            grounded = self._filter_grounded_evidence(
                evidence_list=merged,
                all_steps=all_steps,
                criterion_name=criterion_name,
                model_name=model_name,
            )
            return self._curate_story_evidence(
                self._keep_high_signal_evidence(grounded),
                step_indices,
            )
        except Exception as exc:
            logger.debug("Phase evidence expansion failed for %s: %s", phase_id, exc)
            return curated_current

    def _parse_evaluation_response(
        self,
        response_text: str,
        criterion_name: str,
        aggregated_steps: AggregatedSteps,
        all_steps: Optional[List[Dict[str, Any]]] = None,
        model_name: Optional[str] = None,
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
                model_name=model_name,
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

        return EvaluationResult(
            criterion_name=criterion_name,
            verdict=self._normalize_verdict(response_data.get("verdict", "UNABLE_TO_EVALUATE")),
            reasoning=response_data.get("reasoning", ""),
            confidence_score=float(response_data.get("confidence_score", 0.5)),
            relevant_steps=response_data.get("relevant_steps", []),
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
        evaluation_dimensions: List[Dict[str, Any]],
        global_behavior_summary: str,
        phase_results: List[EvaluationResult],
        target_phases: List[Dict[str, Any]],
        model_name: str,
        all_steps: List[Dict[str, Any]],
    ) -> EvaluationResult:
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
            phase_chunks.append(
                (
                    f"Phase: {phase_id}\n"
                    f"  Steps: {step_indices}\n"
                    f"  Phase Summary: {phase_summary}\n"
                    f"  Verdict: {result.verdict}\n"
                    f"  Confidence: {result.confidence_score}\n"
                    f"  Reasoning: {result.reasoning}\n"
                    f"  Evidence Count: {len(result.highlighted_evidence or [])}\n"
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
                model_name=model_name,
            )

        try:
            llm = self.llm_factory.get_langchain_llm(model_name)
            chain = self.phase_overall_synthesis_template | llm
            invoke_dict = {
                "task_name": task_name,
                "criterion_name": criterion_name,
                "criterion_assertion": criterion_assertion,
                "criterion_description": criterion_description or "",
                "personas": ", ".join(personas) if personas else "None",
                "models": ", ".join(models) if models else "None",
                "criterion_intent": criterion_intent,
                "persona_task_alignment": persona_task_alignment,
                "evaluation_dimensions": json.dumps(evaluation_dimensions, ensure_ascii=False, indent=2),
                "global_behavior_summary": global_behavior_summary,
                "phase_evaluations_summary": phase_evaluations_summary,
            }
            response = await asyncio.to_thread(chain.invoke, invoke_dict)
            response_text = response.content if hasattr(response, "content") else str(response)
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

    def _merge_evaluation_results(
        self,
        results: List[EvaluationResult],
        criterion_name: str,
        granularity: Granularity,
        criterion_assertion: str = "",
        model_name: str = "gpt-4o-mini",
    ) -> EvaluationResult:
        if not results:
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict="UNABLE_TO_EVALUATE",
                reasoning="No results to merge",
                confidence_score=0.0,
                aggregated_step_summary="No intermediate results to merge",
                used_granularity=granularity,
            )

        verdicts_str = ""
        for idx, result in enumerate(results):
            verdicts_str += (
                f"\nEvaluation {idx + 1}:\n"
                f"  Verdict: {result.verdict}\n"
                f"  Confidence: {result.confidence_score}\n"
                f"  Reasoning: {result.reasoning}\n"
            )

        try:
            llm = self.llm_factory.get_langchain_llm(model_name)
            chain = self.merge_template | llm
            response = chain.invoke(
                {
                    "criterion_name": criterion_name,
                    "criterion_assertion": criterion_assertion,
                    "granularity_type": "PHASE_LEVEL",
                    "individual_verdicts": verdicts_str,
                }
            )
            response_text = response.content if hasattr(response, "content") else str(response)
            return self._parse_merge_response(response_text, criterion_name, results, granularity)
        except Exception as exc:
            logger.warning("LLM merge failed: %s", exc)
            return self._simple_merge_results(results, criterion_name, granularity)

    def _parse_merge_response(
        self,
        response_text: str,
        criterion_name: str,
        results: List[EvaluationResult],
        granularity: Granularity,
    ) -> EvaluationResult:
        response_data = self._extract_json_object(response_text)
        if not response_data:
            return self._simple_merge_results(results, criterion_name, granularity)

        aggregated_evidence: List[EvidenceCitation] = []
        for result in results:
            if result.highlighted_evidence:
                aggregated_evidence.extend(result.highlighted_evidence)

        return EvaluationResult(
            criterion_name=criterion_name,
            verdict=self._normalize_verdict(response_data.get("verdict", "UNABLE_TO_EVALUATE")),
            reasoning=response_data.get("reasoning", ""),
            confidence_score=float(response_data.get("confidence_score", 0.5)),
            aggregated_step_summary=response_data.get("aggregation_summary", ""),
            used_granularity=granularity,
            highlighted_evidence=aggregated_evidence,
        )

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
        logger.info("Starting unified batch evaluation for run: %s with %d criteria", run_id, len(criteria))

        try:
            global_overview = await self._build_global_behavior_overview_async(
                task_name=task.name,
                personas=personas,
                models=models,
                all_steps=all_steps,
                model_name=evaluator_model,
            )
        except Exception as exc:
            logger.warning("Global behavior overview failed in batch mode, fallback to single-phase default: %s", exc)
            global_overview = {
                "overall_behavior_summary": "",
                "phases": [
                    {
                        "phase_id": "phase_0",
                        "semantic_label": "Complete Execution",
                        "step_indices": list(range(len(all_steps))),
                        "phase_summary": f"Complete execution with {len(all_steps)} steps",
                        "criticality": "high",
                        "why_key": "Fallback due to global overview failure.",
                    }
                ],
                "key_phase_ids": ["phase_0"],
                "global_reasoning": "Fallback global overview due to upstream error.",
            }

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
                global_overview=global_overview,
            )
            for criterion in criteria
        ]
        evaluation_results = await asyncio.gather(*criterion_tasks)
        overall_assessment = self._create_overall_assessment(evaluation_results)

        global_phases = global_overview.get("phases", []) if isinstance(global_overview, dict) else []
        subtask_clusters: List[StepCluster] = []
        for idx, phase in enumerate(global_phases if isinstance(global_phases, list) else []):
            if not isinstance(phase, dict):
                continue
            step_indices = [i for i in phase.get("step_indices", []) if isinstance(i, int)]
            if not step_indices:
                continue
            subtask_clusters.append(
                StepCluster(
                    cluster_id=str(phase.get("phase_id", f"phase_{idx}")),
                    semantic_label=str(phase.get("semantic_label", "Phase")),
                    step_indices=step_indices,
                    cluster_summary=str(phase.get("phase_summary", "")) or f"Phase {idx}",
                    key_decisions=[str(phase.get("why_key", ""))] if str(phase.get("why_key", "")).strip() else [],
                    dependencies=[],
                )
            )

        if not subtask_clusters:
            subtask_clusters = [
                StepCluster(
                    cluster_id="phase_0",
                    semantic_label="Unified Execution",
                    step_indices=list(range(len(all_steps))),
                    cluster_summary="Unified architecture evaluates dynamic LLM-segmented phases.",
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
                "pipeline_style": "global-phase-global",
                "global_behavior_summary": str(global_overview.get("overall_behavior_summary", ""))[:1000],
            },
        )
        logger.info("Unified batch evaluation complete for run: %s", run_id)
        return report
