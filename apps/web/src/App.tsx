import { useState, useEffect } from 'react';
import CareerMissionView from './components/CareerMissionView';
import { AgentActivityView } from './components/AgentActivityView';


// Types for Phase 1 matching
type MatchResult = {
  earned_points: number;
  max_points: number;
  missing_mandatory: number;
  mandatory_requirements_met: boolean;
  coverage_percent: number;
};

const phase1Skills = [
  { name: 'C++', target: 2, weight: 5, mandatory: 1 },
  { name: 'Data Structures', target: 2, weight: 4, mandatory: 1 },
  { name: 'RTOS', target: 1, weight: 3, mandatory: 0 },
  { name: 'Git', target: 1, weight: 2, mandatory: 0 },
];

// Types for Phase 3.1 Learning Path Engine
interface Skill {
  id: number;
  name: string;
  category: string;
  max_level: number;
  description: string;
  prerequisites: number[];
  unlocked_skills: number[];
}

interface RoleItem {
  role_id: string;
  title: string;
  department: string;
  location: string;
  description: string;
  requirements_count: number;
}

interface EffortRange {
  min_hours: number;
  max_hours: number;
}

interface SkillUpgrade {
  skill_id: number;
  skill_name: string;
  category: string;
  current_level: number;
  target_level: number;
  level_delta: number;
  is_verified: boolean;
  verification_status: string;
  estimated_effort: EffortRange;
  rationale: string;
}

interface LearningStage {
  stage_number: number;
  stage_title: string;
  stage_effort: EffortRange;
  skills: SkillUpgrade[];
}

interface AlgorithmTrace {
  graph_representation: string;
  graph_node_count: number;
  graph_edge_count: number;
  prerequisite_closure_nodes_visited: number;
  kahn_queue_enqueues: number;
  kahn_queue_dequeues: number;
  topo_stages_formed: number;
  execution_time_microseconds: number;
}

interface LearningPlan {
  achievable: boolean;
  message: string;
  target_skills: number[];
  missing_skills: number[];
  prerequisite_closure: number[];
  total_estimated_effort: EffortRange;
  stages: LearningStage[];
  algorithm_trace?: AlgorithmTrace;
}

interface StudentSkillState {
  level: number;
  is_verified: boolean;
}

interface EvidenceItem {
  id: number;
  skill_id: number;
  skill_name: string;
  title: string;
  description: string;
  url?: string | null;
  evidence_type: string;
  verified_by_staff: boolean;
  created_at?: string | null;
}

interface StudentProfile {
  id: number;
  name: string;
  email: string;
  target_role_id?: string | null;
  weekly_hours: number;
  is_demo: boolean;
  skills: Array<{
    skill_id: number;
    skill_name: string;
    category: string;
    declared_level: number;
    verified_level: number;
    is_verified: boolean;
  }>;
  evidence: EvidenceItem[];
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'mission' | 'path' | 'match' | 'agent'>('mission');


  // Phase 1 state
  const [matchLevels, setMatchLevels] = useState<number[]>([2, 1, 0, 1]);
  const [matchResult, setMatchResult] = useState<MatchResult | null>(null);
  const [matchError, setMatchError] = useState('');
  const [matchWorking, setMatchWorking] = useState(false);

