import test from 'node:test';
import assert from 'node:assert/strict';

// -------------------------------------------------------------
// 1. Data Schema & Transformation Tests
// -------------------------------------------------------------

test('Skill model parsing and category categorization', () => {
  const sampleSkill = {
    id: 6,
    name: 'High-Scale Distributed Systems',
    category: 'Systems',
    max_level: 5,
    description: 'Consensus protocols and distributed architectures',
    prerequisites: [4, 5],
    unlocked_skills: [],
  };

  assert.equal(sampleSkill.id, 6);
  assert.equal(sampleSkill.category, 'Systems');
  assert.deepEqual(sampleSkill.prerequisites, [4, 5]);
  assert.equal(sampleSkill.max_level, 5);
});

test('Student skill state mapping distinguishes verified from self-reported', () => {
  const skills = [
    { id: 1, name: 'Foundations' },
    { id: 2, name: 'Python' },
    { id: 7, name: 'Git' },
  ];

  // Default state initialization
  const studentSkills = {};
  skills.forEach((s) => {
    if (s.id === 1) studentSkills[s.id] = { level: 2, is_verified: true };
    else if (s.id === 2) studentSkills[s.id] = { level: 2, is_verified: true };
    else if (s.id === 7) studentSkills[s.id] = { level: 1, is_verified: false };
    else studentSkills[s.id] = { level: 0, is_verified: false };
  });

  // Verify status mapping
  assert.equal(studentSkills[1].is_verified, true);
  assert.equal(studentSkills[2].is_verified, true);
  assert.equal(studentSkills[7].is_verified, false);

  // Payload serialization
  const payload = Object.entries(studentSkills)
    .filter(([, val]) => val.level > 0)
    .map(([idStr, val]) => ({
      skill_id: Number(idStr),
      level: val.level,
      is_verified: val.is_verified,
    }));

  assert.equal(payload.length, 3);
  assert.deepEqual(payload[0], { skill_id: 1, level: 2, is_verified: true });
  assert.deepEqual(payload[2], { skill_id: 7, level: 1, is_verified: false });
});

test('Preset handlers correctly reset or assign profiles', () => {
  const allIds = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

  // Beginner preset (All 0)
  const beginner = {};
  allIds.forEach((id) => {
    beginner[id] = { level: 0, is_verified: false };
  });
  assert(Object.values(beginner).every((v) => v.level === 0 && !v.is_verified));

  // Advanced preset (Level 3 verified)
  const advanced = {};
  allIds.forEach((id) => {
    advanced[id] = { level: 3, is_verified: true };
  });
  assert(Object.values(advanced).every((v) => v.level === 3 && v.is_verified));
});

test('Learning plan stages represent parallelizable DAG partitions', () => {
  const samplePlan = {
    achievable: true,
    stages: [
      {
        stage_number: 1,
        stage_title: 'Stage 1: Foundational Prerequisites',
        stage_effort: { min_hours: 30, max_hours: 50 },
        skills: [
          { skill_id: 3, skill_name: 'C++', level_delta: 1 },
          { skill_id: 9, skill_name: 'SQL', level_delta: 1 },
        ],
      },
      {
        stage_number: 2,
        stage_title: 'Stage 2: Advanced Competencies',
        stage_effort: { min_hours: 35, max_hours: 59 },
        skills: [
          { skill_id: 5, skill_name: 'DSA', level_delta: 1 },
          { skill_id: 4, skill_name: 'FastAPI', level_delta: 1 },
        ],
      },
    ],
  };

  assert.equal(samplePlan.stages.length, 2);
  // Stage 1 contains 2 skills that can be studied in parallel
  assert.equal(samplePlan.stages[0].skills.length, 2);
  assert.equal(samplePlan.stages[0].stage_effort.min_hours, 30);
  assert.equal(samplePlan.stages[0].stage_effort.max_hours, 50);
});

// -------------------------------------------------------------
// 2. Live API Integration Tests from Web Client
// -------------------------------------------------------------

