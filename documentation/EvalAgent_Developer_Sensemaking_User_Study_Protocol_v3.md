# EvalAgent Developer Sensemaking User Study Protocol

**Version:** 3.0  
**Date:** July 27, 2026  
**Study format:** Moderated remote developer sensemaking study with a short pre-session activity  
**Participant commitment:** Approximately 50 minutes total  
**Target sample:** 16 new participants  
**Environment:** EvalAgent and safe WebHarbor replicas

## 1. Study Purpose

This study investigates EvalAgent as a sensemaking environment for configuring and comparing GUI agents. Its central concern is not whether participants can write increasingly detailed evaluation criteria. Instead, it asks how people construct meaningful agent variations, compare the resulting behaviors, form explanations for similarities and differences, and use those explanations to decide how an agent should be configured next.

The study follows one core loop:

> Configure different agents → compare their behaviors → interpret similarities, differences, and surprises → revise a configuration → test the revised configuration.

Evaluation criteria and Agentic Judge evidence remain available as optional sensemaking resources. They are not required tasks and are not primary outcomes.

This is an **ecologically grounded** study. In this protocol, ecological validity means that the participants, tasks, and use context resemble the intended real-world setting: agent developers or evaluators use a safe pre-deployment sandbox, select a personally meaningful or work-relevant task, and construct configurations they would genuinely want to compare. It does not mean that the study concerns environmental ecology, nor does it imply deployment on live production websites.

This study complements rather than replaces the original controlled component study. The original study provides exploratory evidence about structural alignment and evidence highlighting. The present study examines the complete human sensemaking process around configuration, comparison, interpretation, and reconfiguration.

## 2. Research Questions

**RQ1 - Configuration:** How do users translate a task, preference, policy, or concern into multiple agent configurations that they consider meaningful to compare?

**RQ2 - Comparative sensemaking:** How do users make sense of similarities, differences, trade-offs, and unexpected behaviors across agents performing the same task?

**RQ3 - Mental-model revision:** How does comparative exploration change users' understanding of the relationship between an agent's configuration and its behavior?

**RQ4 - Reconfiguration and testing:** How do insights from comparison affect what users preserve, change, and test in a subsequent agent configuration?

Across these questions, the study also examines which patterns recur across domains and where participants remain uncertain or cannot form a satisfactory explanation.

## 3. Study Design

The study uses a single-condition, mixed-methods design. Every participant uses the complete EvalAgent system. There is no ablation condition because the goal is to understand the integrated sensemaking process rather than isolate one interface component.

Each participant:

1. Selects a personally meaningful WebHarbor domain and proposes a task.
2. Creates two contrasting agent configurations for the same task.
3. States how they expect the configurations to affect behavior.
4. Compares a neutral run and the two configured runs in EvalAgent.
5. Records the similarities, differences, surprises, and explanations that matter to them.
6. Revises one configuration or proposes a new configuration based on what they learned.
7. Inspects the revised run and determines whether it supports or challenges their explanation.

The same agent model, task, environment state, tools, and execution limits are held constant across runs. Only the participant-defined configuration changes.

## 4. Participants and Domain Coverage

### 4.1 Participants

Recruit 16 participants with experience developing, testing, using, or evaluating LLM-based agents. Relevant participants may include agent developers, evaluation or QA practitioners, HCI/AI researchers, responsible-AI auditors, and technically experienced agent users.

Prioritize participants whose work includes prompt or configuration testing, behavioral comparison, debugging, quality assurance, or pre-deployment evaluation.

Participants must:

- be at least 18 years old;
- be able to conduct the study in English;
- have relevant LLM-agent or evaluation experience; and
- be willing to share their screen and audio.

Low task performance, disagreement with EvalAgent, an incorrect interpretation, or failure to revise a configuration are not exclusion criteria.

### 4.2 Quota-constrained free choice