  // Phase 3.1 & 3.2 state
  const [skills, setSkills] = useState<Skill[]>([]);
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [selectedRoleId, setSelectedRoleId] = useState<string>('distributed-systems-intern');
  const [studentSkills, setStudentSkills] = useState<Record<number, StudentSkillState>>({});
  const [studentName, setStudentName] = useState('Alex Chen (Dev Mode)');
  const [weeklyHours, setWeeklyHours] = useState(15);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSaveSuccess, setProfileSaveSuccess] = useState(false);
  const [profileSaveError, setProfileSaveError] = useState('');

  const [plan, setPlan] = useState<LearningPlan | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState('');
  const [showDsaInspector, setShowDsaInspector] = useState(false);
  const [viewMode, setViewMode] = useState<'stages' | 'graph'>('stages');
  const [selectedSkillNode, setSelectedSkillNode] = useState<Skill | null>(null);

  // Load initial skills, roles, and persisted student profile
  useEffect(() => {
    async function loadInitialData() {
      try {
        const [skillsRes, rolesRes, profileRes] = await Promise.all([
          fetch('/v1/skills'),
          fetch('/v1/roles'),
          fetch('/v1/profile'),
        ]);
        if (skillsRes.ok && rolesRes.ok) {
          const loadedSkills: Skill[] = await skillsRes.json();
          const loadedRoles: RoleItem[] = await rolesRes.json();
          setSkills(loadedSkills);
          setRoles(loadedRoles);

          const initialMap: Record<number, StudentSkillState> = {};
          loadedSkills.forEach((s) => {
            initialMap[s.id] = { level: 0, is_verified: false };
          });

          if (profileRes.ok) {
            const profile: StudentProfile = await profileRes.json();
            setStudentName(profile.name);
            setWeeklyHours(profile.weekly_hours);
            if (profile.target_role_id) {
              setSelectedRoleId(profile.target_role_id);
            }
            if (profile.evidence) {
              setEvidenceList(profile.evidence);
            }
            profile.skills.forEach((ps) => {
              initialMap[ps.skill_id] = {
                level: ps.declared_level,
                is_verified: ps.is_verified,
              };
            });
          } else {
            // Default fallback
            if (initialMap[1]) initialMap[1] = { level: 2, is_verified: true };
            if (initialMap[2]) initialMap[2] = { level: 2, is_verified: true };
            if (initialMap[7]) initialMap[7] = { level: 1, is_verified: false };
          }
          setStudentSkills(initialMap);
        }
      } catch (err) {
        console.error('Failed to load initial data:', err);
      }
    }
    loadInitialData();
  }, []);


  // Phase 1 Analyze handler
  async function analyzeMatch() {
    setMatchError('');
    setMatchWorking(true);
    try {
      const response = await fetch('/v1/demo/match', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          student_levels: matchLevels,
          required_levels: phase1Skills.map((s) => s.target),
          weights: phase1Skills.map((s) => s.weight),
          mandatory: phase1Skills.map((s) => s.mandatory),
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `API HTTP ${response.status}`);
      }
      setMatchResult(await response.json());
    } catch (e) {
      setMatchError(e instanceof Error ? e.message : 'Unknown error');
      setMatchResult(null);
    } finally {
      setMatchWorking(false);
    }
  }

  // Phase 3.1 Generate Learning Path handler
  async function generateLearningPath() {
    setPlanError('');
    setPlanLoading(true);
    try {
      const studentPayload = Object.entries(studentSkills)
        .filter(([, val]) => val.level > 0)
        .map(([idStr, val]) => ({
          skill_id: Number(idStr),
          level: val.level,
          is_verified: val.is_verified,
        }));

      const response = await fetch('/v1/learning-path/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role_id: selectedRoleId,
          student_skills: studentPayload,
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `API HTTP ${response.status}`);
      }

      const generatedPlan: LearningPlan = await response.json();
      setPlan(generatedPlan);
    } catch (e) {
      setPlanError(e instanceof Error ? e.message : 'Failed to generate learning plan');
      setPlan(null);
    } finally {
      setPlanLoading(false);
    }
  }

  // Preset handlers
  function applyPreset(preset: 'default' | 'beginner' | 'advanced') {
    const updated: Record<number, StudentSkillState> = {};
    skills.forEach((s) => {
      if (preset === 'default') {
        if (s.id === 1) updated[s.id] = { level: 2, is_verified: true };
        else if (s.id === 2) updated[s.id] = { level: 2, is_verified: true };
        else if (s.id === 7) updated[s.id] = { level: 1, is_verified: false };
        else updated[s.id] = { level: 0, is_verified: false };
      } else if (preset === 'beginner') {
        updated[s.id] = { level: 0, is_verified: false };
      } else if (preset === 'advanced') {
        updated[s.id] = { level: 3, is_verified: true };
      }
    });
    setStudentSkills(updated);
  }

  // Phase 3.2 Save Profile handler (PUT /v1/profile)
  async function saveProfile() {
    setProfileSaving(true);
    setProfileSaveError('');
    setProfileSaveSuccess(false);
    try {
      const skillsPayload = Object.entries(studentSkills).map(([idStr, val]) => ({
        skill_id: Number(idStr),
        declared_level: val.level,
        verified_level: val.is_verified ? val.level : 0,
        is_verified: val.is_verified,
      }));

      const res = await fetch('/v1/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: studentName,
          target_role_id: selectedRoleId,
          weekly_hours: weeklyHours,
          skills: skillsPayload,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      setProfileSaveSuccess(true);
      setTimeout(() => setProfileSaveSuccess(false), 3500);
    } catch (err) {
      setProfileSaveError(err instanceof Error ? err.message : 'Failed to save profile');
    } finally {
      setProfileSaving(false);
    }
  }

  // Phase 3.3 Adopt plan as persistent Career Mission
  async function adoptPlanAsCareerMission() {
    try {
      const res = await fetch('/v1/missions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_role_id: selectedRoleId,
          weekly_hours: weeklyHours,
          allow_replace_active: true,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      setActiveTab('mission');
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to create career mission');
    }
  }

  const selectedRole = roles.find((r) => r.role_id === selectedRoleId);


  return (
    <div className="shell">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="brand">
          <span className="mark">✦</span>
          <span>
            InternPath <b>AI</b>
          </span>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          <div
            id="nav-career-mission"
            className={`nav-item ${activeTab === 'mission' ? 'active' : ''}`}
            onClick={() => setActiveTab('mission')}
          >
            🎯 &nbsp; Career Mission
          </div>
          <div
            id="nav-learning-path"
            className={`nav-item ${activeTab === 'path' ? 'active' : ''}`}
            onClick={() => setActiveTab('path')}
          >
            🛤 &nbsp; Learning Path
          </div>
          <div
            id="nav-dashboard"
            className={`nav-item ${activeTab === 'match' ? 'active' : ''}`}
            onClick={() => setActiveTab('match')}
          >
            ▦ &nbsp; Readiness Match
          </div>
          <div className="nav-item">
            ⌕ &nbsp; Opportunities <i>soon</i>
          </div>
          <div className="nav-item">
            ◈ &nbsp; Skills & Evidence <i>soon</i>
          </div>
          <div
            id="nav-agent"
            className={`nav-item ${activeTab === 'agent' ? 'active' : ''}`}
            onClick={() => setActiveTab('agent')}
          >
            ✧ &nbsp; Agent Activity
          </div>
        </nav>
        <div className="sidebar-bottom">
          PHASE 3.4 • AGENTIC AI FOUNDATION
          <br />
          <small>Bounded Event-Driven AI & Human Boundary</small>
        </div>
      </aside>

      {/* Main Content Area */}
      <main>
        <header className="topbar">
          <span>
            Internship Readiness & Skill Graph Engine &nbsp;•&nbsp;{' '}
            <b>
              {activeTab === 'mission'
                ? 'Persistent Career Mission & Governance'
                : activeTab === 'path'
                  ? 'Learning Path Planner'
                  : activeTab === 'agent'
                    ? 'Autonomous Career Event Observer & Audit Log'
                    : 'Phase 1 Scoring Preview'}
            </b>
          </span>
          <div className="topbar-actions">
            {activeTab === 'path' && (
              <button
                id="btn-toggle-dsa"
                className={`pill-toggle ${showDsaInspector ? 'active' : ''}`}
                onClick={() => setShowDsaInspector(!showDsaInspector)}
                title="Toggle DSA Presenter Visibility Mode"
              >
                🔬 Presenter DSA Mode {showDsaInspector ? 'ON' : 'OFF'}
              </button>
            )}
            <span className="pill">● C++20 Verified</span>
          </div>
        </header>

        <div className="content">
          {/* ======================================================== */}
          {/* TAB 0: CAREER MISSION (PHASE 3.3)                        */}
          {/* ======================================================== */}
          {activeTab === 'mission' && (
            <CareerMissionView
              onNavigateToPlanner={() => setActiveTab('path')}
              availableRoles={roles}
              evidenceList={evidenceList}
            />
          )}

          {/* ======================================================== */}
          {/* TAB: AGENT ACTIVITY (PHASE 3.4)                          */}
          {/* ======================================================== */}
          {activeTab === 'agent' && (
            <AgentActivityView
              onNavigateToMission={() => setActiveTab('mission')}
            />
          )}


          {/* ======================================================== */}
          {/* TAB 1: LEARNING PATH ENGINE (PHASE 3.1)                  */}
          {/* ======================================================== */}
          {activeTab === 'path' && (
            <div className="learning-path-container">
              <div className="eyebrow">DAG ENGINE & LEARNING PLANNER</div>
              <h1>Build your verified path to target roles.</h1>
              <p className="lede">
                Select your target internship, configure your current skill competencies, and ask
                our C++20 graph engine to generate a dependency-sound, topologically staged
                learning path.
              </p>

              {/* Role Selection & Student Skill Configuration Grid */}
              <div className="planner-grid">
                {/* Panel 1: Target Role Selector */}
                <div className="panel target-panel">
                  <div className="panel-header">
                    <div>
                      <h2>1. Target Internship Role</h2>
                      <p>Select the engineering position you are aiming for.</p>
                    </div>
                    <span className="mini-icon">🎯</span>
                  </div>

                  <div className="role-cards-container">
                    {roles.map((r) => (
                      <div
                        id={`role-card-${r.role_id}`}
                        key={r.role_id}
                        className={`role-card ${selectedRoleId === r.role_id ? 'selected' : ''}`}
                        onClick={() => setSelectedRoleId(r.role_id)}
                      >
                        <div className="role-card-header">
                          <strong className="role-title">{r.title}</strong>
                          <span className="badge-dept">{r.department}</span>
                        </div>
                        <p className="role-desc">{r.description}</p>
                        <div className="role-meta">
                          <span>📍 {r.location}</span>
                          <span className="req-count">
                            {r.requirements_count} required competencies
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  {selectedRole && (
                    <div className="role-detail-box">
                      <div className="box-title">ROLE PREREQUISITE FOCUS</div>
                      <p className="box-body">
                        This role requires mastery across distributed architectures, systems-level
                        prerequisites, and containerized deployment.
                      </p>
                    </div>
                  )}
                </div>

                {/* Panel 2: Student Skills & Verification Controls */}
                <div className="panel skills-panel">
                  <div className="panel-header">
                    <div>
                      <h2>2. Your Current Skills</h2>
                      <p>
                        Distinguish between verified competence and self-reported declarations.
                      </p>
                    </div>
                    <span className="mini-icon">🛡️</span>
                  </div>

                  {/* Single-User Dev Profile Persistence Bar */}
                  <div className="profile-persistence-bar">
                    <div className="profile-info">
                      <span className="profile-tag">DEV MODE</span>
                      <strong>{studentName}</strong>
                      <span style={{ color: '#64748b' }}>
                        • {weeklyHours}h/week study • Database Persistent
                      </span>
                    </div>
                    <div className="profile-actions">
                      <button
                        type="button"
                        id="btn-save-profile"
                        className="save-profile-btn"
                        onClick={saveProfile}
                        disabled={profileSaving}
                      >
                        {profileSaving ? 'Saving…' : '💾 Save Profile Changes'}
                      </button>
                      {profileSaveSuccess && (
                        <span className="save-status-msg success">✓ Saved to Database</span>
                      )}
                      {profileSaveError && (
                        <span className="save-status-msg error">⚠️ {profileSaveError}</span>
                      )}
                    </div>
                  </div>

                  {/* Quick Presets */}
                  <div className="presets-bar">
                    <span className="presets-label">Quick Profiles:</span>
                    <button
                      type="button"
                      id="preset-default"
                      className="preset-btn"
                      onClick={() => applyPreset('default')}
                    >
                      Sample Student
                    </button>
                    <button
                      type="button"
                      id="preset-beginner"
                      className="preset-btn"
                      onClick={() => applyPreset('beginner')}
                    >
                      Beginner (0)
                    </button>
                    <button
                      type="button"
                      id="preset-advanced"
                      className="preset-btn"
                      onClick={() => applyPreset('advanced')}
                    >
                      Experienced (3)
                    </button>
                  </div>

                  {/* Skills Table */}
                  <div className="skills-scroll-list">
                    <div className="skills-table-head">
                      <span>COMPETENCY</span>
                      <span>PROFICIENCY</span>
                      <span>VERIFICATION</span>
                    </div>

                    {skills.map((s) => {
                      const state = studentSkills[s.id] || { level: 0, is_verified: false };
                      return (
                        <div className="skill-input-row" key={s.id}>
                          <div className="skill-info">
                            <strong>{s.name}</strong>
                            <span className="category-pill">{s.category}</span>
                          </div>

                          <div className="skill-level-select">
                            <select
                              id={`select-level-${s.id}`}
                              aria-label={`Skill ${s.name} level`}
                              value={state.level}
                              onChange={(e) => {
                                const newLvl = Number(e.target.value);
                                setStudentSkills((prev) => ({
                                  ...prev,
                                  [s.id]: {
                                    ...prev[s.id],
                                    level: newLvl,
                                    is_verified: newLvl === 0 ? false : state.is_verified,
                                  },
                                }));
                              }}
                            >
                              <option value={0}>0 — None</option>
                              <option value={1}>1 — Basic</option>
                              <option value={2}>2 — Intermediate</option>
                              <option value={3}>3 — Advanced</option>
                            </select>
                          </div>

                          <div className="skill-verify-toggle">
                            <label className="toggle-label">
                              <input
                                id={`check-verify-${s.id}`}
                                type="checkbox"
                                disabled={state.level === 0}
                                checked={state.is_verified && state.level > 0}
                                onChange={(e) => {
                                  setStudentSkills((prev) => ({
                                    ...prev,
                                    [s.id]: {
                                      ...prev[s.id],
                                      is_verified: e.target.checked,
                                    },
                                  }));
                                }}
                              />
                              <span
                                className={`status-badge ${state.level === 0
                                    ? 'unknown'
                                    : state.is_verified
                                      ? 'verified'
                                      : 'self-reported'
                                  }`}
                              >
                                {state.level === 0
                                  ? '⚪ Not declared'
                                  : state.is_verified
                                    ? '🛡️ Verified'
                                    : '✍️ Self-reported'}
                              </span>
                            </label>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Portfolio Evidence Drawer */}
                  {evidenceList.length > 0 && (
                    <div className="evidence-drawer">
                      <div className="evidence-drawer-header">
                        <span>PORTFOLIO EVIDENCE ({evidenceList.length})</span>
                        <span style={{ fontSize: '10px', color: '#64748b' }}>
                          Verified project artifacts & coursework
                        </span>
                      </div>
                      {evidenceList.map((ev) => (
                        <div key={ev.id} className="evidence-item-row">
                          <div>
                            {ev.url ? (
                              <a
                                href={ev.url}
                                target="_blank"
                                rel="noreferrer"
                                className="evidence-title-link"
                              >
                                {ev.title} ↗
                              </a>
                            ) : (
                              <strong>{ev.title}</strong>
                            )}
                            <span style={{ marginLeft: '8px', color: '#64748b', fontSize: '11px' }}>
                              ({ev.skill_name} • {ev.evidence_type})
                            </span>
                          </div>
                          <span className={`evidence-badge ${ev.verified_by_staff ? 'verified' : ''}`}>
                            {ev.verified_by_staff ? '🛡️ Verified' : 'Project'}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Generate Button */}
                  <button
                    id="btn-generate-plan"
                    className="generate-btn"
                    onClick={generateLearningPath}
                    disabled={planLoading}
                  >
                    {planLoading
                      ? 'Executing C++20 Topological Planner…'
                      : '⚡ Generate Learning Path with C++20 Engine →'}
                  </button>


                  {planError && (
                    <div id="plan-error-banner" className="error-banner" role="alert">
                      ⚠️ {planError}
                    </div>
                  )}
                </div>
              </div>

              {/* ======================================================== */}
              {/* LEARNING PLAN OUTPUT SECTION                            */}
              {/* ======================================================== */}
              {plan && (
                <section id="plan-results-section" className="plan-results-section">
                  <div className="results-hero-card">
                    <div className="results-hero-left">
                      <div className="eyebrow-accent">C++20 ENGINE LEARNING PLAN</div>
                      <h2 className="results-title">
                        {plan.achievable ? 'Learning Plan Achievable' : 'Dependency Conflict'}
                      </h2>
                      <p className="results-subtitle">{plan.message}</p>
                      <div className="chips-row">
                        <span className="metric-chip">
                          <b>{plan.stages.length}</b> Learning Stages
                        </span>
                        <span className="metric-chip">
                          <b>{plan.missing_skills.length}</b> Missing Skills
                        </span>
                        <span className="metric-chip">
                          <b>{plan.prerequisite_closure.length}</b> Transitive Prerequisites
                        </span>
                        <span className="metric-chip highlight">
                          ⏱️ Total Effort:{' '}
                          <b>
                            {plan.total_estimated_effort.min_hours} –{' '}
                            {plan.total_estimated_effort.max_hours} hrs
                          </b>
                        </span>
                      </div>
                    </div>

                    <div className="results-hero-right">
                      <button
                        id="btn-adopt-career-mission"
                        className="btn-adopt-mission-cta"
                        onClick={adoptPlanAsCareerMission}
                        title="Persist this generated learning path as your active Career Mission"
                      >
                        🎯 Adopt as Career Mission
                      </button>
                      <div className="view-toggle">
                        <button
                          id="btn-view-stages"
                          className={viewMode === 'stages' ? 'active' : ''}
                          onClick={() => setViewMode('stages')}
                        >
                          Ordered Stages
                        </button>
                        <button
                          id="btn-view-graph"
                          className={viewMode === 'graph' ? 'active' : ''}
                          onClick={() => setViewMode('graph')}
                        >
                          Interactive Graph (DAG)
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Mode A: Ordered Learning Stages */}
                  {viewMode === 'stages' && (
                    <div className="stages-container">
                      {plan.stages.length === 0 ? (
                        <div className="fully-qualified-card">
                          <span className="celebration-icon">🎉</span>
                          <h3>You Already Meet All Requirements!</h3>
                          <p>
                            Your declared and verified competencies satisfy all direct target skills
                            and transitive prerequisites for this internship role.
                          </p>
                        </div>
                      ) : (
                        plan.stages.map((stage) => (
                          <div
                            id={`stage-card-${stage.stage_number}`}
                            key={stage.stage_number}
                            className="stage-card"
                          >
                            <div className="stage-card-header">
                              <div>
                                <span className="stage-badge">Stage {stage.stage_number}</span>
                                <h3 className="stage-title">{stage.stage_title}</h3>
                              </div>
                              <div className="stage-effort-pill">
                                Est. Effort: <b>{stage.stage_effort.min_hours} – {stage.stage_effort.max_hours} hrs</b>
                              </div>
                            </div>

                            <p className="stage-parallel-note">
                              ⚡ <i>Concurrency Opportunity:</i> Competencies within this stage have
                              no interdependencies and can be studied in parallel.
                            </p>

                            <div className="upgrades-grid">
                              {stage.skills.map((upgrade) => (
                                <div
                                  id={`upgrade-card-${upgrade.skill_id}`}
                                  key={upgrade.skill_id}
                                  className="upgrade-card"
                                >
                                  <div className="upgrade-card-top">
                                    <strong className="upgrade-name">{upgrade.skill_name}</strong>
                                    <span className="category-pill">{upgrade.category}</span>
                                  </div>

                                  <div className="level-progression-bar">
                                    <span>Level {upgrade.current_level}</span>
                                    <span className="arrow-progression">➔</span>
                                    <span className="target-level-pill">
                                      Target Level {upgrade.target_level}
                                    </span>
                                    <span className="delta-badge">+{upgrade.level_delta} lvl</span>
                                  </div>

                                  <div className="rationale-box">
                                    <span className="rationale-label">Dependency Rationale:</span>
                                    <p className="rationale-text">{upgrade.rationale}</p>
                                  </div>

                                  <div className="upgrade-footer">
                                    <span className="effort-badge">
                                      ⏱️ {upgrade.estimated_effort.min_hours} –{' '}
                                      {upgrade.estimated_effort.max_hours} hrs
                                    </span>
                                    <span
                                      className={`verification-tag ${upgrade.is_verified ? 'verified' : 'unverified'
                                        }`}
                                    >
                                      {upgrade.is_verified ? '🛡️ Verified Base' : '✍️ Needs Study/Exam'}
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {/* Mode B: Interactive Graph (DAG) View */}
                  {viewMode === 'graph' && (
                    <div id="graph-view-panel" className="graph-view-panel">
                      <div className="graph-header">
                        <h3>Interactive Skill Dependency Graph (Curriculum DAG)</h3>
                        <p>
                          Directed edges A ➔ B indicate prerequisite dependencies. Nodes are
                          partitioned into topological stages computed by Kahn's algorithm.
                        </p>
                      </div>

                      <div className="dag-canvas">
                        <svg className="dag-svg" viewBox="0 0 900 480" width="100%" height="450">
                          <defs>
                            <marker
                              id="arrowhead"
                              markerWidth="8"
                              markerHeight="6"
                              refX="7"
                              refY="3"
                              orient="auto"
                            >
                              <polygon points="0 0, 8 3, 0 6" fill="#507096" />
                            </marker>
                            <marker
                              id="arrowhead-active"
                              markerWidth="8"
                              markerHeight="6"
                              refX="7"
                              refY="3"
                              orient="auto"
                            >
                              <polygon points="0 0, 8 3, 0 6" fill="#3288ff" />
                            </marker>
                          </defs>

                          {/* Directed Edges */}
                          {/* 1 -> 2, 1 -> 3 */}
                          <line x1="140" y1="80" x2="310" y2="70" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead-active)" />
                          <line x1="140" y1="80" x2="310" y2="160" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead-active)" />
                          {/* 2 -> 4, 9 -> 4 */}
                          <line x1="450" y1="70" x2="570" y2="90" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead-active)" />
                          <line x1="140" y1="360" x2="570" y2="110" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead-active)" />
                          {/* 3 -> 5 */}
                          <line x1="450" y1="160" x2="570" y2="180" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead-active)" />
                          {/* 4 -> 6, 5 -> 6 */}
                          <line x1="710" y1="100" x2="790" y2="140" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead-active)" />
                          <line x1="710" y1="180" x2="790" y2="160" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead-active)" />
                          {/* 7 -> 8 -> 10 */}
                          <line x1="140" y1="260" x2="310" y2="260" stroke="#507096" strokeWidth="1.5" markerEnd="url(#arrowhead)" />
                          <line x1="450" y1="260" x2="570" y2="260" stroke="#507096" strokeWidth="1.5" markerEnd="url(#arrowhead)" />

                          {/* Nodes */}
                          {/* Node 1: Foundations */}
                          <g
                            className="dag-node"
                            transform="translate(40, 50)"
                            onClick={() => setSelectedSkillNode(skills.find((s) => s.id === 1) || null)}
                          >
                            <rect width="120" height="60" rx="8" fill="#1b3054" stroke="#4886e0" strokeWidth="2" />
                            <text x="60" y="28" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">Foundations (1)</text>
                            <text x="60" y="44" fill="#8cb7f5" fontSize="9" textAnchor="middle">Core Logic</text>
                          </g>

                          {/* Node 2: Python */}
                          <g
                            className="dag-node"
                            transform="translate(320, 40)"
                            onClick={() => setSelectedSkillNode(skills.find((s) => s.id === 2) || null)}
                          >
                            <rect width="130" height="60" rx="8" fill="#1b3054" stroke="#4886e0" strokeWidth="2" />
                            <text x="65" y="28" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">Python (2)</text>
                            <text x="65" y="44" fill="#8cb7f5" fontSize="9" textAnchor="middle">Languages</text>
                          </g>

                          {/* Node 3: C++ */}
                          <g
                            className="dag-node"
                            transform="translate(320, 130)"
                            onClick={() => setSelectedSkillNode(skills.find((s) => s.id === 3) || null)}
                          >
                            <rect width="130" height="60" rx="8" fill="#203a66" stroke="#5ba0ff" strokeWidth="2" />
                            <text x="65" y="28" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">C++ Systems (3)</text>
                            <text x="65" y="44" fill="#ffd479" fontSize="9" fontWeight="700" textAnchor="middle">Stage 1</text>
                          </g>

                          {/* Node 9: SQL */}
                          <g
                            className="dag-node"
                            transform="translate(40, 330)"
                            onClick={() => setSelectedSkillNode(skills.find((s) => s.id === 9) || null)}
                          >
                            <rect width="130" height="60" rx="8" fill="#203a66" stroke="#5ba0ff" strokeWidth="2" />
                            <text x="65" y="28" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">SQL & DBs (9)</text>
                            <text x="65" y="44" fill="#ffd479" fontSize="9" fontWeight="700" textAnchor="middle">Stage 1</text>
                          </g>

                          {/* Node 4: FastAPI */}
                          <g
                            className="dag-node"
                            transform="translate(580, 60)"
                            onClick={() => setSelectedSkillNode(skills.find((s) => s.id === 4) || null)}
                          >
                            <rect width="130" height="60" rx="8" fill="#203a66" stroke="#5ba0ff" strokeWidth="2" />
                            <text x="65" y="28" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">Backend APIs (4)</text>
                            <text x="65" y="44" fill="#ffd479" fontSize="9" fontWeight="700" textAnchor="middle">Stage 2</text>
                          </g>

                          {/* Node 5: DSA */}
                          <g
                            className="dag-node"
                            transform="translate(580, 150)"
                            onClick={() => setSelectedSkillNode(skills.find((s) => s.id === 5) || null)}
                          >
                            <rect width="130" height="60" rx="8" fill="#203a66" stroke="#5ba0ff" strokeWidth="2" />
                            <text x="65" y="28" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">Algorithms (5)</text>
                            <text x="65" y="44" fill="#ffd479" fontSize="9" fontWeight="700" textAnchor="middle">Stage 2</text>
                          </g>

                          {/* Node 6: Distributed Systems (Target) */}
                          <g
                            className="dag-node"
                            transform="translate(770, 120)"
                            onClick={() => setSelectedSkillNode(skills.find((s) => s.id === 6) || null)}
                          >
                            <rect width="120" height="65" rx="8" fill="#0f448c" stroke="#62aaff" strokeWidth="3" />
                            <text x="60" y="28" fill="#fff" fontSize="11" fontWeight="800" textAnchor="middle">Dist. Systems (6)</text>
                            <text x="60" y="44" fill="#75ffb3" fontSize="9" fontWeight="700" textAnchor="middle">🎯 TARGET (Stage 3)</text>
                          </g>

                          {/* Node 7: Git & Linux */}
                          <g
                            className="dag-node"
                            transform="translate(40, 230)"
                            onClick={() => setSelectedSkillNode(skills.find((s) => s.id === 7) || null)}
                          >
                            <rect width="120" height="60" rx="8" fill="#142138" stroke="#364966" strokeWidth="1.5" />
                            <text x="60" y="28" fill="#cad5e5" fontSize="11" textAnchor="middle">Git & Linux (7)</text>
                            <text x="60" y="44" fill="#7b91b0" fontSize="9" textAnchor="middle">Tools</text>
                          </g>

                          {/* Node 8: Docker */}
                          <g
                            className="dag-node"
                            transform="translate(320, 230)"
                            onClick={() => setSelectedSkillNode(skills.find((s) => s.id === 8) || null)}
                          >
                            <rect width="120" height="60" rx="8" fill="#142138" stroke="#364966" strokeWidth="1.5" />
                            <text x="60" y="28" fill="#cad5e5" fontSize="11" textAnchor="middle">Docker (8)</text>
                            <text x="60" y="44" fill="#7b91b0" fontSize="9" textAnchor="middle">DevOps</text>
                          </g>

                          {/* Node 10: Kubernetes */}
                          <g
                            className="dag-node"
                            transform="translate(580, 230)"
                            onClick={() => setSelectedSkillNode(skills.find((s) => s.id === 10) || null)}
                          >
                            <rect width="120" height="60" rx="8" fill="#142138" stroke="#364966" strokeWidth="1.5" />
                            <text x="60" y="28" fill="#cad5e5" fontSize="11" textAnchor="middle">Cloud & K8s (10)</text>
                            <text x="60" y="44" fill="#7b91b0" fontSize="9" textAnchor="middle">DevOps</text>
                          </g>
                        </svg>
                      </div>

                      {selectedSkillNode && (
                        <div className="node-detail-card">
                          <div className="node-detail-header">
                            <strong>{selectedSkillNode.name}</strong>
                            <span className="category-pill">{selectedSkillNode.category}</span>
                          </div>
                          <p className="node-detail-desc">{selectedSkillNode.description}</p>
                          <div className="node-detail-meta">
                            <span>
                              <b>Direct Prerequisites:</b>{' '}
                              {selectedSkillNode.prerequisites.length > 0
                                ? selectedSkillNode.prerequisites.map((p) => `#${p}`).join(', ')
                                : 'None (Root Node)'}
                            </span>
                            <span>
                              <b>Unlocks:</b>{' '}
                              {selectedSkillNode.unlocked_skills.length > 0
                                ? selectedSkillNode.unlocked_skills.map((u) => `#${u}`).join(', ')
                                : 'Leaf / Capstone'}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </section>
              )}

              {/* ======================================================== */}
              {/* PRESENTER-ONLY DSA VISIBILITY INSPECTOR (PART D)        */}
              {/* ======================================================== */}
              {showDsaInspector && (
                <section id="dsa-inspector-panel" className="dsa-inspector-panel">
                  <div className="dsa-inspector-header">
                    <div>
                      <div className="eyebrow-dsa">PRESENTER MODE • DSA VISIBILITY</div>
                      <h2>Custom C++20 Data Structure & Algorithm Architecture</h2>
                      <p>
                        Real recorded execution metrics and algorithmic foundations running in the C++ engine.
                      </p>
                    </div>
                    <span className="dsa-badge">LIVE METRICS ENABLED</span>
                  </div>

                  {plan?.algorithm_trace ? (
                    <div className="dsa-metrics-grid">
                      <div className="dsa-metric-card">
                        <span className="dsa-metric-label">Graph Structure</span>
                        <strong className="dsa-metric-val">
                          {plan.algorithm_trace.graph_node_count} nodes / {plan.algorithm_trace.graph_edge_count} edges
                        </strong>
                        <small>Adjacency lists in custom HashTable</small>
                      </div>
                      <div className="dsa-metric-card">
                        <span className="dsa-metric-label">Prerequisite Closure</span>
                        <strong className="dsa-metric-val">
                          {plan.algorithm_trace.prerequisite_closure_nodes_visited} visited
                        </strong>
                        <small>Reverse BFS via CircularQueue</small>
                      </div>
                      <div className="dsa-metric-card">
                        <span className="dsa-metric-label">Kahn Queue Ops</span>
                        <strong className="dsa-metric-val">
                          {plan.algorithm_trace.kahn_queue_enqueues} enqueues / {plan.algorithm_trace.kahn_queue_dequeues} dequeues
                        </strong>
                        <small>In-degree zero queue tracking</small>
                      </div>
                      <div className="dsa-metric-card">
                        <span className="dsa-metric-label">Engine Latency</span>
                        <strong className="dsa-metric-val highlight">
                          {plan.algorithm_trace.execution_time_microseconds.toFixed(2)} µs
                        </strong>
                        <small>Measured via std::chrono</small>
                      </div>
                    </div>
                  ) : (
                    <div className="dsa-metrics-placeholder">
                      Run "Generate Learning Path" to capture live C++ execution traces.
                    </div>
                  )}

                  <div className="dsa-explainer-cards">
                    <div className="explainer-card">
                      <div className="explainer-title">
                        <span>1</span>
                        <h4>Directed Graph & Custom HashTable</h4>
                      </div>
                      <p>
                        The curriculum graph is modeled as directed adjacency lists stored inside our
                        custom <code>HashTable&lt;int, DynamicArray&lt;int&gt;&gt;</code>. Edges{' '}
                        <code>A ➔ B</code> represent strict prerequisites. Storing both forward
                        and reverse adjacencies enables $O(1)$ expected degree calculation and
                        bidirectional path checks.
                      </p>
                    </div>

                    <div className="explainer-card">
                      <div className="explainer-title">
                        <span>2</span>
                        <h4>Reverse Prerequisite Closure in O(V + E)</h4>
                      </div>
                      <p>
                        To discover all missing prerequisites without recursion stack limits, the
                        engine conducts a reverse BFS traversal using our custom{' '}
                        <code>CircularQueue&lt;int&gt;</code>. A visited set guarantees that shared
                        prerequisites (diamond dependencies) are visited and billed exactly once.
                      </p>
                    </div>

                    <div className="explainer-card">
                      <div className="explainer-title">
                        <span>3</span>
                        <h4>Kahn's Layered Topological Sorting</h4>
                      </div>
                      <p>
                        Rather than producing a linear sequence, our planner uses a level-by-level
                        Kahn's algorithm queue peeling strategy. Vertices whose prerequisites are
                        satisfied form discrete, parallelizable <b>Stages</b>. If an edge cycle
                        existed, 3-color DFS path reconstruction extracts the exact loop.
                      </p>
                    </div>

                    <div className="explainer-card">
                      <div className="explainer-title">
                        <span>4</span>
                        <h4>DynamicArray Contiguity & Memory Safety</h4>
                      </div>
                      <p>
                        All queues, stacks, and stage lists build upon our custom{' '}
                        <code>DynamicArray&lt;T&gt;</code>, offering strong exception safety with
                        amortized $O(1)$ growth, RAII deallocation, and cache-friendly sequential
                        memory layout.
                      </p>
                    </div>
                  </div>
                </section>
              )}
            </div>
          )}

          {/* ======================================================== */}
          {/* TAB 2: PHASE 1 MATCHING PREVIEW (REGRESSION PRESERVED)   */}
          {/* ======================================================== */}
          {activeTab === 'match' && (
            <div className="match-container">
              <div className="eyebrow">PHASE 1 MATCHING ENGINE</div>
              <h1>Requirement Coverage Calculator</h1>
              <p className="lede">
                Our original Phase 1 integration: edit a student's declared skill levels and
                execute the C++20 matching engine to calculate weighted requirements coverage.
              </p>

              <section className="hero-grid">
                <div className="panel form-panel">
                  <div className="panel-header">
                    <div>
                      <h2>Sample skill profile</h2>
                      <p>Illustrative Embedded Systems role — not a verified posting.</p>
                    </div>
                    <span className="mini-icon">⌘</span>
                  </div>
                  <div className="skills-head">
                    <span>SKILL</span>
                    <span>YOUR LEVEL</span>
                    <span>REQUIRED</span>
                  </div>
                  {phase1Skills.map((skill, index) => (
                    <div className="skill-row" key={skill.name}>
                      <div>
                        <strong>{skill.name}</strong>
                        <span className="metadata">
                          {skill.mandatory ? 'Mandatory' : 'Preferred'}
                        </span>
                      </div>
                      <select
                        aria-label={`${skill.name} student level`}
                        value={matchLevels[index]}
                        onChange={(e) =>
                          setMatchLevels((old) =>
                            old.map((v, i) => (i === index ? Number(e.target.value) : v))
                          )
                        }
                      >
                        <option value={0}>0 — Not declared</option>
                        <option value={1}>1 — Basic</option>
                        <option value={2}>2 — Intermediate</option>
                        <option value={3}>3 — Advanced</option>
                      </select>
                      <span className="required-tag">Level {skill.target}</span>
                    </div>
                  ))}
                  <button onClick={analyzeMatch} disabled={matchWorking}>
                    {matchWorking ? 'Calculating…' : 'Recalculate with C++ Engine →'}
                  </button>
                  {matchError && (
                    <p className="error" role="alert">
                      {matchError}
                    </p>
                  )}
                  <p className="footnote">
                    Self-reported levels are illustrative. This number is not a hiring probability.
                  </p>
                </div>

                <div className="panel result-panel">
                  <div className="eyebrow">LIVE ENGINE OUTPUT</div>
                  <div className="score">
                    {matchResult ? `${matchResult.coverage_percent.toFixed(2)}%` : '—'}
                  </div>
                  <p className="result-label">Requirement coverage</p>
                  <div className="progress-track">
                    <div
                      className="progress-fill"
                      style={{ width: `${matchResult?.coverage_percent ?? 0}%` }}
                    />
                  </div>
                  <div className="stat-divider" />
                  <div className="stat">
                    <span>Earned points</span>
                    <strong>
                      {matchResult
                        ? `${matchResult.earned_points} / ${matchResult.max_points}`
                        : '—'}
                    </strong>
                  </div>
                  <div className="stat">
                    <span>Missing mandatory requirements</span>
                    <strong>{matchResult?.missing_mandatory ?? '—'}</strong>
                  </div>
                  <div className="stat">
                    <span>Mandatory levels met</span>
                    <strong>
                      {matchResult
                        ? matchResult.mandatory_requirements_met
                          ? 'Yes'
                          : 'Not yet'
                        : '—'}
                    </strong>
                  </div>
                  <div className="engine-note">
                    ✓ Browser → FastAPI → C++20 → FastAPI → Browser
                  </div>
                </div>
              </section>
            </div>
          )}

          <footer>InternPath AI · Curriculum Graph & Learning Path Engine · Phase 3.1</footer>
        </div>
      </main>
    </div>
  );
}