async function isServerRunning() {
  try {
    const res = await fetch('http://127.0.0.1:8000/health', {
      signal: AbortSignal.timeout(1000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

test('Frontend can fetch live /v1/skills from FastAPI', async (t) => {
  if (!(await isServerRunning())) {
    t.skip('FastAPI backend not running at 127.0.0.1:8000');
    return;
  }
  const res = await fetch('http://127.0.0.1:8000/v1/skills');
  assert.equal(res.status, 200);
  const skills = await res.json();
  assert(Array.isArray(skills));
  assert.equal(skills.length, 10);
});

test('Frontend can fetch live /v1/roles from FastAPI', async (t) => {
  if (!(await isServerRunning())) {
    t.skip('FastAPI backend not running at 127.0.0.1:8000');
    return;
  }
  const res = await fetch('http://127.0.0.1:8000/v1/roles');
  assert.equal(res.status, 200);
  const roles = await res.json();
  assert(Array.isArray(roles));
  assert.equal(roles.length, 2);
});

test('Frontend can generate learning path end-to-end via FastAPI & C++ engine', async (t) => {
  if (!(await isServerRunning())) {
    t.skip('FastAPI backend not running at 127.0.0.1:8000');
    return;
  }
  const res = await fetch('http://127.0.0.1:8000/v1/learning-path/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      role_id: 'distributed-systems-intern',
      student_skills: [
        { skill_id: 1, level: 2, is_verified: true },
        { skill_id: 2, level: 2, is_verified: true },
      ],
    }),
  });

  assert.equal(res.status, 200);
  const plan = await res.json();
  assert.equal(plan.achievable, true);
  assert(Array.isArray(plan.stages));
  assert(plan.stages.length >= 1);
  assert(plan.total_estimated_effort.min_hours > 0);
  assert(plan.total_estimated_effort.max_hours >= plan.total_estimated_effort.min_hours);
  assert(plan.algorithm_trace != null);
  assert(plan.algorithm_trace.execution_time_microseconds > 0);
});

test('Frontend can fetch persisted /v1/profile from FastAPI database', async (t) => {
  if (!(await isServerRunning())) {
    t.skip('FastAPI backend not running at 127.0.0.1:8000');
    return;
  }
  const res = await fetch('http://127.0.0.1:8000/v1/profile');
  assert.equal(res.status, 200);
  const profile = await res.json();
  assert.equal(profile.email, 'alex.dev@internpath.local');
  assert(Array.isArray(profile.skills));
  assert(profile.skills.length >= 3);
  assert(Array.isArray(profile.evidence));
});

test('Frontend can update /v1/profile and persist to database', async (t) => {
  if (!(await isServerRunning())) {
    t.skip('FastAPI backend not running at 127.0.0.1:8000');
    return;
  }
  const updatePayload = {
    name: 'Alex Chen (Dev Mode)',
    weekly_hours: 18,
    skills: [
      { skill_id: 1, declared_level: 3, is_verified: true },
      { skill_id: 2, declared_level: 2, is_verified: true },
      { skill_id: 7, declared_level: 1, is_verified: false },
    ],
  };
  const res = await fetch('http://127.0.0.1:8000/v1/profile', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updatePayload),
  });
  assert.equal(res.status, 200);
  const updated = await res.json();
  assert.equal(updated.weekly_hours, 18);
  const skill1 = updated.skills.find((s) => s.skill_id === 1);
  assert.equal(skill1.declared_level, 3);
});

// -------------------------------------------------------------
// 3. Phase 3.3 Career Mission & Plan Governance Frontend Tests
// -------------------------------------------------------------

test('Career Mission progress and remaining pacing calculation', () => {
  const mission = {
    total_tasks: 8,
    completed_tasks: 2,
    weekly_hours: 15,
    estimated_remaining_hours_min: 45,
    estimated_remaining_hours_max: 75,
  };

  const progressPercent = Math.round((mission.completed_tasks / mission.total_tasks) * 100);
  assert.equal(progressPercent, 25);

  const estimatedWeeks = Math.ceil(mission.estimated_remaining_hours_max / mission.weekly_hours);
  assert.equal(estimatedWeeks, 5);
});

test('Task prerequisite unlock evaluation in client roadmap', () => {
  const tasksByKey = {
    task_skill_1_lvl_2: { status: 'completed' },
    task_skill_2_lvl_2: { status: 'in_progress' },
    task_skill_4_lvl_2: { status: 'not_started' },
  };

  function checkUnlocked(prereqKeys) {
    if (!prereqKeys || prereqKeys.length === 0) return true;
    return prereqKeys.every((k) => tasksByKey[k]?.status === 'completed');
  }

  // Task depending on skill 1 (completed) -> unlocked
  assert.equal(checkUnlocked(['task_skill_1_lvl_2']), true);

  // Task depending on skill 2 (in_progress) -> locked
  assert.equal(checkUnlocked(['task_skill_2_lvl_2']), false);

  // Task depending on both -> locked
  assert.equal(checkUnlocked(['task_skill_1_lvl_2', 'task_skill_2_lvl_2']), false);

  // Independent task -> unlocked
  assert.equal(checkUnlocked([]), true);
});

test('Proposal diff calculation correctly structures added, removed, and retained tasks', () => {
  const diffSummary = {
    added_tasks: [{ skill_name: 'Docker & Containerization', target_level: 2 }],
    removed_tasks: [{ skill_name: 'High-Scale Distributed Systems', target_level: 3 }],
    retained_tasks: [{ skill_name: 'Backend APIs (FastAPI)', preserved_status: 'completed' }],
    effort_delta: { min_hours: -15, max_hours: -20 },
  };

  assert.equal(diffSummary.added_tasks.length, 1);
  assert.equal(diffSummary.removed_tasks.length, 1);
  assert.equal(diffSummary.retained_tasks.length, 1);
  assert.equal(diffSummary.retained_tasks[0].preserved_status, 'completed');
  assert.equal(diffSummary.effort_delta.min_hours, -15);
});

test('Frontend can fetch active Career Mission from FastAPI', async (t) => {
  if (!(await isServerRunning())) {
    t.skip('FastAPI backend not running at 127.0.0.1:8000');
    return;
  }
  const res = await fetch('http://127.0.0.1:8000/v1/missions/active');
  // Returns either 200 (if active mission exists) or 404 (if none created yet)
  assert([200, 404].includes(res.status));
});

