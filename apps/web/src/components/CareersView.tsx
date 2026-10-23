import React, { useState, useEffect } from 'react';

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

export interface RoleDetail {
  role_id: string;
  title: string;
  department: string;
  location: string;
  description: string;
  requirements: RoleRequirementItem[];
}

interface CareersViewProps {
  roles: RoleItem[];
  selectedRoleId: string;
  onSelectRole: (roleId: string) => void;
  onNavigateToRoadmap: () => void;
  onNavigateToReadiness: () => void;
  onStartOnboarding?: (roleId: string) => void;
  studentSkills?: Record<number, { level: number; is_verified: boolean }>;
}

export const CareersView: React.FC<CareersViewProps> = ({
  roles,
  selectedRoleId,
  onSelectRole,
  onNavigateToRoadmap,
  onNavigateToReadiness,
  onStartOnboarding,
  studentSkills = {},
}) => {
  const [roleDetail, setRoleDetail] = useState<RoleDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadRoleRequirements() {
      if (!selectedRoleId) return;
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/v1/roles/${selectedRoleId}/requirements`);
        if (res.ok) {
          const detail: RoleDetail = await res.json();
          setRoleDetail(detail);
        } else {
          setError(`Could not load requirements for role "${selectedRoleId}"`);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error fetching role details');
      } finally {
        setLoading(false);
      }
    }

    loadRoleRequirements();
  }, [selectedRoleId]);

  // Compute student skill matches and gaps for the selected role
  const requirements = roleDetail?.requirements || [];

  const matchedSkills: Array<{
    req: RoleRequirementItem;
    studentLevel: number;
    isVerified: boolean;
    isMet: boolean;
  }> = [];

  const skillGaps: Array<{
    req: RoleRequirementItem;
    studentLevel: number;
    levelGap: number;
  }> = [];

  requirements.forEach((req) => {
    const student = studentSkills[req.skill_id];
    const studentLevel = student?.level ?? 0;
    const isVerified = student?.is_verified ?? false;
    const isMet = studentLevel >= req.required_level;

    if (studentLevel > 0) {
      matchedSkills.push({ req, studentLevel, isVerified, isMet });
    }

    if (studentLevel < req.required_level) {
      skillGaps.push({
        req,
        studentLevel,
        levelGap: req.required_level - studentLevel,
      });
    }
  });

  return (
    <div className="careers-view-container" id="careers-view">
      {/* Page Header */}
      <div className="view-header">
        <div className="eyebrow">INTERNSHIP CAREER PROFILES</div>
        <h1>Explore Roles & Required Competencies</h1>
        <p className="lede">
          Understand what technical engineering roles require before applying. Compare required
          competencies against your current skills and build a clear plan to close gaps.
        </p>
      </div>

      {/* Honest Provenance Banner */}
      <div className="demo-notice-banner">
        <span>
          ℹ <b>Academic Competition Notice:</b> Roles below are illustrative engineering competency
          profiles for system demonstration and algorithm validation. They are not active employer
          job vacancies. Sourced Sri Lankan Embedded / IoT job postings will be introduced in Refinement R3.
        </span>
      </div>

      <div className="careers-layout-grid">
        {/* Left Column: Role Cards */}
        <div className="careers-roles-panel panel">
          <div className="panel-header">
            <div>
              <h3>Available Role Profiles ({roles.length})</h3>
              <p>Select a profile to inspect its requirements.</p>
            </div>
            <span className="mini-icon">🎯</span>
          </div>

          <div className="role-cards-container">
            {roles.map((r) => {
              const isSelected = r.role_id === selectedRoleId;
              return (
                <div
                  key={r.role_id}
                  id={`career-role-card-${r.role_id}`}
                  className={`role-card ${isSelected ? 'selected' : ''}`}
                  onClick={() => onSelectRole(r.role_id)}
                  tabIndex={0}
                  role="button"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') onSelectRole(r.role_id);
                  }}
                >
                  <div className="role-card-header">
                    <strong className="role-title">{r.title}</strong>
                    <span className="demo-tag">DEMO ROLE</span>
                  </div>
                  <div className="role-meta-row">
                    <span className="badge-dept">{r.department}</span>
                    <span className="badge-location">📍 {r.location}</span>
                  </div>
                  <p className="role-desc">{r.description}</p>
                  <div className="role-card-footer">
                    <span>{r.requirements_count} required competencies</span>
                    <span className="select-hint">
                      {isSelected ? '✓ Inspecting' : 'Click to inspect →'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Structured Role Details */}
        <div className="careers-detail-panel panel">
          {loading ? (
            <div className="loading-state">
              <span className="spinner" /> Loading competency profile...
            </div>
          ) : error ? (
            <div className="error-state">{error}</div>
          ) : roleDetail ? (
            <div className="role-details-container">
              {/* Section 1: About This Role & CTA Header */}
              <div className="role-hero-header">
                <div className="role-hero-info">
                  <div className="role-eyebrow">CAREER PROFILE OVERVIEW</div>
                  <h2>{roleDetail.title}</h2>
                  <div className="role-meta-badges">
                    <span className="badge-dept">{roleDetail.department}</span>
                    <span className="badge-location">📍 {roleDetail.location}</span>
                    <span className="badge-provenance">Illustrative Curriculum Profile</span>
                  </div>
                  <p className="role-full-desc">{roleDetail.description}</p>
                </div>

                <div className="role-hero-actions">
                  {onStartOnboarding && (
                    <button
                      id="btn-careers-start-onboarding"
                      className="btn-primary btn-large"
                      onClick={() => onStartOnboarding(roleDetail.role_id)}
                      title="Generate a personalized learning path and mission for this goal"
                    >
                      🚀 Start Roadmap for This Goal →
                    </button>
                  )}
                  <button
                    id="btn-careers-plan-roadmap"
                    className="btn-secondary"
                    onClick={onNavigateToRoadmap}
                  >
                    View Active Roadmap →
                  </button>
                  <button
                    className="btn-secondary"
                    onClick={onNavigateToReadiness}
                  >
                    Rate Skills in Readiness Map →
                  </button>
                </div>
              </div>

              {/* Section 2: What You Already Know vs What You Still Need */}
              <div className="skills-comparison-grid">
                {/* Left Card: What You Already Know */}
                <div className="comparison-card matched-card">
                  <div className="card-top-header">
                    <h4>✓ What You Already Know ({matchedSkills.length})</h4>
                    <small>Skills from your saved profile</small>
                  </div>

                  {matchedSkills.length === 0 ? (
                    <div className="comparison-empty">
                      <p>You haven't assessed skills for this role yet.</p>
                      <button
                        className="btn-secondary btn-small"
                        onClick={() =>
                          onStartOnboarding
                            ? onStartOnboarding(roleDetail.role_id)
                            : onNavigateToReadiness()
                        }
                      >
                        Self-Assess My Skills →
                      </button>
                    </div>
                  ) : (
                    <div className="comparison-items-list">
                      {matchedSkills.map(({ req, studentLevel, isVerified, isMet }) => (
                        <div key={req.skill_id} className="skill-match-row">
                          <div className="skill-name-col">
                            <strong>{req.skill_name}</strong>
                            <span className="skill-level-text">
                              Your level: <b>Level {studentLevel} / 3</b>
                              {isVerified && <span className="verified-chip">Verified ✓</span>}
                            </span>
                          </div>
                          <div>
                            {isMet ? (
                              <span className="status-met-badge">Requirement Met</span>
                            ) : (
                              <span className="status-progress-badge">
                                Partial (Target: L{req.required_level})
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Right Card: What You Still Need (Skill Gaps) */}
                <div className="comparison-card gaps-card">
                  <div className="card-top-header">
                    <h4>◈ What You Still Need ({skillGaps.length} Gaps)</h4>
                    <small>Skills to learn in your roadmap</small>
                  </div>

                  {skillGaps.length === 0 ? (
                    <div className="comparison-empty-success">
                      <span>🎉</span>
                      <p>You meet all stated competency thresholds for this role!</p>
                    </div>
                  ) : (
                    <div className="comparison-items-list">
                      {skillGaps.map(({ req, studentLevel, levelGap }) => (
                        <div key={req.skill_id} className="skill-gap-row">
                          <div className="gap-info-col">
                            <strong>{req.skill_name}</strong>
                            <span className="gap-detail-text">
                              Current: L{studentLevel} → Target: L{req.required_level} (+{levelGap}{' '}
                              lvl)
                            </span>
                          </div>
                          <div>
                            {req.mandatory ? (
                              <span className="badge-mandatory">★ Mandatory Core</span>
                            ) : (
                              <span className="badge-optional">○ Elective</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Section 3: Full Role Competency Requirements */}
              <div className="requirements-section">
                <div className="section-title-row">
                  <h3>All Required Competencies & Role Context</h3>
                  <small>Evaluated by our C++ Kahn's algorithm planning engine</small>
                </div>

                <div className="requirements-table-wrapper">
                  <table className="requirements-table">
                    <thead>
                      <tr>
                        <th>Competency Skill</th>
                        <th>Required Level</th>
                        <th>Classification</th>
                        <th>Role Context & Rationale</th>
                      </tr>
                    </thead>
                    <tbody>
                      {roleDetail.requirements.map((req) => (
                        <tr key={req.skill_id}>
                          <td>
                            <strong>{req.skill_name}</strong>
                          </td>
                          <td>
                            <span className={`level-pill level-${req.required_level}`}>
                              Level {req.required_level} / 3
                            </span>
                          </td>
                          <td>
                            {req.mandatory ? (
                              <span className="badge-mandatory">★ MANDATORY CORE</span>
                            ) : (
                              <span className="badge-optional">○ PREFERRED ELECTIVE</span>
                            )}
                          </td>
                          <td className="context-cell">
                            {req.role_context || 'Core prerequisite for this position.'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="grounding-note">
                  <small>
                    🛡 <b>Transparent Algorithm Grounding:</b> InternPath strictly separates mandatory
                    core prerequisites from optional electives. During tight deadlines, our C++ planner
                    can defer optional electives while strictly preserving mandatory prerequisites.
                  </small>
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <p>Select a role on the left to inspect its requirements.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
