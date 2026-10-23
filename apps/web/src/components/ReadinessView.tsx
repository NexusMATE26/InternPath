import React, { useState } from 'react';

export interface Skill {
  id: number;
  name: string;
  category: string;
  max_level: number;
  description: string;
}

export interface StudentSkillState {
  level: number;
  is_verified: boolean;
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

interface ReadinessViewProps {
  skills: Skill[];
  studentSkills: Record<number, StudentSkillState>;
  onSkillChange: (skillId: number, level: number, isVerified: boolean) => void;
  studentName: string;
  weeklyHours: number;
  onWeeklyHoursChange: (hours: number) => void;
  evidenceList: EvidenceItem[];
  onSaveProfile: () => Promise<void>;
  saving: boolean;
  saveSuccess: boolean;
  saveError: string;
  onNavigateToRoadmap: () => void;
}

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
}) => {
  const [filterCategory, setFilterCategory] = useState<string>('all');

  const categories = ['all', ...Array.from(new Set(skills.map((s) => s.category)))];

  const filteredSkills = skills.filter((s) =>
    filterCategory === 'all' ? true : s.category === filterCategory
  );

  const declaredCount = Object.values(studentSkills).filter((v) => v.level > 0).length;
  const verifiedCount = Object.values(studentSkills).filter((v) => v.is_verified && v.level > 0).length;

  return (
    <div className="readiness-view-container" id="readiness-view">
      <div className="view-header">
        <div className="eyebrow">READINESS PROOF & COMPETENCY ASSESSMENT</div>
        <h1>Demonstrated Skills & Evidence Map</h1>
        <p className="lede">
          Readiness is proof-grounded, not an arbitrary employment probability. Rate your technical
          proficiency, inspect verified versus self-reported competencies, and link artifacts.
        </p>
      </div>

      {/* Profile & Weekly Capacity Bar */}
      <div className="profile-persistence-bar panel">
        <div className="profile-info">
          <span className="profile-tag">STUDENT WORKSPACE</span>
          <strong>{studentName}</strong>
          <span className="capacity-control">
            • Weekly Available Study:
            <select
              id="select-weekly-hours"
              className="select-hours"
              value={weeklyHours}
              onChange={(e) => onWeeklyHoursChange(Number(e.target.value))}
            >
              <option value={5}>5 hrs/week (Part-time slow)</option>
              <option value={10}>10 hrs/week (Standard undergraduate)</option>
              <option value={15}>15 hrs/week (Active preparation)</option>
              <option value={20}>20 hrs/week (Intensive preparation)</option>
              <option value={30}>30 hrs/week (Sprint mode)</option>
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
            {saving ? 'Saving…' : '💾 Save Profile to DB'}
          </button>
          {saveSuccess && <span className="save-status-msg success">✓ Saved successfully</span>}
          {saveError && <span className="save-status-msg error">⚠️ {saveError}</span>}
        </div>
      </div>

      {/* Summary Metrics */}
      <div className="readiness-summary-grid">
        <div className="panel summary-pill-card">
          <span className="summary-icon">◈</span>
          <div>
            <div className="summary-val">{declaredCount} / {skills.length}</div>
            <small>Declared Competencies</small>
          </div>
        </div>

        <div className="panel summary-pill-card highlight-verified">
          <span className="summary-icon">🛡️</span>
          <div>
            <div className="summary-val">{verifiedCount} Verified</div>
            <small>External / Assessment Verified</small>
          </div>
        </div>

        <div className="panel summary-pill-card">
          <span className="summary-icon">📎</span>
          <div>
            <div className="summary-val">{evidenceList.length} Items</div>
            <small>Linked Portfolio Artifacts</small>
          </div>
        </div>

        <div className="panel summary-action-card">
          <button className="btn-secondary" onClick={onNavigateToRoadmap}>
            Apply Skills to Roadmap →
          </button>
        </div>
      </div>

      {/* Category Filter Chips */}
      <div className="category-filter-chips">
        <span className="filter-label">Filter Category:</span>
        {categories.map((cat) => (
          <button
            key={cat}
            className={`filter-chip ${filterCategory === cat ? 'active' : ''}`}
            onClick={() => setFilterCategory(cat)}
          >
            {cat.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Skills Matrix Grid */}
      <div className="readiness-skills-grid">
        {filteredSkills.map((s) => {
          const state = studentSkills[s.id] || { level: 0, is_verified: false };
          return (
            <div key={s.id} className="skill-card panel" id={`readiness-skill-${s.id}`}>
              <div className="skill-card-header">
                <div>
                  <strong className="skill-name">{s.name}</strong>
                  <span className="skill-category-badge">{s.category}</span>
                </div>
                {state.is_verified ? (
                  <span className="badge-verified" title="Verified by assessment or certificate">
                    🛡️ VERIFIED
                  </span>
                ) : (
                  <span className="badge-self-report" title="Self-reported declaration">
                    SELF-REPORTED
                  </span>
                )}
              </div>

              <p className="skill-description">{s.description}</p>

              <div className="skill-level-control">
                <span className="control-label">Your Proficiency:</span>
                <div className="level-buttons-group">
                  {[0, 1, 2, 3].map((lvl) => (
                    <button
                      key={lvl}
                      type="button"
                      className={`level-btn ${state.level === lvl ? 'active' : ''}`}
                      onClick={() => onSkillChange(s.id, lvl, state.is_verified)}
                    >
                      {lvl === 0 ? 'None (0)' : lvl === 1 ? 'Basic (1)' : lvl === 2 ? 'Intermediate (2)' : 'Advanced (3)'}
                    </button>
                  ))}
                </div>
              </div>

              <div className="skill-verify-toggle">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={state.is_verified}
                    onChange={(e) => onSkillChange(s.id, state.level, e.target.checked)}
                  />
                  <span>Mark as verified with portfolio artifact / coursework</span>
                </label>
              </div>
            </div>
          );
        })}
      </div>

      {/* Portfolio Evidence Artifacts List */}
      <div className="evidence-section panel">
        <div className="panel-header">
          <div>
            <h3>Linked Evidence & Project Artifacts ({evidenceList.length})</h3>
            <p>Proof records attached to milestones and skills.</p>
          </div>
          <span className="mini-icon">📎</span>
        </div>

        {evidenceList.length === 0 ? (
          <div className="empty-state">
            <p>No portfolio artifacts linked yet. Link GitHub repositories, projects, or course certificates in your Career Mission.</p>
          </div>
        ) : (
          <table className="evidence-table">
            <thead>
              <tr>
                <th>Artifact Title</th>
                <th>Associated Skill</th>
                <th>Type</th>
                <th>Verification Status</th>
                <th>Reference Link</th>
              </tr>
            </thead>
            <tbody>
              {evidenceList.map((ev) => (
                <tr key={ev.id}>
                  <td>
                    <strong>{ev.title}</strong>
                    <br />
                    <small className="text-muted">{ev.description}</small>
                  </td>
                  <td>{ev.skill_name}</td>
                  <td><span className="evidence-type-tag">{ev.evidence_type}</span></td>
                  <td>
                    {ev.verified_by_staff ? (
                      <span className="status-badge verified">🛡️ Staff Verified</span>
                    ) : (
                      <span className="status-badge pending">⏳ Student Submitted</span>
                    )}
                  </td>
                  <td>
                    {ev.url ? (
                      <a href={ev.url} target="_blank" rel="noreferrer" className="artifact-link">
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