Participants choose from the complete study-ready WebHarbor catalog, but site selection is balanced to prevent all cases from concentrating on Amazon.

In the pre-session form, each participant ranks at least three sites and proposes a possible task for each. The researcher assigns the participant to their highest-ranked site with an open quota.

For N = 16:

- at least eight distinct sites must be represented;
- at least five broad domain families must be represented;
- no single site, including Amazon, may have more than two participants; and
- no broad domain family may have more than four participants.

If all ranked sites are full, the participant may choose among at least three underrepresented sites. Participants may decline rather than accept a domain that is not meaningful to them. The final paper reports whether each participant received their first, second, or third choice.

The study does not claim to validate every WebHarbor domain. It reports only the domains represented in the final sample.

## 5. Task and Agent Configuration

### 5.1 Participant-authored task

The task should be personally interesting, plausible, and capable of producing multiple reasonable strategies. It should involve searching, comparing, synthesizing, or recommending rather than a single obvious click.

Tasks must remain safe and reversible. They may not complete a purchase, reservation, enrollment, download, message, account change, or other consequential action. Participants use no real credentials or sensitive data.

The researcher may minimally edit a task for feasibility, safety, or a clear stopping condition, but may not add preferences or evaluation concerns on the participant's behalf. The participant approves the final wording.

### 5.2 Initial three runs

For the same task, the study prepares:

1. **Neutral run:** The task without an additional preference configuration.
2. **Configured Agent A:** The task plus the participant's first preference, policy, or behavioral priority.
3. **Configured Agent B:** The task plus a meaningfully contrasting priority.

Participants construct contrasts relevant to their own task rather than selecting from a fixed persona list. Examples may include cost versus convenience, novelty versus established reliability, speed versus thoroughness, popularity versus specialized fit, or resource efficiency versus capability.

Each configuration should describe what the agent should prioritize when several options satisfy the task. It must not allow the agent to ignore explicit requirements.

### 5.3 Trajectory generation

The initial three trajectories are generated before the moderated session to avoid spending study time waiting for agents. Use the first technically valid run for each configuration.

Behavioral failure, loops, incomplete comparison, or an undesirable choice remain valid study data. They are not rerun merely because they are uninteresting or unsuccessful.

One revised trajectory is generated during the moderated session after the participant completes the reconfiguration probe. Generation begins immediately and runs in the background while the moderator asks the first retrospective questions.

If generation takes longer than the remaining session, conduct a standardized 5-7 minute asynchronous follow-up within 48 hours. The revised run is part of the primary protocol, not optional future work.

## 6. Data Collected

The study collects six primary forms of data:

1. **Configuration artifacts:** Task, initial configurations, reasons for choosing the contrast, and revised configuration.
2. **Expectation data:** Predictions about how each agent will behave before trajectories are shown.
3. **Interaction data:** Graph navigation, trajectory switching, viewed steps, Judge use, and timestamped interface actions.
4. **Sensemaking data:** Think-aloud observations, interpretations, surprises, contradictions, and uncertainties.
5. **Final reflection:** Updated mental model, preferred configuration, and remaining uncertainty.
6. **Reconfiguration test:** Revised configuration, predicted behavioral change, observed revised behavior, and whether the new run supports, challenges, or leaves unresolved the participant's explanation.

The Agentic Judge and its evidence panel are logged only as possible triggers within the sensemaking process. The study does not require a minimum number of Judge calls or participant-authored criteria.

## 7. Study Procedure

### 7.1 Pre-session activity, approximately 8 minutes

Participants complete a short form:

1. Rank at least three WebHarbor sites.
2. Propose one realistic task for each ranked site.
3. For the assigned task, write two configurations they would like to compare.
4. Explain why this contrast matters.
5. Predict one or two ways the agents might behave differently.

The researcher checks feasibility, applies the site quota, confirms the task with the participant, and precomputes the initial trajectories.

### 7.2 Moderated session, approximately 42 minutes