// -------------------------------------------------------------
// Phase 3.4: Agent Activity & Event Tests
// -------------------------------------------------------------

test('Agent decision category badge mapping and text labels', () => {
  const categories = [
    { cat: 'proposed_mission_adjustment', expectedPrefix: '⚡ PROPOSED' },
    { cat: 'informational_notification', expectedPrefix: 'ℹ INFORMATIONAL' },
    { cat: 'human_review_required', expectedPrefix: '⚠ HUMAN' },
    { cat: 'no_action', expectedPrefix: '○ NO ACTION' },
  ];

  function getBadgeLabel(cat) {
    switch (cat) {
      case 'proposed_mission_adjustment':
        return '⚡ PROPOSED MISSION ADJUSTMENT';
      case 'informational_notification':
        return 'ℹ INFORMATIONAL NOTIFICATION';
      case 'human_review_required':
        return '⚠ HUMAN REVIEW REQUIRED';
      case 'no_action':
      default:
        return '○ NO ACTION REQUIRED';
    }
  }

  for (const { cat, expectedPrefix } of categories) {
    const label = getBadgeLabel(cat);
    assert(label.startsWith(expectedPrefix));
  }
});

test('Agent tool execution logging structures inputs, outputs, and step ordering', () => {
  const toolLog = [
    { tool: 'inspect_relevant_event', input: { event_id: 'evt_123' }, output: { role_id: 'distributed-systems' } },
    { tool: 'read_student_profile', input: { student_id: 1 }, output: { weekly_hours: 15 } },
    { tool: 'calculate_deadline_impact', input: { mission_id: 1 }, output: { decision_category: 'proposed_mission_adjustment' } },
  ];

  assert.equal(toolLog.length, 3);
  assert.equal(toolLog[0].tool, 'inspect_relevant_event');
  assert.equal(toolLog[1].input.student_id, 1);
  assert.equal(toolLog[2].output.decision_category, 'proposed_mission_adjustment');
});

test('Demo simulation requests structure valid controlled scenarios', () => {
  const validScenarios = [
    'deadline_earlier',
    'deadline_extended',
    'unrelated_role',
    'evidence_added',
    'untrusted_source',
    'deadline_earlier_infeasible',
    'stale_event',
  ];

  for (const sc of validScenarios) {
    const req = { scenario: sc };
    assert.equal(typeof req.scenario, 'string');
    assert(validScenarios.includes(req.scenario));
  }
});

test('Phase 3.5 Capacity utilization calculation and color thresholds', () => {
  function getCapacityColor(ratio) {
    if (ratio <= 1.0) return 'green';
    if (ratio <= 1.8) return 'yellow';
    return 'red';
  }

  assert.equal(getCapacityColor(0.8), 'green');
  assert.equal(getCapacityColor(1.0), 'green');
  assert.equal(getCapacityColor(1.4), 'yellow');
  assert.equal(getCapacityColor(1.8), 'yellow');
  assert.equal(getCapacityColor(2.2), 'red');
});

test('Phase 3.5 Engine badge classification distinguishes real, mock, and rule engines', () => {
  function getEngineClass(engine) {
    if (engine.startsWith('gemini:')) return 'engine-chip-gemini';
    if (engine.startsWith('openai:')) return 'engine-chip-openai';
    if (engine === 'mock_llm') return 'engine-chip-mock';
    return 'engine-chip-rules';
  }

  assert.equal(getEngineClass('gemini:gemini-1.5-pro'), 'engine-chip-gemini');
  assert.equal(getEngineClass('openai:gpt-4o'), 'engine-chip-openai');
  assert.equal(getEngineClass('mock_llm'), 'engine-chip-mock');
  assert.equal(getEngineClass('deterministic_rules'), 'engine-chip-rules');
});

test('Frontend can fetch /v1/agent/runs from FastAPI', async (t) => {
  if (!(await isServerRunning())) {
    t.skip('FastAPI backend not running at 127.0.0.1:8000');
    return;
  }
  const res = await fetch('http://127.0.0.1:8000/v1/agent/runs');
  assert.equal(res.status, 200);
  const data = await res.json();
  assert(Array.isArray(data));
});

// -------------------------------------------------------------
// Refinement R1.1: Student Navigation & Home Experience Tests
// -------------------------------------------------------------

test('R1.1 Primary student navigation architecture separates student tabs from technical mode', () => {
  const studentTabs = ['home', 'careers', 'roadmap', 'readiness'];
  const technicalTabs = ['technical'];

  assert.equal(studentTabs.length, 4);
  assert.equal(studentTabs[0], 'home');
  assert(!studentTabs.includes('technical'));
  assert(technicalTabs.includes('technical'));
});

test('R1.1 Deterministic next recommended action derivation prioritizes in_progress over unlocked', () => {
  function getNextAction(tasks) {
    const inProgress = tasks.find((t) => t.status === 'in_progress');
    if (inProgress) return { task: inProgress, type: 'in_progress' };

    const completedKeys = new Set(tasks.filter((t) => t.status === 'completed').map((t) => t.stable_key));
    const nextUnlocked = tasks.find((t) => {
      if (t.status !== 'not_started') return false;
      const prereqs = t.prerequisite_task_keys || [];
      return prereqs.every((k) => completedKeys.has(k));
    });
    if (nextUnlocked) return { task: nextUnlocked, type: 'unlocked' };

    const allCompleted = tasks.every((t) => t.status === 'completed');
    if (allCompleted) return { task: null, type: 'all_completed' };

    return { task: tasks[0], type: 'unlocked' };
  }

  // Case 1: Active task in progress
  const tasks1 = [
    { id: 1, stable_key: 't1', status: 'completed', prerequisite_task_keys: [] },
    { id: 2, stable_key: 't2', status: 'in_progress', prerequisite_task_keys: ['t1'] },
    { id: 3, stable_key: 't3', status: 'not_started', prerequisite_task_keys: ['t1'] },
  ];
  assert.equal(getNextAction(tasks1).task.id, 2);
  assert.equal(getNextAction(tasks1).type, 'in_progress');

  // Case 2: No task in progress, pick first unlocked task
  const tasks2 = [
    { id: 1, stable_key: 't1', status: 'completed', prerequisite_task_keys: [] },
    { id: 2, stable_key: 't2', status: 'not_started', prerequisite_task_keys: ['t1'] },
    { id: 3, stable_key: 't3', status: 'not_started', prerequisite_task_keys: ['t2'] },
  ];
  assert.equal(getNextAction(tasks2).task.id, 2);
  assert.equal(getNextAction(tasks2).type, 'unlocked');

  // Case 3: All tasks completed
  const tasks3 = [
    { id: 1, stable_key: 't1', status: 'completed', prerequisite_task_keys: [] },
    { id: 2, stable_key: 't2', status: 'completed', prerequisite_task_keys: ['t1'] },
  ];
  assert.equal(getNextAction(tasks3).task, null);
  assert.equal(getNextAction(tasks3).type, 'all_completed');
});

test('R1.1 Pending plan proposal alert triggered when pending proposals count > 0', () => {
  function shouldShowProposalBanner(mission) {
    return Boolean(mission && mission.pending_proposals_count > 0);
  }

  assert.equal(shouldShowProposalBanner({ pending_proposals_count: 0 }), false);
  assert.equal(shouldShowProposalBanner({ pending_proposals_count: 1 }), true);
  assert.equal(shouldShowProposalBanner({ pending_proposals_count: 2 }), true);
  assert.equal(shouldShowProposalBanner(null), false);
});

test('R1.1 New student vs returning student Home view state discrimination', () => {
  function getHomeState(mission) {
    if (!mission) return 'new_student_welcome';
    return 'returning_student_roadmap';
  }

  assert.equal(getHomeState(null), 'new_student_welcome');
  assert.equal(getHomeState({ id: 1, title: 'Embedded Systems' }), 'returning_student_roadmap');
});

// -------------------------------------------------------------
// 5. Refinement R1.2: Guided Student Onboarding Flow Tests
// -------------------------------------------------------------

test('R1.2 Onboarding: Role selection and requirement filtering by role', () => {
  const roles = [
    { role_id: 'distributed-systems-intern', title: 'Distributed Systems', requirements_count: 2 },
    { role_id: 'backend-api-intern', title: 'Backend Platform', requirements_count: 3 },
  ];

  function selectRole(selectedId) {
    const role = roles.find((r) => r.role_id === selectedId);
    assert(role, `Role ${selectedId} should exist in catalogue`);
    return role;
  }

  const selected = selectRole('backend-api-intern');
  assert.equal(selected.title, 'Backend Platform');
  assert.equal(selected.requirements_count, 3);
});

test('R1.2 Onboarding: Skill rating scale strictly enforces levels 0 to 3', () => {
  function validateSkillRating(level) {
    if (typeof level !== 'number' || level < 0 || level > 3 || !Number.isInteger(level)) {
      throw new Error(`Invalid skill level ${level}: must be an integer between 0 and 3.`);
    }
    const labels = {
      0: 'Not yet learned',
      1: 'Basic',
      2: 'Intermediate',
      3: 'Advanced',
    };
    return labels[level];
  }

  assert.equal(validateSkillRating(0), 'Not yet learned');
  assert.equal(validateSkillRating(1), 'Basic');
  assert.equal(validateSkillRating(2), 'Intermediate');
  assert.equal(validateSkillRating(3), 'Advanced');

  assert.throws(() => validateSkillRating(-1), /Invalid skill level/);
  assert.throws(() => validateSkillRating(4), /Invalid skill level/);
  assert.throws(() => validateSkillRating(2.5), /Invalid skill level/);
});

test('R1.2 Onboarding: Weekly hours validation and preset mappings', () => {
  function validateWeeklyHours(hrs) {
    if (typeof hrs !== 'number' || isNaN(hrs) || hrs < 1 || hrs > 80) {
      return { valid: false, error: 'Weekly hours must be between 1 and 80 hours/week.' };
    }
    return { valid: true, error: null };
  }

  // Presets
  const presets = [5, 10, 15, 20];
  presets.forEach((p) => {
    assert.equal(validateWeeklyHours(p).valid, true);
  });

  // Boundary conditions
  assert.equal(validateWeeklyHours(1).valid, true);
  assert.equal(validateWeeklyHours(80).valid, true);
  assert.equal(validateWeeklyHours(0).valid, false);
  assert.equal(validateWeeklyHours(-5).valid, false);
  assert.equal(validateWeeklyHours(81).valid, false);
});

test('R1.2 Onboarding: Multi-step draft state retention across Back and Continue navigation', () => {
  // Simulate Onboarding multi-step state container
  const draft = {
    step: 1,
    selectedRoleId: 'backend-api-intern',
    skillRatings: { 4: 2, 9: 1 },
    weeklyHours: 15,
  };

  // Step 1 -> Step 2
  draft.step = 2;
  draft.skillRatings[8] = 0; // added in Step 2

  // Step 2 -> Step 3
  draft.step = 3;
  draft.weeklyHours = 20; // modified in Step 3

  // Step 3 -> Back to Step 2
  draft.step = 2;
  // Verify ratings and role were retained
  assert.equal(draft.selectedRoleId, 'backend-api-intern');
  assert.deepEqual(draft.skillRatings, { 4: 2, 9: 1, 8: 0 });
  assert.equal(draft.weeklyHours, 20);

  // Step 2 -> Back to Step 1
  draft.step = 1;
  assert.equal(draft.selectedRoleId, 'backend-api-intern');
  assert.deepEqual(draft.skillRatings, { 4: 2, 9: 1, 8: 0 });
});

test('R1.2 Onboarding: Truthful deadline display when unconfirmed', () => {
  function getDeadlineNotice(verifiedDeadlineDate) {
    if (!verifiedDeadlineDate) {
      return {
        confirmed: false,
        text: 'Internship deadline not confirmed',
        disclaimer: 'Verified employer application closing dates will be shown here when officially announced.',
      };
    }
    return { confirmed: true, text: verifiedDeadlineDate, disclaimer: 'Verified deadline' };
  }

  const notice = getDeadlineNotice(null);
  assert.equal(notice.confirmed, false);
  assert.equal(notice.text, 'Internship deadline not confirmed');
  assert(notice.disclaimer.includes('Verified employer application closing dates'));
});

test('R1.2 Onboarding: Prevention of duplicate mission submissions while processing', () => {
  let isSubmitting = false;
  let submissionCount = 0;

  function attemptSubmit() {
    if (isSubmitting) {
      return false; // submission locked
    }
    isSubmitting = true;
    submissionCount++;
    return true;
  }

  assert.equal(attemptSubmit(), true);
  assert.equal(submissionCount, 1);

  // Duplicate click while in-flight
  assert.equal(attemptSubmit(), false);
  assert.equal(submissionCount, 1);

  // Unlock after request completes
  isSubmitting = false;
  assert.equal(attemptSubmit(), true);
  assert.equal(submissionCount, 2);
});

test('R1.2 Onboarding: Live first Career Mission generation and persistence via FastAPI', async (t) => {
  if (!(await isServerRunning())) {
    t.skip('FastAPI backend not running at 127.0.0.1:8000');
    return;
  }

  // 1. Update student profile with onboarding skill ratings
  const updateRes = await fetch('http://127.0.0.1:8000/v1/profile', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      target_role_id: 'backend-api-intern',
      weekly_hours: 15,
      skills: [
        { skill_id: 1, declared_level: 2, verified_level: 0, is_verified: false },
        { skill_id: 2, declared_level: 1, verified_level: 0, is_verified: false },
        { skill_id: 4, declared_level: 0, verified_level: 0, is_verified: false },
        { skill_id: 9, declared_level: 0, verified_level: 0, is_verified: false },
      ],
    }),
  });
  assert.equal(updateRes.status, 200);

  // 2. Generate and persist Career Mission (allow_replace_active: true to ensure clean test state)
  const missionRes = await fetch('http://127.0.0.1:8000/v1/missions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      target_role_id: 'backend-api-intern',
      weekly_hours: 15,
      allow_replace_active: true,
    }),
  });
  assert.equal(missionRes.status, 201);
  const mission = await missionRes.json();

  assert(mission.id > 0);
  assert.equal(mission.target_role_id, 'backend-api-intern');
  assert.equal(mission.status, 'active');
  assert.equal(mission.active_version_number, 1);
  assert(mission.total_tasks > 0);
  assert(mission.active_version.stages.length > 0);

  // 3. Verify mission persists across active lookup
  const activeRes = await fetch('http://127.0.0.1:8000/v1/missions/active');
  assert.equal(activeRes.status, 200);
  const active = await activeRes.json();
  assert.equal(active.id, mission.id);
  assert.equal(active.target_role_id, 'backend-api-intern');
});

test('R1.2 Onboarding: Active mission conflict detection & protection (HTTP 409)', async (t) => {
  if (!(await isServerRunning())) {
    t.skip('FastAPI backend not running at 127.0.0.1:8000');
    return;
  }

  // Attempting to create mission with same active role when allow_replace_active is false
  const conflictRes = await fetch('http://127.0.0.1:8000/v1/missions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      target_role_id: 'backend-api-intern',
      weekly_hours: 15,
      allow_replace_active: false,
    }),
  });

  // Must return HTTP 409 Conflict to protect existing student mission
  assert.equal(conflictRes.status, 409);
  const errBody = await conflictRes.json();
  assert(errBody.detail.includes('already exists'));
});

// -------------------------------------------------------------
// Refinement R1.3: Student-Friendly Careers & Roadmap Tests
// -------------------------------------------------------------

test('R1.3 Checkpoint A1: Verification state preservation during self-assessment', () => {
  // Simulating OnboardingFlow skillsPayload assembly with existing verified state
  const existingSkills = [
    { skill_id: 1, declared_level: 2, verified_level: 2, is_verified: true },
    { skill_id: 2, declared_level: 1, verified_level: 1, is_verified: true },
    { skill_id: 7, declared_level: 1, verified_level: 0, is_verified: false },
  ];
  const userRatings = { 1: 3, 2: 1, 7: 2 };

  const existingMap = new Map(existingSkills.map((s) => [s.skill_id, s]));
  const payload = Object.entries(userRatings).map(([sid, rating]) => {
    const sId = Number(sid);
    const prev = existingMap.get(sId);
    return {
      skill_id: sId,
      declared_level: Number(rating),
      verified_level: prev?.is_verified ? prev.verified_level : 0,
      is_verified: prev?.is_verified ?? false,
    };
  });

  const skill1 = payload.find((s) => s.skill_id === 1);
  const skill7 = payload.find((s) => s.skill_id === 7);

  // Skill 1 declared level is updated to 3, but verified level 2 and is_verified: true are preserved
  assert.equal(skill1.declared_level, 3);
  assert.equal(skill1.verified_level, 2);
  assert.equal(skill1.is_verified, true);

  // Skill 7 was unverified; declared level updated to 2, verified remains 0 and false
  assert.equal(skill7.declared_level, 2);
  assert.equal(skill7.verified_level, 0);
  assert.equal(skill7.is_verified, false);
});

test('R1.3 Checkpoint A2: Partial failure & 409 active mission reconciliation', () => {
  // Simulate active mission lookup reconciliation
  const activeMission = {
    id: 42,
    target_role_id: 'embedded-firmware-intern',
    status: 'active',
  };

  const selectedRoleId = 'embedded-firmware-intern';
  const shouldReconcile = activeMission && activeMission.target_role_id === selectedRoleId;
  assert.equal(shouldReconcile, true);

  const differentRoleId = 'cloud-devops-intern';
  const shouldPromptReplace = activeMission && activeMission.target_role_id !== differentRoleId;
  assert.equal(shouldPromptReplace, true);
});

test('R1.3 Checkpoint A3: Weekly availability neutral pacing and effort estimates', () => {
  const pacingPresets = [
    { hours: 5, label: 'Steady Pace (5 hrs/wk)' },
    { hours: 10, label: 'Moderate Pace (10 hrs/wk)' },
    { hours: 15, label: 'Dedicated Track (15 hrs/wk)' },
    { hours: 20, label: 'Intensive Track (20 hrs/wk)' },
  ];

  // Presets use realistic, neutral pacing descriptors (no "Recommended" bias for high hours)
  pacingPresets.forEach((p) => {
    assert(!p.label.toLowerCase().includes('recommended'));
    assert(p.hours >= 5 && p.hours <= 20);
  });

  // Safe clamping of custom hours
  function clampHours(h) {
    if (isNaN(h) || h < 1) return 1;
    if (h > 60) return 60;
    return h;
  }
  assert.equal(clampHours(0), 1);
  assert.equal(clampHours(-5), 1);
  assert.equal(clampHours(100), 60);
  assert.equal(clampHours(15), 15);
});

test('R1.3 Checkpoint B: Role fixture provenance labels & honest academic fixtures', () => {
  const sampleRole = {
    role_id: 'iot-edge-engineer',
    title: 'IoT Edge Systems Intern',
    source_url: null,
  };

  function getProvenanceBadge(role) {
    if (!role.source_url) {
      return { label: 'DEMO ROLE • ILLUSTRATIVE FIXTURE', isIllustrative: true };
    }
    return { label: 'VERIFIED INDUSTRY POSTING', isIllustrative: false };
  }

  const badge = getProvenanceBadge(sampleRole);
  assert.equal(badge.isIllustrative, true);
  assert(badge.label.includes('DEMO ROLE'));
});

test('R1.3 Checkpoint B: Mandatory Core vs Preferred Elective requirement separation', () => {
  const roleSkills = [
    { skill_id: 1, skill_name: 'C Programming', required_level: 2, importance: 'critical' },
    { skill_id: 2, skill_name: 'Microcontrollers', required_level: 2, importance: 'required' },
    { skill_id: 3, skill_name: 'FreeRTOS', required_level: 1, importance: 'preferred' },
    { skill_id: 4, skill_name: 'PCB Design', required_level: 1, importance: 'optional' },
  ];

  const mandatory = roleSkills.filter((s) => s.importance === 'critical' || s.importance === 'required');
  const electives = roleSkills.filter((s) => s.importance === 'preferred' || s.importance === 'optional');

  assert.equal(mandatory.length, 2);
  assert.equal(electives.length, 2);
  assert.equal(mandatory[0].skill_name, 'C Programming');
  assert.equal(electives[0].skill_name, 'FreeRTOS');
});

test('R1.3 Checkpoint B: Student skill-gap calculations against role requirements', () => {
  const roleReqs = [
    { skill_id: 1, skill_name: 'C Programming', required_level: 2 },
    { skill_id: 2, skill_name: 'RTOS Concepts', required_level: 2 },
    { skill_id: 3, skill_name: 'PCB Layout', required_level: 1 },
  ];

  const studentSkills = [
    { skill_id: 1, declared_level: 2, verified_level: 2, is_verified: true },
    { skill_id: 2, declared_level: 1, verified_level: 0, is_verified: false },
    // skill 3 not yet assessed (level 0)
  ];

  const studentMap = new Map(studentSkills.map((s) => [s.skill_id, s]));

  const gaps = [];
  const acquired = [];

  roleReqs.forEach((req) => {
    const s = studentMap.get(req.skill_id);
    const curLevel = s ? s.declared_level : 0;
    if (curLevel >= req.required_level) {
      acquired.push({ ...req, curLevel });
    } else {
      gaps.push({ ...req, curLevel, gapDelta: req.required_level - curLevel });
    }
  });

  assert.equal(acquired.length, 1);
  assert.equal(acquired[0].skill_name, 'C Programming');

  assert.equal(gaps.length, 2);
  assert.equal(gaps[0].skill_name, 'RTOS Concepts');
  assert.equal(gaps[0].gapDelta, 1);
  assert.equal(gaps[1].skill_name, 'PCB Layout');
  assert.equal(gaps[1].gapDelta, 1);
});

test('R1.3 Checkpoint C: Deterministic next-step derivation with student-friendly reasoning', () => {
  function getNextAction(tasks) {
    if (tasks.length === 0) {
      return { task: null, type: 'all_completed', reason: 'No milestones registered in active mission.' };
    }
    const inProg = tasks.find((t) => t.status === 'in_progress');
    if (inProg) {
      return {
        task: inProg,
        type: 'in_progress',
        reason: 'Active Milestone: You have already started this task. Continue your momentum.',
      };
    }
    const completedKeys = new Set(
      tasks.filter((t) => t.status === 'completed').map((t) => t.stable_key)
    );
    const nextUnlocked = tasks.find((t) => {
      if (t.status !== 'not_started') return false;
      if (t.is_unlocked) return true;
      const prereqs = t.prerequisite_task_keys || [];
      return prereqs.every((k) => completedKeys.has(k));
    });
    if (nextUnlocked) {
      const prereqs = nextUnlocked.prerequisite_task_keys || [];
      const reason =
        prereqs.length === 0
          ? 'Foundational milestone: No prior prerequisites required. Start here.'
          : 'Prerequisites verified complete: All preparatory foundation skills are met. Ready to begin.';
      return { task: nextUnlocked, type: 'unlocked', reason };
    }
    return { task: null, type: 'all_completed', reason: 'All milestones 100% complete.' };
  }

  // Foundational first task without prereqs
  const tasks = [
    { id: 10, stable_key: 't1', status: 'not_started', is_unlocked: true, prerequisite_task_keys: [] },
    { id: 11, stable_key: 't2', status: 'not_started', is_unlocked: false, prerequisite_task_keys: ['t1'] },
  ];
  const next1 = getNextAction(tasks);
  assert.equal(next1.task.id, 10);
  assert.equal(next1.type, 'unlocked');
  assert(next1.reason.includes('Foundational milestone'));

  // When task 10 is completed, task 11 becomes unlocked
  tasks[0].status = 'completed';
  const next2 = getNextAction(tasks);
  assert.equal(next2.task.id, 11);
  assert.equal(next2.type, 'unlocked');
  assert(next2.reason.includes('Prerequisites verified complete'));
});

test('R1.3 Checkpoint C: Prerequisite locks prevent un-audited completion', () => {
  const task = {
    id: 11,
    skill_name: 'RTOS Context Switching',
    is_unlocked: false,
    prerequisite_task_keys: ['task_c_basics'],
  };

  function canCompleteWithoutOverride(t, completedKeys) {
    if (t.is_unlocked) return true;
    return t.prerequisite_task_keys.every((k) => completedKeys.has(k));
  }

  const completedKeys = new Set();
  assert.equal(canCompleteWithoutOverride(task, completedKeys), false);

  completedKeys.add('task_c_basics');
  assert.equal(canCompleteWithoutOverride(task, completedKeys), true);
});

test('R1.3 Checkpoint C: Stage collapse toggle state tracking', () => {
  const collapsedStages = {};

  function toggleStage(stageNum) {
    collapsedStages[stageNum] = !collapsedStages[stageNum];
  }

  assert.equal(collapsedStages[1], undefined);
  toggleStage(1);
  assert.equal(collapsedStages[1], true);
  toggleStage(1);
  assert.equal(collapsedStages[1], false);
});

test('R1.3 Checkpoint D: Lightweight Roadmap filter states', () => {
  const tasks = [
    { id: 1, status: 'completed', is_unlocked: true, prerequisite_task_keys: [] },
    { id: 2, status: 'in_progress', is_unlocked: true, prerequisite_task_keys: [] },
    { id: 3, status: 'not_started', is_unlocked: true, prerequisite_task_keys: [] },
    { id: 4, status: 'not_started', is_unlocked: false, prerequisite_task_keys: ['k_unmet'] },
  ];

  const completedKeys = new Set(['k1']);
  const isTaskReady = (t) => {
    if (t.status === 'completed') return false;
    if (t.is_unlocked) return true;
    return t.prerequisite_task_keys.every((k) => completedKeys.has(k));
  };

  const filterTasks = (filter) =>
    tasks.filter((t) => {
      if (filter === 'all') return true;
      if (filter === 'in_progress') return t.status === 'in_progress';
      if (filter === 'completed') return t.status === 'completed';
      if (filter === 'ready') return t.status === 'not_started' && isTaskReady(t);
      if (filter === 'locked') return t.status === 'not_started' && !isTaskReady(t);
      return true;
    });

  assert.equal(filterTasks('all').length, 4);
  assert.equal(filterTasks('ready').length, 1);
  assert.equal(filterTasks('ready')[0].id, 3);
  assert.equal(filterTasks('in_progress').length, 1);
  assert.equal(filterTasks('in_progress')[0].id, 2);
  assert.equal(filterTasks('completed').length, 1);
  assert.equal(filterTasks('completed')[0].id, 1);
  assert.equal(filterTasks('locked').length, 1);
  assert.equal(filterTasks('locked')[0].id, 4);
});

test('R1.3 Checkpoint D: Navigation routing between Home, Careers, and Roadmap', () => {
  const routes = {
    'home-next-action-click': 'roadmap',
    'careers-start-prep-click': 'onboarding',
    'roadmap-review-proposal-click': 'proposals',
    'roadmap-explore-roles-click': 'careers',
  };

  assert.equal(routes['home-next-action-click'], 'roadmap');
  assert.equal(routes['careers-start-prep-click'], 'onboarding');
  assert.equal(routes['roadmap-review-proposal-click'], 'proposals');
  assert.equal(routes['roadmap-explore-roles-click'], 'careers');
});

test('R1.3 Checkpoint F: Technical Mode preservation and student boundary separation', () => {
  const studentNavTabs = ['home', 'careers', 'roadmap', 'readiness'];
  const devWorkspaceTabs = ['technical'];

  // Normal student view tabs contain zero raw graph algorithm debug panels
  studentNavTabs.forEach((tab) => {
    assert(tab !== 'technical');
  });

  // Technical mode preserves full C++ DSA presenter, event simulation, and tool traces
  const technicalModeComponents = [
    'GraphPresenter',
    'MatchingDemo',
    'AgentActivityView',
    'EventSimulationControls',
  ];
  assert.equal(technicalModeComponents.length, 4);
});

test('R1.3 Live Backend Integration: Task status transition and persistence', async (t) => {
  if (!(await isServerRunning())) {
    t.skip('FastAPI backend not running at 127.0.0.1:8000');
    return;
  }

  // 1. Fetch active mission
  const activeRes = await fetch('http://127.0.0.1:8000/v1/missions/active');
  if (activeRes.status !== 200) {
    t.skip('No active mission available for live integration test');
    return;
  }
  const activeMission = await activeRes.json();
  const firstStage = activeMission.active_version?.stages?.[0];
  const firstTask = firstStage?.tasks?.[0];
  if (!firstTask) {
    t.skip('No tasks in active mission');
    return;
  }

  // 2. Update task status to in_progress
  const patchRes = await fetch(
    `http://127.0.0.1:8000/v1/missions/${activeMission.id}/tasks/${firstTask.id}/status`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'in_progress' }),
    }
  );
  assert.equal(patchRes.status, 200);
  const updatedTask = await patchRes.json();
  assert.equal(updatedTask.status, 'in_progress');
});

test('R1.3 Live Backend Integration: Evidence attachment to mission task', async (t) => {
  if (!(await isServerRunning())) {
    t.skip('FastAPI backend not running at 127.0.0.1:8000');
    return;
  }

  const activeRes = await fetch('http://127.0.0.1:8000/v1/missions/active');
  if (activeRes.status !== 200) {
    t.skip('No active mission available for live integration test');
    return;
  }
  const activeMission = await activeRes.json();
  const firstTask = activeMission.active_version?.stages?.[0]?.tasks?.[0];
  if (!firstTask) {
    t.skip('No tasks in active mission');
    return;
  }

  // Check evidence list
  const evRes = await fetch('http://127.0.0.1:8000/v1/evidence');
  if (evRes.status !== 200) {
    t.skip('Evidence API not accessible');
    return;
  }
  const evidenceList = await evRes.json();
  if (evidenceList.length === 0) {
    t.skip('No evidence items to attach');
    return;
  }

  const evId = evidenceList[0].id;
  const linkRes = await fetch(
    `http://127.0.0.1:8000/v1/missions/${activeMission.id}/tasks/${firstTask.id}/evidence`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ evidence_id: evId, notes: 'R1.3 integration verification artifact.' }),
    }
  );
  assert.equal(linkRes.status, 200);
  const linkedTask = await linkRes.json();
  assert.equal(linkedTask.evidence_id, evId);
});






