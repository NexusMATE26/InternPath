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
}

export const CareersView: React.FC<CareersViewProps> = ({
  roles,
  selectedRoleId,
  onSelectRole,
  onNavigateToRoadmap,
  onNavigateToReadiness,
  onStartOnboarding,
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
          setError(`Could not load requirements for ${selectedRoleId}`);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error fetching role details');
      } finally {
        setLoading(false);
      }
    }

    loadRoleRequirements();
  }, [selectedRoleId]);

  return (
    <div className="careers-view-container" id="careers-view">
      <div className="view-header">
        <div className="eyebrow">INTERNSHIP CATALOGUE & REQUIREMENTS</div>
        <h1>Target Engineering Roles & Competency Profiles</h1>
        <p className="lede">
          Understand what engineering employers actually require before you apply. Inspect required
          competencies, mandatory core prerequisites, and preferred electives.
        </p>
      </div>

      <div className="demo-notice-banner">
        <span>
          ℹ <b>Demo Data Notice:</b> Current roles are illustrative fixtures for competition
          demonstration. Sri Lankan Embedded Systems / IoT internship opportunities will be expanded in Refinement R3.
        </span>
      </div>

      <div className="careers-layout-grid">
        {/* Left: Role Selection Cards */}
        <div className="careers-roles-panel panel">
          <div className="panel-header">
            <div>
              <h3>Available Roles ({roles.length})</h3>
              <p>Select a position to view source requirements.</p>
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
                >
                  <div className="role-card-header">
                    <strong className="role-title">{r.title}</strong>
                    <span className="demo-tag">DEMO</span>
                  </div>
                  <div className="role-meta-row">
                    <span className="badge-dept">{r.department}</span>
                    <span className="badge-location">📍 {r.location}</span>
                  </div>
                  <p className="role-desc">{r.description}</p>
                  <div className="role-card-footer">
                    <span>{r.requirements_count} required competencies</span>
                    <span className="select-hint">{isSelected ? '✓ Selected Target' : 'Click to inspect →'}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Selected Role Competency Requirements */}
        <div className="careers-detail-panel panel">
          <div className="panel-header">
            <div>
              <h3>Role Competencies & Prerequisites</h3>
              <p>Ground truth requirements evaluated by our C++ graph engine.</p>
            </div>
            <span className="mini-icon">📋</span>
          </div>

          {loading ? (
            <div className="loading-state">
              <span className="spinner" /> Loading competency profile...
            </div>
          ) : error ? (
            <div className="error-state">{error}</div>
          ) : roleDetail ? (
            <div className="role-requirements-content">
              <div className="role-summary-banner">
                <div>
                  <h4>{roleDetail.title}</h4>
                  <small>{roleDetail.department} • {roleDetail.location}</small>
                </div>
                <div className="action-buttons-group">
                  {onStartOnboarding && (
                    <button
                      id="btn-careers-start-onboarding"
                      className="btn-primary"
                      onClick={() => onStartOnboarding(roleDetail.role_id)}
                    >
                      🚀 Start Roadmap for This Goal →
                    </button>
                  )}
                  <button
                    id="btn-careers-plan-roadmap"
                    className="btn-secondary"
                    onClick={onNavigateToRoadmap}
                  >
                    View / Plan Roadmap →
                  </button>
                  <button
                    className="btn-secondary"
                    onClick={onNavigateToReadiness}
                  >
                    Assess My Skills →
                  </button>
                </div>
              </div>

              <div className="requirements-table-wrapper">
                <table className="requirements-table">
                  <thead>
                    <tr>
                      <th>Competency Skill</th>
                      <th>Required Level</th>
                      <th>Importance</th>
                      <th>Role Context & Rationale</th>
                    </tr>
                  </thead>
                  <tbody>
                    {roleDetail.requirements.map((req) => (
                      <tr key={req.skill_id}>
                        <td>
                          <strong>{req.skill_name}</strong>
                          <br />
                          <small className="text-muted">Skill ID #{req.skill_id}</small>
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
                          {req.role_context || 'Standard role prerequisite.'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="grounding-note">
                <small>
                  🛡 <b>Ethical Grounding:</b> InternPath strictly separates mandatory prerequisites from
                  optional electives. During deadline crunches, the planning agent can suggest deferring
                  optional electives while strictly preserving mandatory prerequisites.
                </small>
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
