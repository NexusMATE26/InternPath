import { useState, useEffect } from 'react';

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
  status: 'not_started' | 'in_progress' | 'completed';
  is_unlocked: boolean;
  estimated_hours_min: number;
  estimated_hours_max: number;
  completion_criteria: string;
  rationale: string;
  prerequisite_task_keys: string[];
  evidence_id?: number | null;
  completed_at?: string | null;
  completed_by?: string | null;
  override_reason?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MissionStage {
  stage_number: number;
  stage_title: string;
  total_tasks: number;
  completed_tasks: number;
  stage_hours_min: number;
  stage_hours_max: number;
  tasks: MissionTask[];
}

export interface MissionVersionDetail {
  id: number;
  mission_id: number;
  version_number: number;
  title: string;
  rationale: string;
  source_schema_version: string;
  is_active: boolean;
  created_by: string;
  approved_by?: string | null;
  approved_at?: string | null;
  total_estimated_hours_min: number;
  total_estimated_hours_max: number;
  total_tasks: number;
  completed_tasks: number;
  stages: MissionStage[];
  tasks: MissionTask[];
  created_at?: string | null;
}

export interface CareerMission {
  id: number;
  student_id: number;
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
  estimated_remaining_hours_min: number;
  estimated_remaining_hours_max: number;
  active_version?: MissionVersionDetail | null;
  pending_proposals_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TaskProgressEvent {
  id: number;
  task_id: number;
  from_status: string;
  to_status: string;
  evidence_id?: number | null;
  notes: string;
  actor: string;
  created_at?: string | null;
}

export interface MissionProposal {
  id: number;
  mission_id: number;
  base_version_number: number;
  proposed_by: string;
  proposal_title: string;
  rationale: string;
  diff_summary: {
    added_tasks?: any[];
    removed_tasks?: any[];
    retained_tasks?: any[];
    effort_delta?: { min_hours: number; max_hours: number };
  };
  status: 'pending' | 'approved' | 'rejected';
  student_decision_notes?: string | null;
  decided_by?: string | null;
  decided_at?: string | null;
  created_at?: string | null;
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

interface CareerMissionViewProps {
  onNavigateToPlanner: () => void;
  availableRoles: Array<{ role_id: string; title: string }>;
  evidenceList: EvidenceItem[];
  onEvidenceCreated?: () => void;
  onStartOnboarding?: () => void;
}

export default function CareerMissionView({
  onNavigateToPlanner,
  availableRoles,
  evidenceList,
  onStartOnboarding,
}: CareerMissionViewProps) {
  const [mission, setMission] = useState<CareerMission | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeSubTab, setActiveSubTab] = useState<'roadmap' | 'proposals' | 'versions'>('roadmap');

  // Modals & Drawers state
  const [selectedTaskHistory, setSelectedTaskHistory] = useState<{
    task: MissionTask;
    events: TaskProgressEvent[];
  } | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  const [overrideTask, setOverrideTask] = useState<MissionTask | null>(null);
  const [overrideReasonInput, setOverrideReasonInput] = useState('');
  const [overrideSubmitting, setOverrideSubmitting] = useState(false);

  const [linkEvidenceTask, setLinkEvidenceTask] = useState<MissionTask | null>(null);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<number | ''>('');
  const [evidenceLinkNotes, setEvidenceLinkNotes] = useState('');
  const [evidenceLinking, setEvidenceLinking] = useState(false);

  const [proposals, setProposals] = useState<MissionProposal[]>([]);
  const [proposalsLoading, setProposalsLoading] = useState(false);

  const [versions, setVersions] = useState<any[]>([]);
  const [inspectVersion, setInspectVersion] = useState<MissionVersionDetail | null>(null);

  // Proposal creation modal
  const [showSimulateModal, setShowSimulateModal] = useState(false);
  const [simRole, setSimRole] = useState(availableRoles[1]?.role_id || 'backend-api-intern');
  const [simTitle, setSimTitle] = useState('Strategic Pivot to Backend Platform Role');
  const [simRationale, setSimRationale] = useState('Aligning mission tasks with upcoming platform engineering internship opening.');
  const [simulating, setSimulating] = useState(false);
  const [actionSuccessMsg, setActionSuccessMsg] = useState('');

