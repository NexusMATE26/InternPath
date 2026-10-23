import React, { useState, useEffect, useMemo } from 'react';

export interface Skill {
  id: number;
  name: string;
  category: string;
  max_level: number;
  description: string;
}

export interface StudentSkillState {
  level: number;
  verified_level?: number;
  is_verified: boolean;
  verification_source?: string;
}

export interface EvidenceItem {
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

export interface RoleItem {
  role_id: string;
  title: string;
  department: string;
  location: string;
  description: string;
  requirements_count: number;
}

export interface RoleRequirementItem {
  skill_id: number;
  skill_name: string;
  required_level: number;
  mandatory: boolean;
  role_context: string;
}

export interface RoleDetailResponse {
  role_id: string;
  title: string;
  department: string;
  location: string;
  description: string;
  requirements: RoleRequirementItem[];
}

export interface MissionTask {
  id: number;
  version_id: number;
  stable_key: string;
  stage_number: number;
  stage_title: string;
  skill_id: number;
  skill_name: string;
  category: string;
  current_level: number;
  target_level: number;
  level_delta: number;
  status: string;
  is_unlocked: boolean;
  estimated_hours_min: number;
  estimated_hours_max: number;
  completion_criteria: string;
  rationale: string;
  evidence_id?: number | null;
}

export interface CareerMission {
  id: number;
  target_role_id?: string | null;
  target_role_title?: string | null;
  title: string;
  status: string;
  weekly_hours: number;
  active_version_number?: number | null;
  total_tasks: number;
  completed_tasks: number;
  in_progress_tasks: number;
  progress_percent: number;
  active_version?: {
    id: number;
    version_number: number;
    tasks: MissionTask[];
  } | null;
  pending_proposals_count: number;
  created_at?: string | null;
}

interface ReadinessViewProps {
  skills: Skill[];
  studentSkills: Record<number, StudentSkillState>;
  onSkillChange: (skillId: number, level: number) => void;
  studentName: string;
  weeklyHours: number;
  onWeeklyHoursChange: (hours: number) => void;
  evidenceList: EvidenceItem[];
  onSaveProfile: () => Promise<void>;
  saving: boolean;
  saveSuccess: boolean;
  saveError: string;
  onNavigateToRoadmap: (taskId?: number) => void;
  onNavigateToCareers?: () => void;
  selectedRoleId?: string | null;
  onSelectRole?: (roleId: string) => void;
  roles?: RoleItem[];
  activeMission?: CareerMission | null;
}

const LEVEL_LABELS: Record<number, string> = {
  0: 'None (0)',
  1: 'Foundational (1)',
  2: 'Working (2)',
  3: 'Advanced (3)',
};

export const ReadinessView: React.FC<ReadinessViewProps> = ({
  skills,
  studentSkills,
  onSkillChange,
  studentName,
  weeklyHours,
  onWeeklyHoursChange,
  evidenceList,
  onSaveProfile,
  saving,
  saveSuccess,
  saveError,
  onNavigateToRoadmap,
  onNavigateToCareers,
  selectedRoleId,
  onSelectRole,
  roles = [],
  activeMission,
}) => {
  // Current role being inspected
  const currentRoleId = selectedRoleId || (roles.length > 0 ? roles[0].role_id : 'distributed-systems-intern');
  const [roleDetail, setRoleDetail] = useState<RoleDetailResponse | null>(null);
  const [roleLoading, setRoleLoading] = useState(false);
  const [roleError, setRoleError] = useState<string | null>(null);

  // Filters
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'mandatory' | 'elective' | 'gaps' | 'with_evidence'>('all');

  // Fetch requirement specifications for the target role
  useEffect(() => {
    if (!currentRoleId) return;
    let isCancelled = false;
    setRoleLoading(true);
    setRoleError(null);

    fetch(`/v1/roles/${currentRoleId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Role '${currentRoleId}' not found (HTTP ${res.status})`);
        return res.json();
      })
      .then((data: RoleDetailResponse) => {
        if (!isCancelled) {
          setRoleDetail(data);
        }
      })
      .catch((err) => {
        if (!isCancelled) {
          console.error('Failed to load role detail for readiness:', err);
          setRoleError(err instanceof Error ? err.message : 'Failed to load role requirements');
        }
      })
      .finally(() => {
        if (!isCancelled) setRoleLoading(false);
      });

    return () => {
      isCancelled = true;
    };
  }, [currentRoleId]);

  const requirements = useMemo(() => {
    return roleDetail?.requirements || [];
  }, [roleDetail]);

  // Skill lookup helper
  const skillMetaMap = useMemo(() => {
    const map = new Map<number, Skill>();
    skills.forEach((s) => map.set(s.id, s));
    return map;
  }, [skills]);

  // Evidence grouped by skill_id
  const evidenceBySkill = useMemo(() => {
    const map = new Map<number, EvidenceItem[]>();
    evidenceList.forEach((item) => {
      const list = map.get(item.skill_id) || [];
      list.push(item);
      map.set(item.skill_id, list);
    });
    return map;
  }, [evidenceList]);

  // Tasks in active mission grouped by skill_id
  const missionTasksBySkill = useMemo(() => {
    const map = new Map<number, MissionTask[]>();
    const tasks = activeMission?.active_version?.tasks || [];
    tasks.forEach((t) => {
      const list = map.get(t.skill_id) || [];
      list.push(t);
      map.set(t.skill_id, list);
    });
    return map;
  }, [activeMission]);

  // Meaningful factual metrics
  const totalReqs = requirements.length;
  const mandatoryCount = requirements.filter((r) => r.mandatory).length;
  const electiveCount = totalReqs - mandatoryCount;

  const metReqs = requirements.filter((r) => {
    const st = studentSkills[r.skill_id];
    return (st?.level ?? 0) >= r.required_level;
  }).length;

  const gapReqs = requirements.filter((r) => {
    const st = studentSkills[r.skill_id];
    return (st?.level ?? 0) < r.required_level;
  }).length;

  const evidenceSkillsCount = requirements.filter((r) => {
    const items = evidenceBySkill.get(r.skill_id);
    return items && items.length > 0;
  }).length;

  const coveragePercent = totalReqs > 0 ? Math.round((metReqs / totalReqs) * 100) : 0;

  // Categories list
  const availableCategories = useMemo(() => {
    const cats = new Set<string>();
    requirements.forEach((req) => {
      const sk = skillMetaMap.get(req.skill_id);
      if (sk?.category) cats.add(sk.category);
    });
    return ['all', ...Array.from(cats)];
  }, [requirements, skillMetaMap]);

  // Filtered requirements
  const filteredRequirements = useMemo(() => {
    return requirements.filter((req) => {
      const sk = skillMetaMap.get(req.skill_id);
      const cat = sk?.category || '';
      if (categoryFilter !== 'all' && cat !== categoryFilter) return false;

      const studentLevel = studentSkills[req.skill_id]?.level ?? 0;
      const isMet = studentLevel >= req.required_level;
      const hasEvidence = (evidenceBySkill.get(req.skill_id)?.length || 0) > 0;

      if (statusFilter === 'mandatory' && !req.mandatory) return false;
      if (statusFilter === 'elective' && req.mandatory) return false;
      if (statusFilter === 'gaps' && isMet) return false;
      if (statusFilter === 'with_evidence' && !hasEvidence) return false;

      return true;
    });
  }, [requirements, skillMetaMap, categoryFilter, statusFilter, studentSkills, evidenceBySkill]);

  const targetRoleObj = roles.find((r) => r.role_id === currentRoleId) || roleDetail;

  return (
    <div className="readiness-view-container" id="readiness-view">
      {/* View Header */}
      <div className="view-header">
        <div className="eyebrow">READINESS PROOF MAP & COMPETENCY INTEGRITY</div>
        <h1>Demonstrated Skills & Evidence Map</h1>
        <p className="lede">
          Readiness is proof-grounded, not an arbitrary employment probability. Compare target internship
          requirements against your declared proficiency, inspect verified baseline competence, and review
          linked portfolio artifacts.
        </p>
      </div>

      {/* Section A — Target Role Context & Honest Provenance */}
      <div className="readiness-target-role-card panel" id="readiness-target-role-panel">
        <div className="target-role-header-row">
          <div>
            <span className="section-subtag">TARGET INTERNSHIP ROLE</span>
            <div className="role-title-select-row">
              <h2 className="target-role-title">{targetRoleObj?.title || currentRoleId}</h2>
              {roles.length > 1 && onSelectRole && (
                <div className="role-selector-control">
                  <label htmlFor="select-target-role">Switch Target Role:</label>
                  <select
                    id="select-target-role"
                    className="select-role-dropdown"
                    value={currentRoleId}
                    onChange={(e) => onSelectRole(e.target.value)}
                  >
                    {roles.map((r) => (
                      <option key={r.role_id} value={r.role_id}>
                        {r.title}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {onNavigateToCareers && (
                <button
                  type="button"
                  className="btn-secondary btn-small"
                  onClick={onNavigateToCareers}
                  style={{ marginLeft: '8px' }}
                >
                  Explore Careers Catalogue →
                </button>
              )}
            </div>
            <div className="role-meta-info">
              <span>🏢 {targetRoleObj?.department || 'Engineering'}</span>
              <span>•</span>
              <span>📍 {targetRoleObj?.location || 'Colombo, Sri Lanka'}</span>
            </div>
          </div>
          <span className="demo-role-badge">DEMONSTRATION BENCHMARK</span>
        </div>

        {/* Source / Demo Status Notice */}
        <div className="demo-notice-banner" style={{ marginTop: '12px' }}>
          <span>
            ℹ <b>Demonstration Role — Requirements are Illustrative:</b> Competency requirements shown
            are curriculum-grounded engineering benchmarks developed for undergraduate Embedded Systems and
            IoT internships. Sourced, verified employer requirement provenance will arrive in <b>Refinement R3</b>.
          </span>
        </div>

        <p className="methodology-explainer">
          Requirements define canonical 1–3 proficiency expectations categorized as <b>Mandatory Core</b> (must be
          satisfied) and <b>Preferred Elective</b> (valuable specialization). Prerequisites are evaluated using
          C++ Kahn's topological sort.
        </p>
      </div>

      {/* Profile & Capacity Bar */}
      <div className="profile-persistence-bar panel">
        <div className="profile-info">
          <span className="profile-tag">STUDENT WORKSPACE</span>
          <strong>{studentName}</strong>
          <span className="capacity-control">
            • Weekly Study Allocation:
            <select
              id="select-weekly-hours"
              className="select-hours"
              value={weeklyHours}
              onChange={(e) => onWeeklyHoursChange(Number(e.target.value))}
            >
              <option value={5}>5 hrs/week (Steady)</option>
              <option value={10}>10 hrs/week (Moderate)</option>
              <option value={15}>15 hrs/week (Dedicated)</option>
              <option value={20}>20 hrs/week (Intensive)</option>
              <option value={30}>30 hrs/week (Sprint)</option>
            </select>
          </span>
        </div>
        <div className="profile-actions">
          <button
            type="button"
            id="btn-save-readiness-profile"
            className="btn-primary"
            onClick={onSaveProfile}
            disabled={saving}
          >
            {saving ? 'Saving…' : '💾 Save Self-Assessment'}
          </button>
          {saveSuccess && <span className="save-status-msg success">✓ Saved successfully</span>}
          {saveError && <span className="save-status-msg error">⚠️ {saveError}</span>}
        </div>
      </div>

      {/* Honest Boundary Notice */}
      <div className="verification-boundary-notice">
        <span>
          🛡 <b>Competency Integrity Principle:</b> Rating proficiency here updates your self-assessed declared level.
          Self-assessment does not grant, raise, or alter independently verified competence. Genuine verified badges require
          external assessment authority or baseline provenance.
        </span>
      </div>

      {/* Section B — Simple Readiness Overview Metrics */}
      <div className="readiness-summary-grid">
        <div className="panel summary-pill-card" id="metric-total-requirements">
          <span className="summary-icon">◈</span>
          <div>
            <div className="summary-val">{totalReqs} Competencies</div>
            <small>{mandatoryCount} Core Mandatory • {electiveCount} Elective</small>
          </div>
        </div>

        <div className="panel summary-pill-card highlight-met" id="metric-requirements-met">
          <span className="summary-icon">✓</span>
          <div>
            <div className="summary-val">{metReqs} / {totalReqs} Met</div>
            <small>Declared level meets requirement</small>
          </div>
        </div>

        <div className="panel summary-pill-card highlight-evidence" id="metric-linked-evidence">
          <span className="summary-icon">📎</span>
          <div>
            <div className="summary-val">{evidenceSkillsCount} Supported</div>
            <small>{evidenceList.length} total artifacts linked</small>
          </div>
        </div>

        <div className="panel summary-pill-card highlight-gaps" id="metric-skill-gaps">
          <span className="summary-icon">⚠️</span>
          <div>
            <div className="summary-val">{gapReqs} Remaining Gaps</div>
            <small>Competencies needing development</small>
          </div>
        </div>
      </div>

      {/* Coverage Metric Banner (Factual, not employment probability) */}
      <div className="coverage-metric-banner panel">
        <div className="coverage-metric-left">
          <div className="coverage-metric-label">DECLARED REQUIREMENT COVERAGE</div>
          <div className="coverage-percentage-val">
            <b>{coveragePercent}%</b> of role requirements satisfied by self-report
          </div>
          <div className="coverage-progress-track">
            <div className="coverage-progress-bar" style={{ width: `${Math.min(100, coveragePercent)}%` }} />
          </div>
        </div>
        <div className="coverage-metric-disclaimer">
          <small>
            <b>Metric definition:</b> Factual percentage of target competencies where declared proficiency meets or
            exceeds the required level. <b>Not an employment probability or hiring guarantee.</b>
          </small>
        </div>
      </div>

      {/* Filter Row */}
      <div className="readiness-filter-bar">
        {/* Category Chips */}
        <div className="category-filter-chips">
          <span className="filter-label">Category:</span>
          {availableCategories.map((cat) => (
            <button
              key={cat}
              className={`filter-chip ${categoryFilter === cat ? 'active' : ''}`}
              onClick={() => setCategoryFilter(cat)}
            >
              {cat === 'all' ? 'ALL CATEGORIES' : cat.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Status Filter */}
        <div className="status-filter-pills">
          <span className="filter-label">Filter:</span>
          <button
            className={`filter-chip ${statusFilter === 'all' ? 'active' : ''}`}
            onClick={() => setStatusFilter('all')}
          >
            All ({requirements.length})
          </button>
          <button
            className={`filter-chip ${statusFilter === 'mandatory' ? 'active' : ''}`}
            onClick={() => setStatusFilter('mandatory')}
          >
            ★ Core ({mandatoryCount})
          </button>
          <button
            className={`filter-chip ${statusFilter === 'gaps' ? 'active' : ''}`}
            onClick={() => setStatusFilter('gaps')}
          >
            ⚠️ Gaps ({gapReqs})
          </button>
          <button
            className={`filter-chip ${statusFilter === 'with_evidence' ? 'active' : ''}`}
            onClick={() => setStatusFilter('with_evidence')}
          >
            📎 With Evidence ({evidenceSkillsCount})
          </button>
        </div>
      </div>

      {/* Section C — Requirement-to-Evidence Map */}
      <div className="requirements-proof-map-section">
        <div className="section-header-row">
          <div>
            <h3>Competency Requirement-to-Evidence Map ({filteredRequirements.length})</h3>
            <p>Compare requirements, update declared levels, and inspect supporting evidence.</p>
          </div>
          {gapReqs > 0 && (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => onNavigateToRoadmap()}
            >
              Open Roadmap to Plan Gaps →
            </button>
          )}
        </div>

        {roleLoading && (
          <div className="loading-state panel">
            <p>Loading competency requirements for {currentRoleId}…</p>
          </div>
        )}

        {roleError && (
          <div className="error-state panel">
            <p>⚠️ {roleError}</p>
          </div>
        )}

        {!roleLoading && !roleError && filteredRequirements.length === 0 && (
          <div className="empty-state panel">
            <p>No requirements match your active filter selection.</p>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setCategoryFilter('all');
                setStatusFilter('all');
              }}
            >
              Reset Filters
            </button>
          </div>
        )}

        <div className="requirements-cards-grid">
          {filteredRequirements.map((req) => {
            const studentSkill = studentSkills[req.skill_id] || { level: 0, is_verified: false };
            const declaredLvl = studentSkill.level ?? 0;
            const isVerified = studentSkill.is_verified;
            const verifiedLvl = studentSkill.verified_level ?? 0;
            const verSource = studentSkill.verification_source || (isVerified ? 'curated_demo' : 'unverified');
            const isMet = declaredLvl >= req.required_level;
            const gap = Math.max(0, req.required_level - declaredLvl);
            const skillMeta = skillMetaMap.get(req.skill_id);
            const linkedArtifacts = evidenceBySkill.get(req.skill_id) || [];
            const missionTasks = missionTasksBySkill.get(req.skill_id) || [];

            // Find relevant next mission task
            const inProgressTask = missionTasks.find((t) => t.status === 'in_progress');
            const unlockedTask = missionTasks.find((t) => t.status === 'not_started' && t.is_unlocked);
            const completedTask = missionTasks.find((t) => t.status === 'completed');
            const relevantTask = inProgressTask || unlockedTask;

            return (
              <div
                key={req.skill_id}
                className={`requirement-proof-card panel ${isMet ? 'status-met' : 'status-gap'}`}
                id={`readiness-requirement-${req.skill_id}`}
              >
                {/* Card Header */}
                <div className="req-card-topbar">
                  <div className="req-card-title-group">
                    <strong className="req-skill-name">{req.skill_name}</strong>
                    <span className="skill-category-badge">{skillMeta?.category || 'Engineering'}</span>
                  </div>
                  <div className="req-card-badges">
                    {req.mandatory ? (
                      <span className="badge-core-mandatory">★ Mandatory Core</span>
                    ) : (
                      <span className="badge-preferred-elective">✦ Preferred Elective</span>
                    )}
                  </div>
                </div>

                {/* Role Context */}
                <p className="req-context-text">
                  {req.role_context || 'Essential domain competency for internship execution.'}
                </p>

                {/* Level Comparison & Status Grid */}
                <div className="comparison-metric-grid">
                  <div className="comparison-metric-item">
                    <span className="cmp-label">Target Required</span>
                    <strong className="cmp-val target-lvl">
                      Level {req.required_level}
                    </strong>
                    <small>{LEVEL_LABELS[req.required_level]}</small>
                  </div>

                  <div className="comparison-metric-item">
                    <span className="cmp-label">Your Declared Level</span>
                    <strong className="cmp-val declared-lvl">
                      Level {declaredLvl}
                    </strong>
                    <small>{LEVEL_LABELS[declaredLvl]}</small>
                  </div>

                  <div className="comparison-metric-item">
                    <span className="cmp-label">Requirement Gap</span>
                    {isMet ? (
                      <strong className="cmp-val gap-met">✓ Requirement Met</strong>
                    ) : (
                      <strong className="cmp-val gap-pending">
                        +{gap} Level{gap > 1 ? 's' : ''} Needed
                      </strong>
                    )}
                    <small>{isMet ? 'Meets role threshold' : 'Skill gap present'}</small>
                  </div>

                  <div className="comparison-metric-item">
                    <span className="cmp-label">Verification Provenance</span>
                    {isVerified ? (
                      <strong className="cmp-val verified-tag">
                        🛡️ {verSource === 'curated_demo' ? 'Curated Demo Baseline' : 'Independently Verified'} (L{verifiedLvl})
                      </strong>
                    ) : (
                      <strong className="cmp-val unverified-tag">
                        📝 Self-Reported (Unverified)
                      </strong>
                    )}
                    <small>{isVerified ? 'Immutable baseline' : 'Awaiting independent audit'}</small>
                  </div>
                </div>

                {/* Interactive Self-Assessment Level Buttons */}
                <div className="skill-level-control">
                  <div className="control-label-row">
                    <span className="control-label">Update Declared Proficiency (Self-Assessment):</span>
                    <small className="control-hint">Canonical 0–3 Scale</small>
                  </div>
                  <div className="level-buttons-group">
                    {[0, 1, 2, 3].map((lvl) => (
                      <button
                        key={lvl}
                        type="button"
                        id={`btn-skill-${req.skill_id}-level-${lvl}`}
                        className={`level-btn ${declaredLvl === lvl ? 'active' : ''}`}
                        onClick={() => onSkillChange(req.skill_id, lvl)}
                      >
                        {LEVEL_LABELS[lvl]}
                      </button>
                    ))}
                  </div>
                  <span className="self-assessment-disclaimer">
                    ℹ Declaring level {declaredLvl} records your self-assessment. Does not create or alter independent verification.
                  </span>
                </div>

                {/* Section D — Evidence Items for this Requirement */}
                <div className="req-evidence-block">
                  <div className="evidence-block-header">
                    <span><b>Linked Evidence ({linkedArtifacts.length})</b></span>
                    <span className="mini-tag">PORTFOLIO ARTIFACTS</span>
                  </div>

                  {linkedArtifacts.length === 0 ? (
                    <div className="empty-evidence-notice">
                      <small>No portfolio artifacts or repository links attached to this skill yet.</small>
                    </div>
                  ) : (
                    <div className="linked-artifacts-list">
                      {linkedArtifacts.map((art) => (
                        <div key={art.id} className="artifact-pill-card" id={`evidence-item-${art.id}`}>
                          <div className="artifact-pill-header">
                            <div>
                              <strong className="artifact-title">{art.title}</strong>
                              <span className="artifact-type-badge">{art.evidence_type}</span>
                            </div>
                            <span className="artifact-status-tag">
                              {art.verified_by_staff ? '🛡️ Staff Reviewed' : '📎 Student Portfolio Link'}
                            </span>
                          </div>
                          {art.description && (
                            <p className="artifact-desc">{art.description}</p>
                          )}
                          <div className="artifact-link-row">
                            {art.url ? (
                              <a
                                href={art.url}
                                target="_blank"
                                rel="noreferrer"
                                className="artifact-external-link"
                              >
                                View Linked Artifact ↗
                              </a>
                            ) : (
                              <span className="text-muted">No external URL provided</span>
                            )}
                            <small className="artifact-caution">
                              Student-linked reference; not an official accreditation.
                            </small>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Section E — Next Step / Relevant Mission Action */}
                <div className="req-next-action-footer">
                  <div className="next-action-left">
                    <span className="next-action-label">NEXT LEARNING ACTION:</span>
                    {relevantTask ? (
                      <div>
                        <strong>{relevantTask.skill_name}</strong>
                        <span className="stage-pill">Stage {relevantTask.stage_number}: {relevantTask.stage_title}</span>
                        <span className={`task-status-pill ${relevantTask.status}`}>
                          {relevantTask.status === 'in_progress' ? '⚡ In Progress' : '▶ Unlocked & Ready'}
                        </span>
                      </div>
                    ) : completedTask ? (
                      <div>
                        <span className="completed-pill">✓ Milestone Completed in Active Roadmap</span>
                      </div>
                    ) : isMet ? (
                      <div className="action-text-muted">
                        Competency satisfied for this role benchmark.
                      </div>
                    ) : (
                      <div className="action-text-gap">
                        Skill gap present. Open your Roadmap to schedule learning milestones.
                      </div>
                    )}
                  </div>

                  <div className="next-action-right">
                    {relevantTask ? (
                      <button
                        type="button"
                        className="btn-primary btn-small"
                        onClick={() => onNavigateToRoadmap(relevantTask.id)}
                      >
                        Jump to Task in Roadmap →
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="btn-secondary btn-small"
                        onClick={() => onNavigateToRoadmap()}
                      >
                        Open Roadmap →
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Section E — All Linked Evidence Artifacts Consolidated */}
      <div className="evidence-section panel" style={{ marginTop: '28px' }}>
        <div className="panel-header">
          <div>
            <h3>All Linked Portfolio Artifacts ({evidenceList.length})</h3>
            <p>Proof records attached across your profile and mission milestones.</p>
          </div>
          <span className="mini-icon">📎</span>
        </div>

        {evidenceList.length === 0 ? (
          <div className="empty-state">
            <p>No portfolio artifacts linked yet. You can attach GitHub repositories, projects, or course certificates in your Career Mission milestones.</p>
          </div>
        ) : (
          <table className="evidence-table">
            <thead>
              <tr>
                <th>Artifact Title</th>
                <th>Associated Skill</th>
                <th>Type</th>
                <th>Review Status</th>
                <th>Reference Link</th>
              </tr>
            </thead>
            <tbody>
              {evidenceList.map((ev) => (
                <tr key={ev.id}>
                  <td>
                    <strong>{ev.title}</strong>
                    {ev.description && (
                      <div className="text-muted" style={{ fontSize: '11px', marginTop: '2px' }}>
                        {ev.description}
                      </div>
                    )}
                  </td>
                  <td>{ev.skill_name}</td>
                  <td>
                    <span className="evidence-type-tag">{ev.evidence_type}</span>
                  </td>
                  <td>
                    {ev.verified_by_staff ? (
                      <span className="status-badge verified">🛡️ Staff Reviewed</span>
                    ) : (
                      <span className="status-badge pending">📎 Student Submitted</span>
                    )}
                  </td>
                  <td>
                    {ev.url ? (
                      <a
                        href={ev.url}
                        target="_blank"
                        rel="noreferrer"
                        className="artifact-link"
                      >
                        View Artifact ↗
                      </a>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
