# InternPath AI — Architecture Decision Record (Phase 1)

## Product goal
Transform sourced internship requirements and student-confirmed evidence into an actionable, feasible Career Mission. Observe meaningful changes, decide whether replanning is needed, propose a versioned update, validate it, and request student approval before making it active.

## Boundaries
- `apps/web`: presentation only; no trust in frontend score or authorization.
- `services/api`: validates typed requests; will own student authorization, data repository, agent orchestration, and C++ calls.
- `engines/dsa`: custom C++20 algorithms; no LLM decisions and no independent authoritative database.
- `PostgreSQL` (Phase 2+): one authoritative store; source snapshots and mission versions must be auditable.

## Initial matching contract
`POST /v1/demo/match`
```
{
  "student_levels": [2,1,0,1],
  "required_levels": [2,2,1,1],
  "weights": [5,4,3,2],
  "mandatory": [1,1,0,0]
}
```
Levels are 0–3, required levels 1–3, weights 1–5, mandatory values 0 or 1.
C++ scores each skill with `weight * (6 * min(student_level, required_level) / required_level)`; maximum per skill = `6*weight`. Percent displayed as points / max points, rounded to 2 decimals. Mandatory gaps count mandatory requirements where current level is below required. It is **coverage of declared requirements**, not employment probability or verified competence.

## Originality and data integrity
Real job requirements must include exact source spans or be identified as unverified. Student skills are self-reports until supported by evidence. Demo/synthetic data must never be shown as real postings. The AI agent may propose a plan but a deterministic validator controls approval and persistence.

## Decision record
- 2026-10-22: One codebase, two demonstration modes.
- 2026-10-22: First build a small working end-to-end slice before large UI or agent coding.
- 2026-10-22: Use plain C++20 matching function behind a CLI, with a temporary simple argument-based integration boundary. Replace with durable versioned JSON transport during Phase 2.
- 2026-10-22: Do not build a fictional applicant-selection or hiring engine as the core product.