#### Phase 1: Welcome and orientation, 4 minutes

The moderator explains:

> We are studying how people understand and configure agents, not whether you can find a correct answer. The agents may behave unexpectedly, and EvalAgent's Judge may also be wrong. Please use the interface in whatever way helps you understand the runs.

Demonstrate how to switch trajectories, inspect aligned and divergent steps, open step details, and optionally use the Judge. Do not demonstrate a preferred comparison strategy.

#### Phase 2: Initial mental model, 4 minutes

Before showing the runs, ask:

- What behavior were you trying to encourage with each configuration?
- Where do you expect the agents to behave similarly?
- Where do you expect them to differ?
- Which configuration do you initially expect to work best, and why?
- How confident are you in these expectations, from 1 to 7?

#### Phase 3: Free comparative exploration, 15 minutes

The participant freely explores the neutral run and two configured runs.

Opening prompt:

> Compare these agents as naturally as you would when trying to understand whether a configuration meaningfully changed behavior. Please tell me what you notice, what surprises you, and how you are explaining the differences.

Neutral follow-up prompts may include:

- What are you comparing right now?
- Is this difference meaningful or incidental?
- What do you think produced this behavior?
- Did anything contradict your expectation?
- Are these agents different in strategy, outcome, or both?
- What are you still uncertain about?

The moderator must not point participants toward a specific divergence, criterion, or Judge verdict.

#### Phase 4: Sensemaking map, 5 minutes

For each agent, the participant records:

- intended configuration;
- observed strategy;
- important similarities;
- important differences;
- most surprising behavior;
- current explanation of how configuration relates to behavior; and
- confidence in that explanation.

The participant marks whether each explanation is supported by a visible trace, based mainly on inference, or unresolved. This captures the participant's mental model without requiring formal evaluation criteria.

#### Phase 5: Reconfiguration probe and background execution, 5 minutes

Ask:

> If you could run one more agent, what would you preserve or change in its configuration, and what behavioral change would you expect?

The participant revises Agent A or B, or creates Configuration C. Record:

- revised configuration text;
- observation that prompted the revision;
- expected behavioral effect;
- result that would challenge the current explanation; and
- whether the revision is intended to improve the agent, test a hypothesis, or explore another trade-off.

Immediately execute the revised configuration using the same model, task, environment, tools, and execution limits. Only the revised configuration text changes.

#### Phase 6: Revised-run inspection, 5 minutes

Ask the participant to compare the revised run with the most relevant original run:

- Did the behavior change as expected?
- Which observation supports or challenges your explanation?
- Did the revised configuration isolate the intended difference?
- What remains ambiguous?
- Would you keep, revise, or discard this configuration?

Record whether the reconfiguration test confirms, partially confirms, contradicts, or does not resolve the participant's configuration-behavior hypothesis.

If the run is unavailable before the session ends, use the asynchronous follow-up described in Section 5.3.

#### Phase 7: Final interview, 4 minutes

Ask:

1. What did comparison help you understand that a single trajectory would not?
2. What was the most important surprise?
3. Did your understanding of either configuration change?
4. Which interface resource most affected your interpretation, and why?
5. What could you not determine from the available runs?
6. Would this workflow help you configure or test agents in a real pre-deployment setting?

Finally collect:

- preferred configuration, with ties allowed;
- final confidence in understanding the agents, from 1 to 7; and
- perceived mental effort, from 1 to 7.

## 8. Analysis Plan

### 8.1 Primary unit: sensemaking episode

The primary analytic unit is a time-bounded sensemaking episode:

> Trigger → observation → interpretation → mental-model update → configuration action → result of the reconfiguration test.

For example, a participant may observe that two agents reached the same result through different search strategies, interpret the difference as an effect of a speed-oriented configuration, find contradictory evidence, lower confidence, and revise the next configuration to specify when speed should be prioritized.

### 8.2 Coding dimensions

Code each episode for:

- **Trigger:** Graph structure, divergence, raw trace, outcome, Judge output, or comparison across runs.
- **Object of sensemaking:** Strategy, action, outcome, failure, trade-off, or configuration interpretation.
- **Relationship noticed:** Similarity, difference, contradiction, anomaly, or uncertainty.
- **Interpretive move:** Describing, comparing, explaining, questioning, testing, or revising.
- **Mental-model change:** Confirmation, elaboration, correction, replacement, or unresolved.
- **Configuration consequence:** Preserve, clarify, strengthen, weaken, combine, separate, or add a new configuration.
- **Reconfiguration result:** Confirmed, partially confirmed, contradicted, unresolved, or technically unavailable.

Two researchers independently code all episodes using a shared codebook, resolve disagreements, and report agreement for the structured categories.

### 8.3 Configuration analysis

Analyze how participants construct agent differences:

- abstract value labels versus operational instructions;
- single priorities versus conditional or multi-objective configurations;
- opposing configurations versus complementary probes;
- task-specific versus cross-domain configuration concepts; and
- configurations intended to optimize behavior versus configurations intended to test a hypothesis.

Compare each participant's initial and revised configuration to identify what the comparative exploration taught them to specify differently. Then compare the predicted effect with the revised trajectory.

A single revised run is not treated as causal proof. It is used to examine how participants formulate and test configuration-behavior hypotheses.

### 8.4 Descriptive measures

Report participant-level descriptive measures:

- number of meaningful similarities and differences identified;
- number of configuration-behavior links articulated;
- number of expectations confirmed, contradicted, or unresolved;
- number and type of mental-model revisions;
- whether the preferred configuration changed;
- whether a revised configuration was proposed;
- whether the revised run behaved as predicted;
- change in confidence; and
- which interface resources triggered sensemaking episodes.

These measures contextualize the qualitative findings. They are exploratory and are not used to compare domains statistically.

### 8.5 Cross-domain and negative-case analysis

Use a participant-by-domain matrix to distinguish:

- patterns recurring across at least two domain families;
- domain-specific forms of sensemaking;
- cases where configurations produced little meaningful difference;
- cases where participants inferred a relationship not supported by the trace;
- cases where the Judge distracted or misled participants;
- cases where comparison increased rather than resolved uncertainty;
- participants who chose not to revise a configuration; and
- revised configurations that failed to produce the intended behavior.

Negative and unresolved cases are reported as findings, not hidden as noise.

## 9. Claim Boundaries

If supported by the data, the study may show:

- how users construct contrasts among agents for personally meaningful tasks;
- how comparative trajectories support noticing and explaining behavioral variation;
- how surprises and contradictions reshape users' mental models;
- how sensemaking informs subsequent configuration choices and small-scale hypothesis testing; and
- which aspects of this process recur or break down across the observed domains.

The study must not claim that:

- EvalAgent proves a configuration caused a behavior;
- every WebHarbor domain was validated;
- the workflow improves configuration quality relative to a control condition; or
- participant explanations are equivalent to formal causal conclusions.

A revised run is a probe of the participant's explanation rather than a controlled causal experiment.

## 10. Recommended Paper Framing

Present the expanded study as a developer sensemaking study that complements the original controlled component study:

> The controlled study examined how structural alignment and evidence surfacing supported comparison and inspection. The expanded developer sensemaking study examined the broader human process around these components: how users constructed agent variations, made sense of resulting behaviors, revised their mental models, and tested a subsequent configuration across self-selected WebHarbor tasks.

The results should follow the sensemaking loop:

1. Constructing meaningful agent contrasts.
2. Noticing alignable similarities and differences.
3. Explaining surprises and revising mental models.
4. Turning understanding into reconfiguration and testing.
5. Cross-domain recurrence, uncertainty, and breakdowns.

Criteria evolution may appear as a secondary observation when participants voluntarily use criteria, but it should not organize the study or its main claims.
