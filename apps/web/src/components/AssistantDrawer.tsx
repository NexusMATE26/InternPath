import React from 'react';

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

interface AssistantDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigateToRoadmap: (taskId?: number) => void;
  onNavigateToCareers: () => void;
  onNavigateToReadiness?: () => void;
  studentName: string;
  activeRoleTitle?: string | null;
  weeklyHours: number;
  activeMission?: CareerMission | null;
}

export const AssistantDrawer: React.FC<AssistantDrawerProps> = ({
  isOpen,
  onClose,
  onNavigateToRoadmap,
  onNavigateToCareers,
  onNavigateToReadiness,
  studentName,
  activeRoleTitle,
  weeklyHours,
  activeMission,
}) => {
  if (!isOpen) return null;

  // Next recommended task: prioritize in-progress, then first unlocked not_started
  const allTasks = activeMission?.active_version?.tasks || [];
  const inProgressTask = allTasks.find((t) => t.status === 'in_progress');
  const nextUnlockedTask = allTasks.find((t) => t.status === 'not_started' && t.is_unlocked);
  const nextTask = inProgressTask || nextUnlockedTask;

  const hasPendingProposals = (activeMission?.pending_proposals_count ?? 0) > 0;
  const isMissionComplete = allTasks.length > 0 && allTasks.every((t) => t.status === 'completed');

  return (
    <div className="assistant-drawer-overlay" onClick={onClose} id="assistant-drawer-overlay">
      <div
        className="assistant-drawer-panel"
        onClick={(e) => e.stopPropagation()}
        id="assistant-drawer"
      >
        {/* Drawer Header */}
        <div className="drawer-header">
          <div className="drawer-header-left">
            <span className="assistant-avatar">✦</span>
            <div>
              <h3>InternPath Contextual Assistant</h3>
              <small>Grounded Database & Plan Companion</small>
            </div>
          </div>
          <button className="drawer-close-btn" onClick={onClose} title="Close Assistant">
            ✕
          </button>
        </div>

        <div className="drawer-body">
          {/* Active Goal & Context Card */}
          <div className="drawer-context-card" id="assistant-context-card">
            <span className="context-label">CURRENT ACTIVE MISSION CONTEXT</span>
            <h4>{studentName || 'Student'}</h4>
            <div className="context-meta-row">
              <span>
                🎯 Target Role: <b>{activeMission?.target_role_title || activeRoleTitle || 'None selected'}</b>
              </span>
              <span>
                ⏱ Study Capacity: <b>{activeMission?.weekly_hours || weeklyHours} hrs/wk</b>
              </span>
            </div>
            {activeMission ? (
              <div className="context-mission-status">
                <div className="status-metric-line">
                  <span>Mission Progress:</span>
                  <b>{activeMission.completed_tasks} / {activeMission.total_tasks} milestones completed ({activeMission.progress_percent}%)</b>
                </div>
                <div className="mini-progress-bar-bg">
                  <div
                    className="mini-progress-bar-fill"
                    style={{ width: `${activeMission.progress_percent}%` }}
                  />
                </div>
              </div>
            ) : (
              <div className="context-mission-empty">
                <small>No active Career Mission generated yet.</small>
              </div>
            )}
          </div>

          {/* Pending Plan Change Proposal Alert (Agent-Generated) */}
          {hasPendingProposals && (
            <div className="drawer-alert-card proposal-alert" id="assistant-proposal-alert">
              <div className="alert-card-header">
                <span className="alert-icon">⚠️</span>
                <strong>Plan Change Proposal Pending</strong>
              </div>
              <p>
                An agent evaluation detected a timeline or constraint change and prepared a plan adjustment proposal
                for your active Career Mission.
              </p>
              <button
                type="button"
                className="btn-primary btn-small"
                onClick={() => {
                  onClose();
                  onNavigateToRoadmap();
                }}
              >
                Review Plan Proposal in Roadmap →
              </button>
            </div>
          )}

          {/* Next Recommended Task Card (Grounded in Real Mission Data) */}
          <div className="drawer-next-task-section" id="assistant-next-task-card">
            <h5>Actual Next Mission Milestone</h5>
            {nextTask ? (
              <div className="next-task-grounded-card">
                <div className="task-header-line">
                  <span className={`task-badge ${nextTask.status === 'in_progress' ? 'badge-in-progress' : 'badge-unlocked'}`}>
                    {nextTask.status === 'in_progress' ? '⚡ In Progress' : '▶ Unlocked & Ready'}
                  </span>
                  <span className="task-stage-tag">
                    Stage {nextTask.stage_number}: {nextTask.stage_title}
                  </span>
                </div>

                <h4 className="grounded-task-title">{nextTask.skill_name}</h4>
                <div className="task-effort-snippet">
                  Target Proficiency: Level {nextTask.target_level} • Effort: {nextTask.estimated_hours_min}–{nextTask.estimated_hours_max} hours
                </div>

                {/* Grounded Completion Criteria */}
                {nextTask.completion_criteria && (
                  <div className="grounded-metadata-box">
                    <span className="metadata-label">Grounded Completion Criteria:</span>
                    <p>{nextTask.completion_criteria}</p>
                  </div>
                )}

                {/* Grounded Graph Rationale */}
                {nextTask.rationale && (
                  <div className="grounded-metadata-box rationale-box">
                    <span className="metadata-label">Topological Prerequisite Rationale:</span>
                    <p>{nextTask.rationale}</p>
                  </div>
                )}

                <div className="task-action-row">
                  <button
                    type="button"
                    className="btn-primary btn-small"
                    onClick={() => {
                      onClose();
                      onNavigateToRoadmap(nextTask.id);
                    }}
                  >
                    Open Milestone in Roadmap →
                  </button>
                </div>
              </div>
            ) : isMissionComplete ? (
              <div className="all-complete-card">
                <span className="party-icon">🎉</span>
                <strong>All Current Milestones Completed!</strong>
                <p>
                  You have completed all milestones in your active Career Mission. Inspect your Readiness
                  Proof Map or select an advanced specialization.
                </p>
                {onNavigateToReadiness && (
                  <button
                    type="button"
                    className="btn-secondary btn-small"
                    onClick={() => {
                      onClose();
                      onNavigateToReadiness();
                    }}
                  >
                    View Readiness Proof Map →
                  </button>
                )}
              </div>
            ) : (
              <div className="no-task-card">
                <p>No active milestones available. Generate a Career Mission to receive your personalized roadmap.</p>
                <button
                  type="button"
                  className="btn-secondary btn-small"
                  onClick={() => {
                    onClose();
                    onNavigateToCareers();
                  }}
                >
                  Explore Careers & Generate Mission →
                </button>
              </div>
            )}
          </div>

          {/* Grounded Inquiries / Navigation Shortcuts */}
          <div className="drawer-actions-section">
            <h5>Contextual Navigation Shortcuts</h5>
            <div className="drawer-prompts-list">
              {onNavigateToReadiness && (
                <button
                  type="button"
                  className="drawer-prompt-btn"
                  onClick={() => {
                    onClose();
                    onNavigateToReadiness();
                  }}
                >
                  <span>◈</span>
                  <div>
                    <strong>"What skills and evidence am I missing?"</strong>
                    <small>Inspects the Readiness Proof Map & requirement gaps</small>
                  </div>
                </button>
              )}

              <button
                type="button"
                className="drawer-prompt-btn"
                onClick={() => {
                  onClose();
                  onNavigateToRoadmap();
                }}
              >
                <span>🛤</span>
                <div>
                  <strong>"What is the topological order of my tasks?"</strong>
                  <small>Opens your Kahn-sorted stages in Active Roadmap</small>
                </div>
              </button>

              <button
                type="button"
                className="drawer-prompt-btn"
                onClick={() => {
                  onClose();
                  onNavigateToCareers();
                }}
              >
                <span>🎯</span>
                <div>
                  <strong>"Which competencies are mandatory vs elective?"</strong>
                  <small>Compares target role requirements in Careers</small>
                </div>
              </button>
            </div>
          </div>

          {/* Honest Architectural Disclosure */}
          <div className="drawer-future-roadmap" id="assistant-transparency-notice">
            <small>
              🛡 <b>Truthful AI Capability Disclosure:</b> In Refinement R1.4, this assistant provides
              deterministic guidance directly grounded in your persistent database mission state and C++
              prerequisite graph. Genuine LLM tool-calling (<code>read_student_profile</code>, <code>simulate_plan_variant</code>)
              and free-form natural language dialogue are scheduled for <b>Refinement R2</b>.
            </small>
          </div>
        </div>
      </div>
    </div>
  );
};
