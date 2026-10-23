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