  // Fetch active mission
  async function fetchActiveMission() {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/v1/missions/active');
      if (res.status === 404) {
        setMission(null);
        return;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const data: CareerMission = await res.json();
      setMission(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch mission');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchActiveMission();
  }, []);

  // Fetch proposals when switching to proposals tab
  async function fetchProposals(missionId: number) {
    setProposalsLoading(true);
    try {
      const res = await fetch(`/v1/missions/${missionId}/proposals`);
      if (res.ok) {
        setProposals(await res.json());
      }
    } catch (err) {
      console.error('Error fetching proposals:', err);
    } finally {
      setProposalsLoading(false);
    }
  }

  // Fetch version history
  async function fetchVersions(missionId: number) {
    try {
      const res = await fetch(`/v1/missions/${missionId}/versions`);
      if (res.ok) {
        setVersions(await res.json());
      }
    } catch (err) {
      console.error('Error fetching versions:', err);
    }
  }

  useEffect(() => {
    if (mission?.id) {
      if (activeSubTab === 'proposals') {
        fetchProposals(mission.id);
      } else if (activeSubTab === 'versions') {
        fetchVersions(mission.id);
      }
    }
  }, [activeSubTab, mission?.id]);

  function notifySuccess(msg: string) {
    setActionSuccessMsg(msg);
    setTimeout(() => setActionSuccessMsg(''), 4000);
  }

  // Update Task Status
  async function handleUpdateStatus(task: MissionTask, newStatus: string, overrideReason?: string) {
    if (!mission) return;

    if (newStatus === 'completed' && !task.is_unlocked && !overrideReason) {
      // Trigger override modal
      setOverrideTask(task);
      setOverrideReasonInput('');
      return;
    }

    try {
      const payload: any = { status: newStatus };
      if (overrideReason) {
        payload.override_reason = overrideReason;
      }

      const res = await fetch(`/v1/missions/${mission.id}/tasks/${task.id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }

      notifySuccess(`Task "${task.skill_name}" marked as ${newStatus.replace('_', ' ')}.`);
      fetchActiveMission();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update task status');
    }
  }

  // Submit Override Reason
  async function submitOverride() {
    if (!overrideTask || !overrideReasonInput.trim()) {
      alert('Please provide a reason to bypass prerequisite dependencies.');
      return;
    }
    setOverrideSubmitting(true);
    await handleUpdateStatus(overrideTask, 'completed', overrideReasonInput.trim());
    setOverrideSubmitting(false);
    setOverrideTask(null);
  }

  // View Task History
  async function openTaskHistory(task: MissionTask) {
    if (!mission) return;
    setHistoryLoading(true);
    setSelectedTaskHistory({ task, events: [] });
    try {
      const res = await fetch(`/v1/missions/${mission.id}/tasks/${task.id}/history`);
      if (res.ok) {
        const events = await res.json();
        setSelectedTaskHistory({ task, events });
      }
    } catch (err) {
      console.error('Failed to load history:', err);
    } finally {
      setHistoryLoading(false);
    }
  }

  // Link Evidence Submit
  async function submitLinkEvidence() {
    if (!mission || !linkEvidenceTask || !selectedEvidenceId) return;
    setEvidenceLinking(true);
    try {
      const res = await fetch(`/v1/missions/${mission.id}/tasks/${linkEvidenceTask.id}/evidence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          evidence_id: Number(selectedEvidenceId),
          notes: evidenceLinkNotes.trim(),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      notifySuccess(`Evidence attached to "${linkEvidenceTask.skill_name}".`);
      setLinkEvidenceTask(null);
      fetchActiveMission();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to link evidence');
    } finally {
      setEvidenceLinking(false);
    }
  }

  // Simulate / Create Change Proposal
  async function handleCreateProposal() {
    if (!mission) return;
    setSimulating(true);
    try {
      const res = await fetch(`/v1/missions/${mission.id}/proposals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          proposal_title: simTitle.trim(),
          rationale: simRationale.trim(),
          target_role_id: simRole,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      notifySuccess('Change Proposal created successfully for student review.');
      setShowSimulateModal(false);
      setActiveSubTab('proposals');
      fetchProposals(mission.id);
      fetchActiveMission();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to create proposal');
    } finally {
      setSimulating(false);
    }
  }

  // Approve Proposal
  async function handleApproveProposal(proposalId: number) {
    if (!mission) return;
    const confirmApprove = window.confirm(
      'Are you sure you want to approve this proposal? This will create an immutable next version and preserve all completed milestone progress.'
    );
    if (!confirmApprove) return;

    try {
      const res = await fetch(`/v1/missions/${mission.id}/proposals/${proposalId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision_notes: 'Approved roadmap update via Human-in-the-Loop review.',
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      notifySuccess('Mission version updated successfully! Completed milestones preserved.');
      fetchActiveMission();
      fetchProposals(mission.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to approve proposal');
    }
  }

  // Reject Proposal
  async function handleRejectProposal(proposalId: number) {
    if (!mission) return;
    const reason = window.prompt('Optional feedback / reason for rejection:') ?? '';
    try {
      const res = await fetch(`/v1/missions/${mission.id}/proposals/${proposalId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision_notes: reason }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      notifySuccess('Proposal rejected. Active mission remains unchanged.');
      fetchProposals(mission.id);
      fetchActiveMission();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to reject proposal');
    }
  }

  // Create initial mission from planner if none exists
  async function handleCreateInitialMission() {
    setLoading(true);
    try {
      const res = await fetch('/v1/missions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_role_id: availableRoles[0]?.role_id || 'distributed-systems-intern',
          weekly_hours: 15,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      notifySuccess('Career Mission initialized from curriculum graph.');
      fetchActiveMission();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initialize mission');
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="mission-loading-state">
        <div className="spinner"></div>
        <p>Loading your active Career Mission & roadmap...</p>
      </div>
    );
  }

  if (error && !mission) {
    return (
      <div className="mission-error-state">
        <span className="error-icon">⚠️</span>
        <h3>Failed to load Career Mission</h3>
        <p>{error}</p>
        <button className="btn-primary" onClick={fetchActiveMission}>
          Retry
        </button>
      </div>
    );
  }

  if (!mission) {
    return (
      <div className="mission-empty-state">
        <div className="empty-badge">CAREER MISSION WORKSPACE</div>
        <h2>No Active Career Mission Found</h2>
        <p className="empty-sub">
          Transform your prerequisite-aware learning path into an actionable, persistent Career
          Mission with verifiable milestones, audit logging, and human-approved replanning.
        </p>
        <div className="empty-actions">
          {onStartOnboarding ? (
            <button
              id="btn-init-mission"
              className="btn-primary btn-large"
              onClick={onStartOnboarding}
            >
              🚀 Launch Guided Onboarding →
            </button>
          ) : (
            <button
              id="btn-init-mission"
              className="btn-primary"
              onClick={handleCreateInitialMission}
            >
              🎯 Create Career Mission for {availableRoles[0]?.title || 'Target Role'}
            </button>
          )}
          <button className="btn-secondary" onClick={onNavigateToPlanner}>
            🎯 Browse Careers Catalogue
          </button>
        </div>
      </div>
    );
  }

  const activeVersion = mission.active_version;
  const stages = activeVersion?.stages || [];

  return (
    <div className="career-mission-container">
      {/* Toast Notification */}
      {actionSuccessMsg && (
        <div className="mission-toast-success">
          <span>✓</span> {actionSuccessMsg}
        </div>
      )}

      {/* Header Eyebrow & Title */}
      <div className="mission-header-row">
        <div>
          <div className="eyebrow">PERSISTENT CAREER MISSION • STAGE 3.3</div>
          <h1 className="mission-main-title">{mission.title}</h1>
          <p className="mission-subtitle">
            Goal: <b>{mission.target_role_title || mission.target_role_id}</b> • Track your
            progress across prerequisite-sound stages, attach portfolio evidence, and govern
            staged AI plan adjustments.
          </p>
        </div>
        <div className="mission-header-actions">
          <button
            id="btn-simulate-proposal"
            className="btn-action-simulate"
            onClick={() => setShowSimulateModal(true)}
            title="Stage a proposed revision to test human-in-the-loop review"
          >
            ⚡ Propose Plan Change
          </button>
        </div>
      </div>

      {/* Overview Metric Cards */}
      <div className="mission-overview-grid">
        <div className="metric-card progress-card">
          <div className="card-label">MISSION READINESS</div>
          <div className="progress-num-row">
            <span className="big-stat">{mission.progress_percent}%</span>
            <span className="sub-stat">
              {mission.completed_tasks} / {mission.total_tasks} Tasks Complete
            </span>
          </div>
          <div className="progress-bar-track">
            <div
              className="progress-bar-fill"
              style={{ width: `${Math.min(100, mission.progress_percent)}%` }}
            ></div>
          </div>
          <div className="card-footer-info">
            {mission.in_progress_tasks > 0 ? (
              <span>⚡ {mission.in_progress_tasks} task(s) currently in progress</span>
            ) : (
              <span>Ready for next milestone</span>
            )}
          </div>
        </div>

        <div className="metric-card effort-card">
          <div className="card-label">ESTIMATED REMAINING EFFORT</div>
          <div className="big-stat">
            {mission.estimated_remaining_hours_min}–{mission.estimated_remaining_hours_max}{' '}
            <small>hrs</small>
          </div>
          <div className="card-footer-info">
            Illustrative benchmark • ~
            {Math.max(
              1,
              Math.ceil(mission.estimated_remaining_hours_max / (mission.weekly_hours || 10))
            )}{' '}
            wks at {mission.weekly_hours}h/week
          </div>
        </div>

        <div className="metric-card governance-card">
          <div className="card-label">PLAN GOVERNANCE</div>
          <div className="governance-status-row">
            <span className="version-pill">Version {mission.active_version_number}.0</span>
            <span className="status-pill-active">● {mission.status.toUpperCase()}</span>
          </div>
          <div className="card-footer-info">
            {mission.pending_proposals_count > 0 ? (
              <span className="pending-badge">
                ⚠️ {mission.pending_proposals_count} Pending Revision Proposal(s)
              </span>
            ) : (
              <span>All changes approved & up to date</span>
            )}
          </div>
        </div>
      </div>

      {/* Sub-Tabs Navigation */}
      <div className="mission-tabs-nav">
        <button
          id="tab-roadmap"
          className={`mission-tab-btn ${activeSubTab === 'roadmap' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('roadmap')}
        >
          🗺 Mission Roadmap ({mission.total_tasks} Milestones)
        </button>
        <button
          id="tab-proposals"
          className={`mission-tab-btn ${activeSubTab === 'proposals' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('proposals')}
        >
          ⚖ Change Proposals{' '}
          {mission.pending_proposals_count > 0 && (
            <span className="tab-counter-badge">{mission.pending_proposals_count}</span>
          )}
        </button>
        <button
          id="tab-versions"
          className={`mission-tab-btn ${activeSubTab === 'versions' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('versions')}
        >
          📜 Version History (v{mission.active_version_number}.0)
        </button>
      </div>

      {/* ========================================================= */}
      {/* SUB-TAB 1: ROADMAP & TASKS                                */}
      {/* ========================================================= */}
      {activeSubTab === 'roadmap' && (
        <div className="roadmap-container">
          {stages.length === 0 ? (
            <div className="panel p-4">No stages found in this plan.</div>
          ) : (
            stages.map((stage) => {
              const stagePct =
                stage.total_tasks > 0
                  ? Math.round((stage.completed_tasks / stage.total_tasks) * 100)
                  : 0;

              return (
                <div key={stage.stage_number} className="stage-section">
                  <div className="stage-header-card">
                    <div className="stage-title-group">
                      <span className="stage-badge">STAGE {stage.stage_number}</span>
                      <h3 className="stage-title-text">{stage.stage_title}</h3>
                    </div>
                    <div className="stage-meta-group">
                      <span className="stage-hours-meta">
                        ⏱ {stage.stage_hours_min}–{stage.stage_hours_max} hrs
                      </span>
                      <span className="stage-progress-meta">
                        {stage.completed_tasks}/{stage.total_tasks} Complete ({stagePct}%)
                      </span>
                    </div>
                  </div>

                  <div className="stage-tasks-grid">
                    {stage.tasks.map((task) => {
                      const isCompleted = task.status === 'completed';
                      const isInProgress = task.status === 'in_progress';

                      return (
                        <div
                          key={task.id}
                          id={`task-card-${task.id}`}
                          className={`task-card status-${task.status} ${
                            !task.is_unlocked && !isCompleted ? 'locked' : ''
                          }`}
                        >
                          <div className="task-card-top">
                            <div className="task-badges-row">
                              <span className="badge-category">{task.category}</span>
                              <span className={`badge-status ${task.status}`}>
                                {task.status === 'completed'
                                  ? '✓ Completed'
                                  : task.status === 'in_progress'
                                  ? '⚡ In Progress'
                                  : 'Not Started'}
                              </span>
                              {!task.is_unlocked && !isCompleted && (
                                <span
                                  className="badge-locked"
                                  title="Prerequisites must be completed first or explicitly overridden"
                                >
                                  🔒 Locked
                                </span>
                              )}
                              {task.evidence_id && (
                                <span className="badge-evidence-linked" title="Evidence attached">
                                  📎 Evidence Attached
                                </span>
                              )}
                            </div>

                            <span className="task-effort-tag">
                              {task.estimated_hours_min}–{task.estimated_hours_max}h
                            </span>
                          </div>

                          <h4 className="task-skill-heading">
                            {task.skill_name}{' '}
                            <span className="level-progression">
                              (L{task.current_level} ➔ L{task.target_level})
                            </span>
                          </h4>

                          {/* Completion criteria */}
                          <div className="criteria-box">
                            <div className="criteria-title">COMPLETION CRITERIA:</div>
                            <p className="criteria-text">{task.completion_criteria}</p>
                          </div>

                          {/* Prerequisites summary */}
                          {task.prerequisite_task_keys.length > 0 && (
                            <div className="task-prereqs-info">
                              <span className="prereq-label">Prerequisites:</span>
                              {task.prerequisite_task_keys.map((k) => (
                                <span key={k} className="prereq-chip">
                                  {k.replace('task_skill_', 'Skill ').replace('_lvl_', ' Level ')}
                                </span>
                              ))}
                            </div>
                          )}

                          {/* Completed audit info */}
                          {task.override_reason && (
                            <div className="override-flag">
                              <b>Prerequisite Override:</b> {task.override_reason}
                            </div>
                          )}

                          {/* Action Buttons */}
                          <div className="task-card-actions">
                            {task.status === 'not_started' && (
                              <button
                                id={`btn-start-${task.id}`}
                                className="btn-task-action btn-start"
                                onClick={() => handleUpdateStatus(task, 'in_progress')}
                              >
                                ▶ Start Task
                              </button>
                            )}

                            {isInProgress && (
                              <button
                                id={`btn-complete-${task.id}`}
                                className="btn-task-action btn-complete"
                                onClick={() => handleUpdateStatus(task, 'completed')}
                              >
                                ✓ Mark Complete
                              </button>
                            )}

                            {isCompleted && (
                              <button
                                className="btn-task-action btn-reopen"
                                onClick={() => handleUpdateStatus(task, 'in_progress')}
                                title="Reopen task if additional study is needed"
                              >
                                ↺ Reopen
                              </button>
                            )}

                            <button
                              id={`btn-evidence-${task.id}`}
                              className="btn-task-action btn-evidence"
                              onClick={() => {
                                setLinkEvidenceTask(task);
                                setSelectedEvidenceId(task.evidence_id || '');
                                setEvidenceLinkNotes('');
                              }}
                            >
                              📎 Evidence
                            </button>

                            <button
                              id={`btn-history-${task.id}`}
                              className="btn-task-action btn-history"
                              onClick={() => openTaskHistory(task)}
                            >
                              📜 History
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* ========================================================= */}
      {/* SUB-TAB 2: PROPOSALS & PLAN GOVERNANCE                     */}
      {/* ========================================================= */}
      {activeSubTab === 'proposals' && (
        <div className="proposals-container">
          <div className="proposals-top-info">
            <div>
              <h3>Human-in-the-Loop Plan Change Governance</h3>
              <p>
                In InternPath AI, the AI agent or system planner never silently alters your approved
                Career Mission. Proposed changes are staged as formal proposals displaying full
                before/after differences.
              </p>
            </div>
            <button
              className="btn-primary"
              onClick={() => setShowSimulateModal(true)}
            >
              ⚡ Stage New Change Proposal
            </button>
          </div>

          {proposalsLoading ? (
            <div className="loading-box">Loading proposals...</div>
          ) : proposals.length === 0 ? (
            <div className="panel empty-proposals-panel">
              <h4>No Change Proposals Pending</h4>
              <p>
                Your active Career Mission matches your target role. You can stage a revision at any
                time to explore shifting target positions or adjusting scope.
              </p>
            </div>
          ) : (
            <div className="proposals-list">
              {proposals.map((prop) => {
                const diff = prop.diff_summary || {};
                const added = diff.added_tasks || [];
                const removed = diff.removed_tasks || [];
                const retained = diff.retained_tasks || [];
                const effortDelta = diff.effort_delta || { min_hours: 0, max_hours: 0 };
                const isPending = prop.status === 'pending';

                return (
                  <div
                    key={prop.id}
                    id={`proposal-card-${prop.id}`}
                    className={`proposal-card status-${prop.status}`}
                  >
                    <div className="proposal-card-header">
                      <div>
                        <div className="proposal-tag-row">
                          <span className={`proposal-status-pill ${prop.status}`}>
                            {prop.status.toUpperCase()}
                          </span>
                          <span className="proposal-meta-pill">
                            Targets Base Version {prop.base_version_number}.0
                          </span>
                          <span className="proposal-actor-pill">
                            Proposed by: {prop.proposed_by}
                          </span>
                        </div>
                        <h3 className="proposal-title">{prop.proposal_title}</h3>
                        <p className="proposal-rationale">{prop.rationale}</p>
                      </div>

                      {isPending && (
                        <div className="proposal-actions">
                          <button
                            id={`btn-approve-proposal-${prop.id}`}
                            className="btn-approve"
                            onClick={() => handleApproveProposal(prop.id)}
                          >
                            ✓ Approve & Bump to v{mission.active_version_number! + 1}.0
                          </button>
                          <button
                            id={`btn-reject-proposal-${prop.id}`}
                            className="btn-reject"
                            onClick={() => handleRejectProposal(prop.id)}
                          >
                            ✕ Reject
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Diff Inspection Grid */}
                    <div className="proposal-diff-grid">
                      <div className="diff-column added">
                        <div className="diff-header">🟢 Added Milestones ({added.length})</div>
                        {added.length === 0 ? (
                          <div className="diff-empty">No new tasks added</div>
                        ) : (
                          added.map((t: any, i: number) => (
                            <div key={i} className="diff-item">
                              + {t.skill_name} (Level {t.target_level})
                            </div>
                          ))
                        )}
                      </div>

                      <div className="diff-column removed">
                        <div className="diff-header">🔴 Removed Tasks ({removed.length})</div>
                        {removed.length === 0 ? (
                          <div className="diff-empty">No tasks pruned</div>
                        ) : (
                          removed.map((t: any, i: number) => (
                            <div key={i} className="diff-item">
                              - {t.skill_name} (Level {t.target_level})
                            </div>
                          ))
                        )}
                      </div>

                      <div className="diff-column retained">
                        <div className="diff-header">
                          🔵 Retained Work Preserved ({retained.length})
                        </div>
                        {retained.length === 0 ? (
                          <div className="diff-empty">No overlapping tasks</div>
                        ) : (
                          retained.map((t: any, i: number) => (
                            <div key={i} className="diff-item">
                              • {t.skill_name} (Status: {t.preserved_status})
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                    <div className="proposal-footer-meta">
                      <span>
                        <b>Effort Impact:</b>{' '}
                        {effortDelta.min_hours >= 0 ? `+${effortDelta.min_hours}` : effortDelta.min_hours} to{' '}
                        {effortDelta.max_hours >= 0 ? `+${effortDelta.max_hours}` : effortDelta.max_hours} hrs
                      </span>
                      {prop.decided_at && (
                        <span>
                          Decided on {new Date(prop.decided_at).toLocaleString()} by{' '}
                          {prop.decided_by}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ========================================================= */}
      {/* SUB-TAB 3: VERSION HISTORY                                */}
      {/* ========================================================= */}
      {activeSubTab === 'versions' && (
        <div className="versions-container">
          <h3>Immutable Mission Version Snapshots</h3>
          <p>
            Every approved change creates a permanent, immutable version record. Completed work and
            historical evidence remain accessible for verification and competition auditing.
          </p>

          <div className="versions-list">
            {versions.map((ver) => (
              <div key={ver.id} className={`version-card ${ver.is_active ? 'active-version' : ''}`}>
                <div className="version-card-header">
                  <div>
                    <div className="version-badge-row">
                      <span className="ver-badge">Version {ver.version_number}.0</span>
                      {ver.is_active ? (
                        <span className="ver-active-pill">● ACTIVE VERSION</span>
                      ) : (
                        <span className="ver-archived-pill">ARCHIVED SNAPSHOT</span>
                      )}
                    </div>
                    <h4>{ver.title}</h4>
                    <p className="ver-rationale">{ver.rationale}</p>
                  </div>
                  <div className="ver-stats">
                    <div><b>Tasks:</b> {ver.total_tasks}</div>
                    <div><b>Effort:</b> {ver.total_estimated_hours_min}–{ver.total_estimated_hours_max} hrs</div>
                  </div>
                </div>

                <div className="version-footer-meta">
                  <span>Approved by: <b>{ver.approved_by || 'Alex Chen'}</b></span>
                  <span>Approved at: {ver.approved_at ? new Date(ver.approved_at).toLocaleString() : 'N/A'}</span>
                  <button
                    className="btn-task-action btn-history"
                    onClick={async () => {
                      try {
                        const res = await fetch(`/v1/missions/${mission.id}/versions/${ver.version_number}`);
                        if (res.ok) {
                          setInspectVersion(await res.json());
                        }
                      } catch (err) {
                        console.error('Failed to load version snapshot:', err);
                      }
                    }}
                  >
                    🔍 Inspect Roadmap Snapshot
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Snapshot Modal */}
      {inspectVersion && (
        <div className="modal-backdrop">
          <div className="modal-content" style={{ maxWidth: '640px' }}>
            <div className="modal-header">
              <h3>📜 Snapshot: Version {inspectVersion.version_number}.0</h3>
              <button className="modal-close" onClick={() => setInspectVersion(null)}>✕</button>
            </div>
            <div className="modal-body">
              <p><b>Title:</b> {inspectVersion.title}</p>
              <p><b>Rationale:</b> {inspectVersion.rationale}</p>
              <div style={{ marginTop: '14px' }}>
                <h4>Roadmap Stages ({inspectVersion.tasks.length} Milestones):</h4>
                {inspectVersion.stages.map((stg) => (
                  <div key={stg.stage_number} style={{ marginBottom: '12px', background: '#f8fafc', padding: '10px 14px', borderRadius: '8px' }}>
                    <strong>Stage {stg.stage_number}: {stg.stage_title}</strong>
                    <ul style={{ margin: '6px 0 0 16px', fontSize: '12px', color: '#475569' }}>
                      {stg.tasks.map((t) => (
                        <li key={t.id}>
                          <b>{t.skill_name}</b> (Target Level {t.target_level}) — Status: <span style={{ fontWeight: 600 }}>{t.status}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setInspectVersion(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* MODAL 1: PREREQUISITE OVERRIDE DIALOG                     */}
      {/* ========================================================= */}
      {overrideTask && (
        <div className="modal-backdrop">
          <div className="modal-content">
            <div className="modal-header">
              <h3>🔒 Prerequisite Dependency Notice</h3>
              <button className="modal-close" onClick={() => setOverrideTask(null)}>
                ✕
              </button>
            </div>
            <div className="modal-body">
              <p>
                Milestone <b>{overrideTask.skill_name}</b> has prerequisite dependencies that are
                not marked as completed in your roadmap.
              </p>
              <p className="notice-sub">
                To complete this task ahead of prerequisite dependencies, you must provide an explicit,
                audited reason (e.g., prior university coursework, external certifications, or
                equivalent work experience).
              </p>

              <label className="modal-label">Override Reason (Required):</label>
              <textarea
                id="input-override-reason"
                className="modal-textarea"
                rows={3}
                placeholder="e.g. Completed advanced university course on operating systems; certified via AWS Practitioner."
                value={overrideReasonInput}
                onChange={(e) => setOverrideReasonInput(e.target.value)}
              />
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setOverrideTask(null)}>
                Cancel
              </button>
              <button
                id="btn-confirm-override"
                className="btn-primary"
                onClick={submitOverride}
                disabled={overrideSubmitting || !overrideReasonInput.trim()}
              >
                {overrideSubmitting ? 'Recording...' : 'Submit Override & Complete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* MODAL 2: LINK EVIDENCE DIALOG                             */}
      {/* ========================================================= */}
      {linkEvidenceTask && (
        <div className="modal-backdrop">
          <div className="modal-content">
            <div className="modal-header">
              <h3>📎 Attach Portfolio Evidence to Milestone</h3>
              <button className="modal-close" onClick={() => setLinkEvidenceTask(null)}>
                ✕
              </button>
            </div>
            <div className="modal-body">
              <p>
                Linking supporting artifacts to <b>{linkEvidenceTask.skill_name}</b> provides verifiable
                proof of competency for your portfolio and AI readiness evaluation.
              </p>

              <label className="modal-label">Select Evidence Item:</label>
              {evidenceList.length === 0 ? (
                <div className="empty-evidence-hint">
                  No evidence items created yet in profile. Go to the profile or add one below.
                </div>
              ) : (
                <select
                  id="select-evidence"
                  className="modal-select"
                  value={selectedEvidenceId}
                  onChange={(e) => setSelectedEvidenceId(Number(e.target.value))}
                >
                  <option value="">-- Choose from your portfolio items --</option>
                  {evidenceList.map((ev) => (
                    <option key={ev.id} value={ev.id}>
                      #{ev.id} • {ev.title} ({ev.evidence_type})
                    </option>
                  ))}
                </select>
              )}

              <label className="modal-label mt-3">Attachment Notes (Optional):</label>
              <input
                type="text"
                className="modal-input"
                placeholder="e.g. Demonstrates heap allocation benchmarks."
                value={evidenceLinkNotes}
                onChange={(e) => setEvidenceLinkNotes(e.target.value)}
              />
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setLinkEvidenceTask(null)}>
                Cancel
              </button>
              <button
                id="btn-confirm-evidence"
                className="btn-primary"
                onClick={submitLinkEvidence}
                disabled={evidenceLinking || !selectedEvidenceId}
              >
                {evidenceLinking ? 'Attaching...' : 'Link Evidence Item'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* MODAL 3: AUDIT HISTORY DIALOG                             */}
      {/* ========================================================= */}
      {selectedTaskHistory && (
        <div className="modal-backdrop">
          <div className="modal-content">
            <div className="modal-header">
              <h3>📜 Audit Trail: {selectedTaskHistory.task.skill_name}</h3>
              <button className="modal-close" onClick={() => setSelectedTaskHistory(null)}>
                ✕
              </button>
            </div>
            <div className="modal-body">
              {historyLoading ? (
                <div>Loading audit history...</div>
              ) : selectedTaskHistory.events.length === 0 ? (
                <div>No events recorded for this milestone yet.</div>
              ) : (
                <div className="audit-timeline">
                  {selectedTaskHistory.events.map((ev) => (
                    <div key={ev.id} className="audit-event-item">
                      <div className="audit-event-dot"></div>
                      <div className="audit-event-content">
                        <div className="audit-event-top">
                          <span className="audit-transition">
                            {ev.from_status} ➔ <b>{ev.to_status}</b>
                          </span>
                          <span className="audit-time">
                            {ev.created_at ? new Date(ev.created_at).toLocaleString() : ''}
                          </span>
                        </div>
                        <p className="audit-notes">{ev.notes}</p>
                        <span className="audit-actor">Actor: {ev.actor}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setSelectedTaskHistory(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* MODAL 4: SIMULATE / CREATE CHANGE PROPOSAL DIALOG         */}
      {/* ========================================================= */}
      {showSimulateModal && (
        <div className="modal-backdrop">
          <div className="modal-content">
            <div className="modal-header">
              <h3>⚡ Stage a Career Mission Change Proposal</h3>
              <button className="modal-close" onClick={() => setShowSimulateModal(false)}>
                ✕
              </button>
            </div>
            <div className="modal-body">
              <p className="notice-sub">
                Simulate how the system stages plan changes before applying them. The topological engine
                will re-solve prerequisites for the target and calculate a transparent diff.
              </p>

              <label className="modal-label">Target Role Focus:</label>
              <select
                className="modal-select"
                value={simRole}
                onChange={(e) => setSimRole(e.target.value)}
              >
                {availableRoles.map((r) => (
                  <option key={r.role_id} value={r.role_id}>
                    {r.title} ({r.role_id})
                  </option>
                ))}
              </select>

              <label className="modal-label mt-3">Proposal Title:</label>
              <input
                type="text"
                className="modal-input"
                value={simTitle}
                onChange={(e) => setSimTitle(e.target.value)}
              />

              <label className="modal-label mt-3">Rationale & Purpose:</label>
              <textarea
                className="modal-textarea"
                rows={3}
                value={simRationale}
                onChange={(e) => setSimRationale(e.target.value)}
              />
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowSimulateModal(false)}>
                Cancel
              </button>
              <button
                id="btn-submit-proposal"
                className="btn-primary"
                onClick={handleCreateProposal}
                disabled={simulating || !simTitle.trim() || !simRationale.trim()}
              >
                {simulating ? 'Evaluating & Staging...' : 'Generate Change Proposal'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
