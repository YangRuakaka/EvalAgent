# EvalAgent Expanded Sensemaking Study Protocol (Condensed)

**Version:** 6.0  
**Date:** July 29, 2026  
**Participants:** 12 GUI-agent developers, evaluators, or researchers  
**Session length:** Approximately 50 minutes; maximum 55 minutes  
**Environment:** EvalAgent and safe WebHarbor replicas

## 1. Study Goal

This study observes how developers:

1. configure two different agents for the same task;
2. predict how the agents will behave differently;
3. compare their trajectories with EvalAgent;
4. revise their explanation of agent behavior using evidence; and
5. turn that understanding into one targeted configuration revision.

The goal is not to test whether participants can find a “correct prompt.” We examine whether EvalAgent supports more specific and evidence-grounded explanations of agent behavior.

## 2. Research Questions

**RQ1:** How do users configure two meaningful agent variants for the same task and predict their behavioral differences?

**RQ2:** How does users’ understanding of the relationship between configuration and agent behavior change after trajectory comparison?

**RQ3:** Can users translate their updated understanding into a targeted configuration revision and predict its effect?

## 3. Participants and Tasks

Recruit 12 participants with experience in LLM agents, browser agents, GUI automation, prompting, debugging, or agent evaluation.

Each participant selects one of three safe replicas offered by the moderator and defines a task within five minutes. Across sessions, use multiple sites and task types rather than concentrating all participants on one shopping task.

A task must:

- be executable in a safe replica;
- involve no real payment, communication, or irreversible action;
- permit more than one reasonable strategy; and
- fit the study’s runtime budget.

## 4. Experimental Controls

The participant configures Agent A and Agent B for the same task. Only the configuration difference that the participant wants to investigate should vary.

Hold constant:

- model and version;
- task wording;
- website and initial state;
- tools and permissions;
- maximum steps and timeout; and
- execution environment.

Store the complete A, B, and revised configurations and trajectories.

## 5. Session Procedure

Ask one core question at each stage and record the corresponding key data.

| Time and stage | Participant activity | Required core question | Required data |
|---|---|---|---|
| 0–5 min: Select task | Select a site, task, and stopping condition | **What task did you choose, and what counts as completion?** | Site, task wording, stopping condition |
| 5–10 min: Configure A/B | Configure two agents for the same task | **What is the core configuration difference between Agents A and B, and why is it relevant to this task?** | Complete A/B configurations, exact configuration diff, participant’s stated contrast |
| 10–20 min: Prior prediction | Wait for A/B runs and predict behavior | **Before seeing the trajectories, how do you expect A and B to behave differently, and why?** | Expected difference, rationale, other factors that may affect the result |
| 20–35 min: Compare trajectories | Inspect similarities, differences, and evidence with EvalAgent | **What meaningful behavioral difference did you find, and what trajectory evidence supports it?** | Key locations inspected, identified difference, cited evidence |
| 35–38 min: Summarize understanding | Explain the configuration–behavior relationship | **Did the evidence confirm or change your initial understanding, and how do you now explain the relationship between configuration and behavior?** | Whether the initial explanation was confirmed, revised, or unresolved; post-comparison explanation |
| 38–42 min: Revise configuration | Make one targeted change to one agent | **What will you change, what behavior do you expect to change, and what result would support or challenge your explanation?** | Before/after diff, rationale, behavioral prediction, support/challenge condition |
| 42–50 min: Inspect result | Inspect the revised run and judge the explanation | **Did the revised behavior match your prediction, and does this make you keep, revise, or reject your explanation?** | Observed result, supported/partially supported/challenged/unresolved classification, final explanation, remaining question |

Keep the initial A/B trajectories hidden until both runs finish so that early results from one agent cannot change the initial comparison.

## 6. Moderation Principle

Ask each core question once, in the order shown above. Use a neutral follow-up such as “Could you be more specific?” only when an answer is unclear. Do not imply that a difference must have been caused by the prompt, persona, configuration, or Judge.

## 7. Data to Record

For every session, retain:

- participant background and agent experience;
- task, site, and stopping condition;
- complete Agent A and B configurations;
- the participant’s description of the core A/B difference;
- behavioral prediction and rationale before comparison;
- key trajectory moments inspected or cited;
- behavioral similarities and differences identified;
- whether the explanation was confirmed, revised, or remained uncertain;
- exact before/after configuration diff;
- predicted effect of the revision;
- whether revised behavior matched the prediction;
- remaining uncertainties;
- screen/audio recording, run status, and technical failures.

## 8. Evidence of Deeper Understanding

EvalAgent is considered to have supported further understanding when, after comparison, a participant can:

1. provide a more specific configuration–behavior explanation;
2. cite concrete trajectory evidence;
3. distinguish meaningful differences from incidental details and uncertainty;
4. make a targeted configuration revision based on the explanation; and
5. state in advance what result would support or challenge the explanation.

This is an ecological process study. It can show how participants use EvalAgent to deepen or revise understanding, but one revised run cannot prove a stable causal relationship between a configuration and behavior.

## 9. Analysis

The main unit of analysis is a sensemaking episode:

> prior prediction → inspected evidence → explanation → explanation change → configuration revision → run result

Two researchers code:

- what the participant noticed;
- what evidence they used;
- whether the explanation was confirmed, revised, or remained uncertain;
- whether they created a configuration revision; and
- whether the result supported, partially supported, challenged, or could not resolve the explanation.

Report common patterns, representative cases, negative cases, and descriptive counts. Do not conduct significance tests comparing websites.

## 10. Failure and Stopping Rules

- **Behavioral failure:** The agent gets stuck, makes a poor decision, or fails the task. Keep and analyze the run.
- **Technical failure:** The replica, browser, logging, or execution environment fails. Record separately. Allow one rerun only if no interpretable trajectory was produced.
- **Unexpected result:** Do not rerun. Retain it as a negative case.
- **Timeout:** If the revised run is incomplete at 55 minutes, end the live session, retain the participant’s prediction, and conduct one brief follow-up after completion.

## 11. Claim Boundaries

The study may support claims about:

- how users configure and compare agents;
- which EvalAgent resources support or complicate understanding;
- how explanations change;
- how explanations become configuration revisions; and
- where uncertainty remains.

The study cannot establish that:

- EvalAgent universally improves GUI-agent task success;
- one run proves a stable causal relationship between configuration and behavior;
- 12 participants represent all developers and websites; or
- Judge outputs or criteria are necessary for understanding agents.

## Appendix: Session Capture Sheet

### Context

- Participant ID:
- Role and agent experience:
- Site and task:
- Stopping condition:

### Configuration and Prediction

- Agent A configuration:
- Agent B configuration:
- Core A/B contrast:
- Predicted behavioral difference:
- Rationale and uncertainty:

### Comparison and Understanding

- Key trajectory moment:
- Important difference:
- Supporting evidence:
- Explanation confirmed, revised, or unresolved:
- Post-comparison configuration–behavior explanation:

### Configuration Revision

- What changed:
- Why:
- Predicted behavioral effect:
- Result that would support or challenge the explanation:
- Observed result:
- Final judgment:
- Remaining question:
