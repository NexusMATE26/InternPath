import React, { useState, useEffect } from 'react';
import { CareerMission, MissionTask } from './CareerMissionView';

interface HomeViewProps {
  onNavigateToRoadmap: () => void;
  onNavigateToCareers: () => void;
  onNavigateToReadiness: () => void;
  onNavigateToTechnical: () => void;
  onStartOnboarding?: () => void;
}

interface StudentProfile {
  name: string;
  email: string;
  weekly_hours: number;
  target_role_id?: string | null;
}

export const HomeView: React.FC<HomeViewProps> = ({
  onNavigateToRoadmap,
  onNavigateToCareers,
  onNavigateToReadiness,
  onNavigateToTechnical,
  onStartOnboarding,
}) => {
  const [mission, setMission] = useState<CareerMission | null>(null);
  const [profile, setProfile] = useState<StudentProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadHomeData() {
      setLoading(true);
      setError(null);
      try {
        const [missionRes, profileRes] = await Promise.all([
          fetch('/v1/missions/active'),
          fetch('/v1/profile'),
        ]);

        if (profileRes.ok) {
          const profData: StudentProfile = await profileRes.json();
          setProfile(profData);
        }

        if (missionRes.ok) {
          const missionData: CareerMission = await missionRes.json();
          setMission(missionData);
        } else if (missionRes.status === 404) {
          // Normal state: Student has not created an active mission yet
          setMission(null);
        } else {
          setError('Could not retrieve active mission details.');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Network error loading Home data');
      } finally {
        setLoading(false);
      }
    }

    loadHomeData();
  }, []);

  // Deterministic next recommended action derivation rule:
  // 1. Any task currently in_progress (highest priority: finish what was started)
  // 2. First not_started task that is unlocked (prerequisites completed)
  // 3. Fallback: all completed or first sequential task
  function getNextRecommendedAction(m: CareerMission): {
    task: MissionTask | null;
    type: 'in_progress' | 'unlocked' | 'all_completed';
    reason: string;
  } {
    const allTasks: MissionTask[] = m.active_version?.tasks || [];
    if (allTasks.length === 0) {
      return {
        task: null,
        type: 'all_completed',
        reason: 'No roadmap milestones registered in active mission.',
      };
    }

    // Rule 1: Find task in progress
    const inProgress = allTasks.find((t) => t.status === 'in_progress');
    if (inProgress) {
      return {
        task: inProgress,
        type: 'in_progress',
        reason: 'Active Milestone: You have already started this task. Continue your momentum.',
      };
    }

    // Rule 2: Find first unlocked task that has not been started
    const completedKeys = new Set(
      allTasks.filter((t) => t.status === 'completed').map((t) => t.stable_key)
    );

    const nextUnlocked = allTasks.find((t) => {
      if (t.status !== 'not_started') return false;
      if (t.is_unlocked) return true;
      const prereqs = t.prerequisite_task_keys || [];
      return prereqs.every((k) => completedKeys.has(k));
    });

    if (nextUnlocked) {
      return {
        task: nextUnlocked,
        type: 'unlocked',
        reason: 'Prerequisites Satisfied: All preparatory foundation skills are verified. Ready to start.',
      };
    }

    // Rule 3: Check if all completed
    const allCompleted = allTasks.every((t) => t.status === 'completed');
    if (allCompleted) {
      return {
        task: null,
        type: 'all_completed',
        reason: 'All roadmap milestones are 100% completed! You have met all target requirements for this mission.',
      };
    }

    const firstPending = allTasks.find((t) => t.status === 'not_started');
    return {
      task: firstPending || null,
      type: 'unlocked',
      reason: 'Next milestone in curriculum sequence.',
    };
  }

  if (loading) {
    return (
      <div className="home-container" id="home-view-loading">
        <div className="loading-state">
          <span className="spinner" /> Loading student workspace...
        </div>
      </div>
    );
  }

  // =========================================================================
  // VIEW A: RETURNING STUDENT WITH ACTIVE CAREER MISSION
  // =========================================================================
  if (mission) {
    const nextAction = getNextRecommendedAction(mission);
    const weeklyHours = profile?.weekly_hours || mission.weekly_hours || 10;
    const estWeeksRemaining = Math.max(
      1,
      Math.ceil((mission.estimated_remaining_hours_max || 10) / weeklyHours)
    );

    return (
      <div className="home-container" id="home-view-returning">
        {error && <div className="home-proposal-alert" style={{ borderLeftColor: '#ef4444' }}>⚠️ {error}</div>}
        {/* Welcome Header */}
        <div className="home-header">
          <div>
            <div className="eyebrow">CAREER READINESS COMPANION</div>
            <h1>Welcome back, {profile?.name?.split(' ')[0] || 'Student'} 👋</h1>
            <p className="lede">
              Here is where you stand today on your preparation journey and your highest-impact next step.
            </p>
          </div>
          <div className="home-header-badges">
            <span className="pill pill-goal">
              🎯 Goal: {mission.target_role_title || mission.title}
            </span>
            <span className="demo-data-chip" title="Illustrative fixture for competition demonstration">
              DEMO ROLE
            </span>
          </div>
        </div>

        {/* Pending Plan Change Proposal Banner (Agent Governance Alert) */}
        {mission.pending_proposals_count > 0 && (
          <div className="home-proposal-alert" id="home-pending-proposal-banner">
            <div className="alert-content">
              <span className="alert-icon">⚡</span>
              <div>
                <strong>Pending Plan Adjustment Proposal Awaiting Student Review</strong>
                <p>
                  The AI planning agent observed a schedule or deadline event and generated a proposed
                  mission revision. Your active mission remains protected and unchanged until you decide.
                </p>
              </div>
            </div>
            <button
              id="btn-home-review-proposal"
              className="btn-primary btn-alert-cta"
              onClick={onNavigateToRoadmap}
            >
              Review Proposal in Roadmap →
            </button>
          </div>
        )}

        {/* Recommended Next Action Card (Hero Focal Point) */}
        <div className="panel next-action-card" id="home-next-action-card">
          <div className="next-action-header">
            <div className="next-action-tag">
              <span className="pulse-dot">●</span> RECOMMENDED NEXT STEP
            </div>
            <span className="action-type-pill">
              {nextAction.type === 'in_progress' ? '▶ IN PROGRESS' : nextAction.type === 'unlocked' ? '✓ READY TO START' : '🏆 COMPLETED'}
            </span>
          </div>

          {nextAction.task ? (
            <div className="next-action-body">
              <div className="next-action-main">
                <h2>{nextAction.task.skill_name}</h2>
                <div className="next-action-meta">
                  <span className="badge-category">{nextAction.task.category}</span>
                  <span className="badge-level">
                    Target: Level {nextAction.task.target_level} / 3
                  </span>
                  <span className="badge-stage">
                    Stage {nextAction.task.stage_number}: {nextAction.task.stage_title}
                  </span>
                  <span className="badge-hours">
                    ⏱ ~{nextAction.task.estimated_hours_min}–{nextAction.task.estimated_hours_max} hrs
                  </span>
                </div>
                <p className="next-action-criteria">
                  <strong>Milestone Criteria:</strong> {nextAction.task.completion_criteria}
                </p>
                <div className="next-action-rationale">
                  <small>📌 <b>Why this task now:</b> {nextAction.reason}</small>
                </div>
              </div>

              <div className="next-action-cta-box">
                <button
                  id="btn-home-continue-task"
                  className="btn-primary btn-large"
                  onClick={onNavigateToRoadmap}
                >
                  Open Task in Roadmap →
                </button>
                <small className="cta-subtext">Prerequisites validated by C++ engine</small>
              </div>
            </div>
          ) : (
            <div className="next-action-completed">
              <h3>🎉 All Roadmap Milestones Complete!</h3>
              <p>{nextAction.reason}</p>
              <button className="btn-secondary" onClick={onNavigateToReadiness}>
                View Readiness Proof Map →
              </button>
            </div>
          )}
        </div>

        {/* 3-Card Status Overview Grid */}
        <div className="home-stats-grid">
          {/* Card 1: Mission Progress */}
          <div className="panel stat-card" id="home-card-progress">
            <div className="stat-card-top">
              <span className="stat-icon">📈</span>
              <span className="stat-version">
                Version {mission.active_version_number || 1}.0
              </span>
            </div>
            <div className="stat-value">{mission.progress_percent}%</div>
            <div className="stat-label">
              Roadmap Progress ({mission.completed_tasks} of {mission.total_tasks} milestones complete)
            </div>
            <div className="progress-bar-track">
              <div
                className="progress-bar-fill"
                style={{ width: `${mission.progress_percent}%` }}
              />
            </div>
            <div className="stat-footer">
              <span>{mission.in_progress_tasks} in progress</span>
              <button className="text-link" onClick={onNavigateToRoadmap}>
                View Stages →
              </button>
            </div>
          </div>

          {/* Card 2: Weekly Availability & Capacity */}
          <div className="panel stat-card" id="home-card-capacity">
            <div className="stat-card-top">
              <span className="stat-icon">⏱</span>
              <span className="stat-status text-safe">Sustainable Pacing</span>
            </div>
            <div className="stat-value">{weeklyHours} <small>hrs/wk</small></div>
            <div className="stat-label">Declared Weekly Learning Commitment</div>
            <div className="stat-effort-info">
              <span>Remaining Effort: <b>{mission.estimated_remaining_hours_min}–{mission.estimated_remaining_hours_max} hrs</b></span>
              <span>Estimated Runway: <b>~{estWeeksRemaining} weeks</b></span>
            </div>
            <div className="stat-footer">
              <span className="text-muted">Honors student capacity</span>
              <button className="text-link" onClick={onNavigateToReadiness}>
                Update Profile →
              </button>
            </div>
          </div>

          {/* Card 3: Application Runway & Deadline */}
          <div className="panel stat-card" id="home-card-deadline">
            <div className="stat-card-top">
              <span className="stat-icon">📅</span>
              <span className="stat-status text-muted">Application Timeline</span>
            </div>
            <div className="stat-value-subdued">Deadline not confirmed</div>
            <div className="stat-label">
              Official employer deadline has not been published yet.
            </div>
            <p className="timeline-honest-note">
              InternPath proactively monitors for verified deadline shifts and notifies you before making any plan recommendations.
            </p>
            <div className="stat-footer">
              <button className="text-link" onClick={onNavigateToTechnical}>
                Agent Event Feed →
              </button>
            </div>
          </div>
        </div>

        {/* Quick Navigation Cards */}
        <div className="home-quicknav-section">
          <h3>Workspace Sections</h3>
          <div className="home-quicknav-grid">
            <div className="quicknav-card" onClick={onNavigateToCareers}>
              <span className="quicknav-icon">🎯</span>
              <div>
                <strong>Internship Roles & Requirements</strong>
                <p>Explore Sri Lankan Embedded/IoT role profiles and mandatory competencies.</p>
              </div>
              <span className="arrow">→</span>
            </div>

            <div className="quicknav-card" onClick={onNavigateToRoadmap}>
              <span className="quicknav-icon">🛤</span>
              <div>
                <strong>Active Career Roadmap</strong>
                <p>Complete prerequisite-ordered tasks, log progress, and review plan versions.</p>
              </div>
              <span className="arrow">→</span>
            </div>

            <div className="quicknav-card" onClick={onNavigateToReadiness}>
              <span className="quicknav-icon">◈</span>
              <div>
                <strong>Readiness Proof Map</strong>
                <p>Verify your competency evidence, certifications, and portfolio links.</p>
              </div>
              <span className="arrow">→</span>
            </div>

            <div className="quicknav-card highlight-technical" onClick={onNavigateToTechnical}>
              <span className="quicknav-icon">🔬</span>
              <div>
                <strong>Technical / Judge Mode</strong>
                <p>Inspect C++ DSA traces, Kahn's algorithm stages, and the AI agent audit log.</p>
              </div>
              <span className="arrow">→</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // =========================================================================
  // VIEW B: NEW STUDENT ONBOARDING WELCOME (NO ACTIVE MISSION YET)
  // =========================================================================
  return (
    <div className="home-container" id="home-view-new-student">
      <div className="welcome-hero-card">
        <div className="welcome-hero-left">
          <div className="eyebrow">INTERNPATH AI • STUDENT COMPANION</div>
          <h1>Know where you stand.<br />Stay on track. Stay in control.</h1>
          <p className="welcome-tagline">
            InternPath helps engineering undergraduates prepare for competitive technical internships
            by matching your skills against verified requirements, building a custom learning path,
            and monitoring your progress.
          </p>
          <div className="welcome-cta-row">
            <button
              id="btn-home-choose-goal"
              className="btn-primary btn-large"
              onClick={onStartOnboarding || onNavigateToCareers}
            >
              🎯 Choose Your Internship Goal →
            </button>
            <button
              id="btn-home-inspect-dsa"
              className="btn-secondary"
              onClick={onNavigateToTechnical}
            >
              🔬 Inspect C++ DSA Engine
            </button>
          </div>
        </div>
        <div className="welcome-hero-right">
          <div className="welcome-badge-box">
            <div className="welcome-badge-title">THE INTERNPATH PRINCIPLE</div>
            <div className="welcome-badge-principle">
              "The AI proposes.<br />
              The algorithms validate.<br />
              <b>The student decides.</b>"
            </div>
            <small>Human-governed plan versioning with zero autonomous mutations.</small>
          </div>
        </div>
      </div>

      {/* 4-Step Student Journey Preview */}
      <div className="journey-preview-section">
        <div className="section-header">
          <h2>How InternPath prepares you in 4 transparent steps</h2>
          <p>Transparent data structures and algorithms—no mysterious black-box scores.</p>
        </div>

        <div className="journey-steps-grid">
          <div className="journey-step-card">
            <div className="step-number">1</div>
            <span className="step-icon">🎯</span>
            <h4>Choose Your Goal</h4>
            <p>
              Select your target engineering internship role. Inspect what employers actually require,
              from foundational C++ and RTOS to containerization and embedded Linux.
            </p>
          </div>

          <div className="journey-step-card">
            <div className="step-number">2</div>
            <span className="step-icon">◈</span>
            <h4>Rate Skills & Add Proof</h4>
            <p>
              Assess your current competence on a standardized 0–3 scale. Attach project repositories,
              certifications, and lab evidence to back up your claims.
            </p>
          </div>

          <div className="journey-step-card">
            <div className="step-number">3</div>
            <span className="step-icon">🛤</span>
            <h4>Generate Roadmap</h4>
            <p>
              Our handwritten C++20 graph engine computes prerequisite closure and Kahn's topological
              order to produce an achievable, staged learning roadmap.
            </p>
          </div>

          <div className="journey-step-card">
            <div className="step-number">4</div>
            <span className="step-icon">🛡</span>
            <h4>Stay on Track</h4>
            <p>
              If a company deadline moves earlier, our AI evaluator assesses feasibility and stages an
              explainable proposal. You approve or reject every change.
            </p>
          </div>
        </div>
      </div>

      <div className="demo-data-notice">
        <span>ℹ <b>Academic Competition Notice:</b> Current sample catalogue roles are illustrative fixtures for system demonstration. Official employer-grounded Sri Lankan Embedded/IoT role profiles are slated for Refinement R3.</span>
      </div>
    </div>
  );
};
