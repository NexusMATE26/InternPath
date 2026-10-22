# Working draft — InnovaX Phase 1 proposal

**Check the organizer-supplied proposal template before submission. Deadline: November 4, 2026.** This file is draft content, not a completed official template.

## Title
InternPath AI — An Evidence-Grounded Adaptive Internship-Readiness Agent for Engineering Undergraduates

## Domain
Domain B — Education & Human Capability

## The problem
Engineering students often struggle to turn scattered internship requirements into specific, realistic preparation actions. A skill listed on a CV is not necessarily demonstrable. Generic career plans can also become outdated when employer requirements, deadlines, and students' available time change.

## Proposed solution
InternPath AI connects *sourced internship requirement records*, a *student Evidence Ledger*, and a *versioned Career Mission*. A deterministic engine analyzes skills and prerequisite dependencies. A bounded AI agent investigates relevant events, selects approved tools, proposes reasonable plan changes, verifies constraints, and asks the student to approve material modifications. The agent also records explained no-op decisions when an event does not justify replanning.

## Why an AI agent rather than a chatbot?
The agent maintains persistent goal and mission state, calls real services, interprets new events, chooses whether to reassess, compares mission versions, handles failures, and observes the committed result. A single chat response alone does not cover those ongoing decisions and verified tool actions.

## Distinctive contribution
A traceable requirement-to-evidence-to-action-to-approved-revision loop, with clear uncertainty, source anchors, hard validation and explicit human control. The contribution should be demonstrated using event-driven replanning compared against a one-shot-plan baseline, not merely claimed as novel.

## Data
Start with approximately 15–20 permission-compliant internship descriptions (one career family), preserving source URL/text spans and retrieval timestamps. Students can manually enter skills/projects and submit their own descriptions. Label simulated postings and event changes as test fixtures.

## Feasibility
Three-person team. React and TypeScript interface; FastAPI services, PostgreSQL for state, C++20 algorithms for matching, graph prerequisites and searches, and a Python agent using an approved LLM provider. Build the core vertical slice first, then source-grounded planning, then replanning, approvals and testing.

## Responsible AI
Unknown evidence stays unknown; no invented CV claims, unauthorized scraping, or automatic applications. Irreversible or consequential actions require human confirmation. Prompt-injection defenses, validated service tools, per-user authorization, protected student information and reproducible logs are included.

## Impact and evaluation
Measure correctness of extracted requirement spans, task feasibility, correct replan/no-op decisions, reliability of version commits and perceived usefulness with student testers. Report measured findings and limitations, not unsupported success percentages.

## Originality disclosure
This project builds on academic exploration of matching algorithms while introducing evidence-grounded persistent adaptive planning; disclose actual earlier work and third-party/AI contributions according to organizer instructions. Confirm eligibility if the DSA assessment and competition are simultaneous.
