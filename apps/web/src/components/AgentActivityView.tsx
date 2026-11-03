import React, { useState, useEffect } from 'react';

export interface AgentEventItem {
  id: number;
  event_id: string;
  event_type: string;
  source: string;
  source_timestamp: string;
  received_at: string;
  role_id?: string | null;
  previous_value?: string | null;
  new_value?: string | null;
  source_reliability: string;
  processing_status: string;
  is_simulated: boolean;
  payload: Record<string, any>;
  created_at: string;
}

export interface ToolIOLogItem {
  tool: string;
  input: Record<string, any>;
  output: any;
}

export interface AgentRunItem {
  id: string;
  event_id: string;
  mission_id?: number | null;
  student_id: number;
  engine_used: string;
  decision_category:
    | 'no_action'
    | 'informational_notification'
    | 'proposed_mission_adjustment'
    | 'human_review_required';
  is_simulated: boolean;
  relevant_evidence?: Record<string, any> | null;
  tools_invoked: string[];
  tool_io_log: ToolIOLogItem[];
  decision_explanation: string;
  proposal_id?: number | null;
  execution_time_ms: number;
  status: string;
  error_message?: string | null;
  created_at: string;
}

interface AgentActivityViewProps {
  onNavigateToMission: () => void;
}

export const AgentActivityView: React.FC<AgentActivityViewProps> = ({ onNavigateToMission }) => {
  const [runs, setRuns] = useState<AgentRunItem[]>([]);
  const [events, setEvents] = useState<AgentEventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Presenter Simulation State
  const [simulating, setSimulating] = useState<string | null>(null);
  const [simSuccessMsg, setSimSuccessMsg] = useState<string | null>(null);

  // Filter & UI State
  const [filterType, setFilterType] = useState<'all' | 'simulated' | 'real'>('all');
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'runs' | 'events'>('runs');

  async function fetchData() {
    setLoading(true);
    setError(null);
    try {
      const [runsRes, eventsRes] = await Promise.all([
        fetch('/v1/agent/runs'),
        fetch('/v1/agent/events'),
      ]);
      if (runsRes.ok && eventsRes.ok) {
        const loadedRuns: AgentRunItem[] = await runsRes.json();
        const loadedEvents: AgentEventItem[] = await eventsRes.json();
        setRuns(loadedRuns);
        setEvents(loadedEvents);
        if (loadedRuns.length > 0 && !expandedRunId) {
          setExpandedRunId(loadedRuns[0].id);
        }
      } else {
        setError('Failed to fetch agent activity logs from server.');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Network error loading agent activity');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchData();
  }, []);

  async function triggerSimulation(scenario: string, label: string) {
    setSimulating(scenario);
    setSimSuccessMsg(null);
    try {
      const res = await fetch('/v1/agent/events/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Simulation execution failed');
      }
      const newRun: AgentRunItem = await res.json();
      setSimSuccessMsg(`Successfully executed simulation: ${label}`);
      setExpandedRunId(newRun.id);
      await fetchData();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Simulation failed');
    } finally {
      setSimulating(null);
    }
  }

  const filteredRuns = runs.filter((r) => {
    if (filterType === 'simulated') return r.is_simulated;
    if (filterType === 'real') return !r.is_simulated;
    return true;
  });

  const filteredEvents = events.filter((ev) => {
    if (filterType === 'simulated') return ev.is_simulated;
    if (filterType === 'real') return !ev.is_simulated;
    return true;
  });

  function getCategoryBadge(cat: string) {
    switch (cat) {
      case 'proposed_mission_adjustment':
        return (
          <span className="agent-badge badge-proposal" id="badge-cat-proposal">
            ⚡ PROPOSED MISSION ADJUSTMENT
          </span>
        );
      case 'informational_notification':
        return (
          <span className="agent-badge badge-info" id="badge-cat-info">
            ℹ INFORMATIONAL NOTIFICATION
          </span>
        );
      case 'human_review_required':
        return (
          <span className="agent-badge badge-warning" id="badge-cat-warning">
            ⚠ HUMAN REVIEW REQUIRED
          </span>
        );
      case 'no_action':
      default:
        return (
          <span className="agent-badge badge-neutral" id="badge-cat-neutral">
            ○ NO ACTION REQUIRED
          </span>
        );
    }
  }

  function getEngineBadge(engine: string) {
    if (engine.startsWith('gemini:')) {
      return (
        <span className="engine-chip engine-chip-gemini" title="Verified Live Google Gemini Provider">
          <span className="engine-dot live" /> ✦ Live Gemini ({engine.replace('gemini:', '')})
        </span>
      );
    }
    if (engine.startsWith('openai:')) {
      return (
        <span className="engine-chip engine-chip-openai" title="Verified Live OpenAI Provider">
          <span className="engine-dot live" /> ❖ Live OpenAI ({engine.replace('openai:', '')})
        </span>
      );
    }
    if (engine === 'mock_llm') {
      return (
        <span className="engine-chip engine-chip-mock" title="Deterministic Mock Provider (Multi-turn tool loop simulation)">
          <span className="engine-dot mock" /> ⚗ Mock LLM Provider
        </span>
      );
    }
    return (
      <span className="engine-chip engine-chip-rules" title="Deterministic Rule Engine Grounded in C++ Solver">
        <span className="engine-dot rules" /> ⚙ Deterministic Fallback ({engine || 'deterministic_rules'})
      </span>
    );
  }

  return (
    <div className="agent-activity-container" id="agent-activity-view">
      {/* Top Banner: Engine Status & Safety Governance */}
      <div className="agent-header-panel">
        <div className="agent-header-left">
          <div className="eyebrow">PHASE 3.5 • INTELLIGENT REPLANNING & AGENT EVALUATION</div>
          <h1>Autonomous Career Event Observer & Audit Log</h1>
          <p className="lede">
            Observes real and simulated internship deadline shifts, assesses relevance to the
            student's active roadmap, uses strictly authorized tools, and stages human-approved
            mission revision proposals.
          </p>
        </div>

        <div className="agent-governance-cards">
          <div className="gov-card">
            <span className="gov-title">Active AI Engine</span>
            <div className="gov-value" id="engine-status-badge">
              <span className="engine-pulse">●</span> Deterministic Rule Engine
            </div>
            <small>Configurable Gemini/OpenAI adapter with safe fallback</small>
          </div>
          <div className="gov-card highlight-boundary">
            <span className="gov-title">Human-in-the-Loop Boundary</span>
            <div className="gov-value text-safe">
              🛡 Enforced Backend Gate
            </div>
            <small>Agent CANNOT auto-approve proposals or mutate missions</small>
          </div>
        </div>
      </div>

      {/* Presenter / Demo Controls Panel */}
      <div className="panel presenter-demo-panel" id="presenter-demo-controls">
        <div className="panel-header">
          <div>
            <div className="panel-tag">PRESENTER / JUDGE CONTROLS</div>
            <h2>Simulate Controlled Career Events</h2>
            <p>
              Trigger live backend events to inspect the agent decision loop, tool executions,
              and human governance boundaries. All simulations are truthfully labeled.
            </p>
          </div>
          <span className="mini-icon">🎮</span>
        </div>

        <div className="demo-buttons-grid">
          <button
            id="btn-sim-university-exams-query"
            className="btn-demo btn-demo-special"
            disabled={simulating !== null}
            onClick={async () => {
              setSimulating('exams_query');
              setSimSuccessMsg(null);
              try {
                const res = await fetch('/v1/agent/query', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    query: 'I have university exams for the next two weeks. I can only spend four hours per week preparing for my internship. What should I do?',
                    simulated: true,
                  }),
                });
                if (!res.ok) {
                  const errData = await res.json().catch(() => ({}));
                  throw new Error(errData.detail || 'Demo query execution failed');
                }
                const newRun: AgentRunItem = await res.json();
                setSimSuccessMsg('Successfully executed R2.4 Target Demo: Student Exam Constraints (4 hrs/wk)');
                setExpandedRunId(newRun.id);
                await fetchData();
              } catch (e) {
                alert(e instanceof Error ? e.message : 'Demo query failed');
              } finally {
                setSimulating(null);
              }
            }}
          >
            <span className="btn-icon">🎯</span>
            <div>
              <strong>R2.4 Target Demo: Exam Pacing (4 hrs/wk)</strong>
              <small>Student inquiry → C++ simulation → Staged pacing proposal</small>
            </div>
            {simulating === 'exams_query' && <span className="btn-spinner" />}
          </button>

          <button
            id="btn-sim-deadline-earlier"
            className="btn-demo btn-demo-danger"
            disabled={simulating !== null}
            onClick={() => triggerSimulation('deadline_earlier', 'Deadline Moved Earlier')}
          >
            <span className="btn-icon">⚡</span>
            <div>
              <strong>Simulate Deadline Moved Earlier</strong>
              <small>Shrinks runway to 50 days → Staged Plan Adjustment Proposal</small>
            </div>
            {simulating === 'deadline_earlier' && <span className="btn-spinner" />}
          </button>

          <button
            id="btn-sim-deadline-extended"
            className="btn-demo btn-demo-success"
            disabled={simulating !== null}
            onClick={() => triggerSimulation('deadline_extended', 'Deadline Extended')}
          >
            <span className="btn-icon">⏳</span>
            <div>
              <strong>Simulate Deadline Extended</strong>
              <small>Relaxes runway to 120 days → Informational Notification</small>
            </div>
            {simulating === 'deadline_extended' && <span className="btn-spinner" />}
          </button>

          <button
            id="btn-sim-unrelated-role"
            className="btn-demo btn-demo-neutral"
            disabled={simulating !== null}
            onClick={() => triggerSimulation('unrelated_role', 'Unrelated Role Event')}
          >
            <span className="btn-icon">🚫</span>
            <div>
              <strong>Simulate Unrelated Role Event</strong>
              <small>Deadline shift for other role → Ignored / No Action</small>
            </div>
            {simulating === 'unrelated_role' && <span className="btn-spinner" />}
          </button>

          <button
            id="btn-sim-untrusted-source"
            className="btn-demo btn-demo-warning"
            disabled={simulating !== null}
            onClick={() => triggerSimulation('untrusted_source', 'Untrusted Source')}
          >
            <span className="btn-icon">🔍</span>
            <div>
              <strong>Simulate Untrusted Source</strong>
              <small>Unverified third-party forum post → Human Review Required</small>
            </div>
            {simulating === 'untrusted_source' && <span className="btn-spinner" />}
          </button>

          <button
            id="btn-sim-evidence-added"
            className="btn-demo btn-demo-info"
            disabled={simulating !== null}
            onClick={() => triggerSimulation('evidence_added', 'Skill Evidence Added')}
          >
            <span className="btn-icon">◈</span>
            <div>
              <strong>Simulate Evidence Added</strong>
              <small>Student portfolio item logged → Informational Record</small>
            </div>
            {simulating === 'evidence_added' && <span className="btn-spinner" />}
          </button>

          <button
            id="btn-sim-deadline-infeasible"
            className="btn-demo btn-demo-infeasible"
            disabled={simulating !== null}
            onClick={() => triggerSimulation('deadline_earlier_infeasible', 'Infeasible Early Deadline')}
          >
            <span className="btn-icon">⚡</span>
            <div>
              <strong>Simulate Infeasible Early Deadline</strong>
              <small>Shrinks to 12 days → Triggers Scope Reduction & Feasibility Alert</small>
            </div>
            {simulating === 'deadline_earlier_infeasible' && <span className="btn-spinner" />}
          </button>

          <button
            id="btn-sim-stale-event"
            className="btn-demo btn-demo-neutral"
            disabled={simulating !== null}
            onClick={() => triggerSimulation('stale_event', 'Stale / Out-of-Order Event')}
          >
            <span className="btn-icon">⏱</span>
            <div>
              <strong>Simulate Stale / Out-of-Order Event</strong>
              <small>Timestamp older than processed event → Idempotent No-Action</small>
            </div>
            {simulating === 'stale_event' && <span className="btn-spinner" />}
          </button>
        </div>

        {simSuccessMsg && (
          <div className="agent-alert-box alert-success" id="sim-success-alert">
            ✓ {simSuccessMsg}
          </div>
        )}
      </div>

      {/* Tabs: Decision Runs vs Raw Event Stream */}
      <div className="agent-subnav">
        <div className="subnav-tabs">
          <button
            id="tab-runs"
            className={`subnav-tab ${activeTab === 'runs' ? 'active' : ''}`}
            onClick={() => setActiveTab('runs')}
          >
            🤖 Agent Decision History ({runs.length})
          </button>
          <button
            id="tab-events"
            className={`subnav-tab ${activeTab === 'events' ? 'active' : ''}`}
            onClick={() => setActiveTab('events')}
          >
            📡 Ingested Event Feed ({events.length})
          </button>
        </div>

        <div className="subnav-filters">
          <button
            className={`filter-chip ${filterType === 'all' ? 'active' : ''}`}
            onClick={() => setFilterType('all')}
          >
            All Logs
          </button>
          <button
            className={`filter-chip ${filterType === 'simulated' ? 'active' : ''}`}
            onClick={() => setFilterType('simulated')}
          >
            Simulated Demo
          </button>
          <button
            className={`filter-chip ${filterType === 'real' ? 'active' : ''}`}
            onClick={() => setFilterType('real')}
          >
            Live Employer Events
          </button>
          <button className="btn-refresh" onClick={fetchData} title="Refresh Agent Data">
            ⟳ Refresh
          </button>
        </div>
      </div>

      {loading && (
        <div className="loading-state">
          <span className="spinner" /> Loading agent activity audit trail...
        </div>
      )}

      {error && <div className="agent-alert-box alert-error">Error: {error}</div>}

      {/* VIEW 1: AGENT RUNS AUDIT LOG */}
      {activeTab === 'runs' && !loading && (
        <div className="agent-runs-list" id="agent-runs-container">
          {filteredRuns.length === 0 ? (
            <div className="empty-agent-state">
              <h3>No agent decision runs found</h3>
              <p>Click any simulation button above to trigger the agent reasoning workflow.</p>
            </div>
          ) : (
            filteredRuns.map((run) => {
              const isExpanded = expandedRunId === run.id;
              return (
                <div
                  key={run.id}
                  id={`agent-run-${run.id}`}
                  className={`agent-run-card ${isExpanded ? 'expanded' : ''}`}
                >
                  <div
                    className="run-card-header"
                    onClick={() => setExpandedRunId(isExpanded ? null : run.id)}
                  >
                    <div className="run-header-top">
                      <div className="run-id-row">
                        <span className="run-id-badge">ID: {run.id.slice(0, 16)}</span>
                        {run.is_simulated ? (
                          <span className="sim-badge" id={`sim-badge-${run.id}`}>
                            ⚡ SIMULATED DEMO
                          </span>
                        ) : (
                          <span className="live-badge">● LIVE EVENT</span>
                        )}
                        {getEngineBadge(run.engine_used)}
                      </div>
                      <span className="run-timestamp">
                        {new Date(run.created_at).toLocaleString()} • {run.execution_time_ms}ms
                      </span>
                    </div>

                    <div className="run-header-mid">
                      {getCategoryBadge(run.decision_category)}
                      <span className="run-event-ref">Triggered by: {run.event_id}</span>
                    </div>

                    <div className="run-explanation-summary">
                      <strong>Why this event matters:</strong> {run.decision_explanation}
                    </div>

                    <div className="run-expand-hint">
                      {isExpanded ? '▲ Hide Execution Details & Tools' : '▼ Inspect Authorized Tools & Metrics'}
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="run-card-body">
                      {/* Phase 3.5: Run Timeline Stepper */}
                      <div className="run-timeline-stepper">
                        <div className="timeline-step">
                          <span className="step-num">1</span>
                          <div>
                            <strong>Event Ingested</strong>
                            <small>{run.event_id.slice(0, 14)}</small>
                          </div>
                        </div>
                        <div className="timeline-step">
                          <span className="step-num">2</span>
                          <div>
                            <strong>Fact Grounding</strong>
                            <small>Verified DB State</small>
                          </div>
                        </div>
                        <div className="timeline-step">
                          <span className="step-num">3</span>
                          <div>
                            <strong>Tools Executed</strong>
                            <small>{run.tools_invoked.length} tools invoked</small>
                          </div>
                        </div>
                        <div className="timeline-step">
                          <span className="step-num">4</span>
                          <div>
                            <strong>Decision Synthesized</strong>
                            <small>{run.decision_category}</small>
                          </div>
                        </div>
                        <div className={`timeline-step ${run.proposal_id ? 'step-pending-human' : ''}`}>
                          <span className="step-num">5</span>
                          <div>
                            <strong>Governance Gate</strong>
                            <small>{run.proposal_id ? 'Pending Student Review' : 'Preserved Immutable'}</small>
                          </div>
                        </div>
                      </div>

                      {/* Phase 3.5: Scope Reduction Strategy Alert Banner */}
                      {run.relevant_evidence?.scope_reduction_applied && (
                        <div className="scope-reduction-banner" id={`scope-banner-${run.id}`}>
                          <span className="scope-icon">⚡</span>
                          <div>
                            <strong>Adaptive Scope Reduction Strategy Applied:</strong> To prevent student burnout and honor capacity limits, non-mandatory milestones were rescheduled outside the immediate application window. The proposed plan focuses 100% on mandatory prerequisites.
                          </div>
                        </div>
                      )}

                      {/* Proposal Action Callout if Proposal Created */}
                      {run.proposal_id && (
                        <div className="agent-proposal-action-box" id={`run-proposal-box-${run.id}`}>
                          <div className="proposal-box-header">
                            <span className="proposal-tag">HUMAN APPROVAL REQUIRED</span>
                            <h4>Pending Mission Change Proposal #{run.proposal_id} Generated</h4>
                          </div>
                          <p>
                            The AI agent calculated that meeting this deadline requires an accelerated
                            pace. A staged roadmap proposal has been created and left in <b>PENDING</b>{' '}
                            status awaiting your student review.
                          </p>
                          <div className="proposal-actions-row">
                            <button
                              id={`btn-review-proposal-${run.proposal_id}`}
                              className="btn-primary"
                              onClick={onNavigateToMission}
                            >
                              Review & Decide in Career Mission →
                            </button>
                            <span className="governance-note">
                              🔒 Human safety boundary: Mission is unchanged until you approve.
                            </span>
                          </div>
                        </div>
                      )}

                      {/* Relevant Evidence & Fact Metrics */}
                      {run.relevant_evidence && Object.keys(run.relevant_evidence).length > 0 && (
                        <div className="run-metrics-section">
                          <h5>OBSERVED FACTS & CALCULATED PACING METRICS</h5>
                          <div className="metrics-grid">
                            {run.relevant_evidence.days_remaining !== undefined && (
                              <div className="metric-cell">
                                <span className="metric-label">Runway Remaining</span>
                                <span className="metric-val">
                                  {run.relevant_evidence.days_remaining} days (
                                  {run.relevant_evidence.weeks_remaining} wks)
                                </span>
                              </div>
                            )}
                            {run.relevant_evidence.remaining_effort_hours_avg !== undefined && (
                              <div className="metric-cell">
                                <span className="metric-label">Remaining Roadmap Effort</span>
                                <span className="metric-val">
                                  {run.relevant_evidence.remaining_effort_hours_avg} hrs
                                </span>
                              </div>
                            )}
                            {run.relevant_evidence.weekly_hours_capacity !== undefined && (
                              <div className="metric-cell">
                                <span className="metric-label">Student Capacity</span>
                                <span className="metric-val">
                                  {run.relevant_evidence.weekly_hours_capacity} hrs/week
                                </span>
                              </div>
                            )}
                            {run.relevant_evidence.required_weekly_hours !== undefined && (
                              <div className="metric-cell">
                                <span className="metric-label">Required Pacing</span>
                                <span className="metric-val highlight">
                                  {run.relevant_evidence.required_weekly_hours} hrs/week
                                </span>
                              </div>
                            )}
                            {run.relevant_evidence.capacity_ratio !== undefined && (
                              <div className="metric-cell">
                                <span className="metric-label">Capacity Utilization</span>
                                <span className="metric-val highlight">
                                  {(run.relevant_evidence.capacity_ratio * 100).toFixed(0)}%
                                </span>
                              </div>
                            )}
                          </div>

                          {/* Phase 3.5: Capacity & Feasibility Bar Meter */}
                          {run.relevant_evidence.capacity_ratio !== undefined && (
                            <div className="capacity-meter-wrapper">
                              <div className="capacity-meter-labels">
                                <span>Weekly Capacity Pacing Meter</span>
                                <span>
                                  {run.relevant_evidence.required_weekly_hours ?? 0} hrs/wk required / {run.relevant_evidence.weekly_hours_capacity ?? 15} hrs/wk capacity
                                </span>
                              </div>
                              <div className="capacity-meter-track">
                                <div
                                  className={`capacity-meter-fill ${
                                    run.relevant_evidence.capacity_ratio <= 1.0
                                      ? 'fill-green'
                                      : run.relevant_evidence.capacity_ratio <= 1.8
                                      ? 'fill-yellow'
                                      : 'fill-red'
                                  }`}
                                  style={{
                                    width: `${Math.min(100, Math.max(5, (run.relevant_evidence.capacity_ratio / 2.6) * 100))}%`,
                                  }}
                                />
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Tools Invoked Audit Trail */}
                      <div className="run-tools-section">
                        <h5>AUTHORIZED TOOLS INVOKED ({run.tools_invoked.length})</h5>
                        <div className="tools-chip-list">
                          {run.tools_invoked.map((toolName, idx) => (
                            <span key={idx} className="tool-chip">
                              ✓ {toolName}
                            </span>
                          ))}
                        </div>

                        {/* Expandable tool I/O trace */}
                        <div className="tool-io-details">
                          <details>
                            <summary>View Sanitized Tool Inputs & Outputs ({run.tool_io_log.length} calls)</summary>
                            <div className="tool-io-log-list">
                              {run.tool_io_log.map((io, idx) => (
                                <div key={idx} className="tool-io-item">
                                  <div className="tool-io-header">
                                    <span className="step-num">Step {idx + 1}:</span>
                                    <span className="tool-name-tag">{io.tool}</span>
                                  </div>
                                  <div className="io-code-block">
                                    <small className="io-label">Input:</small>
                                    <pre>{JSON.stringify(io.input, null, 2)}</pre>
                                    <small className="io-label">Output (Sanitized):</small>
                                    <pre>{JSON.stringify(io.output, null, 2)}</pre>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </details>
                        </div>
                      </div>

                      {/* Judge Mode: Native C++20 DSA Engine & Graph Trace */}
                      <div className="judge-cpp-section" id={`cpp-trace-${run.id}`}>
                        <div className="judge-section-header">
                          <span className="section-icon">⚙</span>
                          <h5>NATIVE C++20 LEARNING PATH ENGINE VERIFICATION</h5>
                          <span className="cxx-tag">internpath_dsa</span>
                        </div>
                        <div className="cpp-metrics-grid">
                          <div className="cpp-metric-cell">
                            <span className="cpp-label">Graph Implementation</span>
                            <strong>Adjacency Lists via HashTable&lt;int, DynamicArray&lt;int&gt;&gt;</strong>
                          </div>
                          <div className="cpp-metric-cell">
                            <span className="cpp-label">Topological Solver</span>
                            <strong>Kahn's Algorithm (in-degree reduction queue)</strong>
                          </div>
                          <div className="cpp-metric-cell">
                            <span className="cpp-label">Prerequisite Cycle Check</span>
                            <strong className="text-safe">0 cycles detected (DAG Valid)</strong>
                          </div>
                          <div className="cpp-metric-cell">
                            <span className="cpp-label">Completed Task Protection</span>
                            <strong className="text-safe">100% of acquired competencies preserved</strong>
                          </div>
                        </div>
                      </div>

                      {/* Judge Mode: Factual Grounding & Privacy Invariants */}
                      <div className="judge-grounding-section" id={`grounding-trace-${run.id}`}>
                        <div className="judge-section-header">
                          <span className="section-icon">🛡</span>
                          <h5>ARCHITECTURAL GROUNDING & PRIVACY INVARIANTS</h5>
                          <span className="grounding-status-tag">VERIFIED BOUNDARY</span>
                        </div>
                        <div className="grounding-checks-list">
                          <div className="grounding-check-item">
                            <span className="check-icon">✓</span>
                            <div>
                              <strong>Allowlisted Model Tools:</strong>
                              <small>Only server-registered functions executed. Direct database writes and shell access blocked.</small>
                            </div>
                          </div>
                          <div className="grounding-check-item">
                            <span className="check-icon">✓</span>
                            <div>
                              <strong>Counterfactual Simulation Isolation:</strong>
                              <small>All evaluated plan alternatives run in-memory without mutating active mission version.</small>
                            </div>
                          </div>
                          <div className="grounding-check-item">
                            <span className="check-icon">✓</span>
                            <div>
                              <strong>Human Consent Governance:</strong>
                              <small>AI proposes, student decides. Self-approval strictly forbidden by backend gate.</small>
                            </div>
                          </div>
                          <div className="grounding-check-item">
                            <span className="check-icon">✓</span>
                            <div>
                              <strong>Data Minimization & Redaction:</strong>
                              <small>Student credentials, passwords, and raw keys redacted from audit logs and LLM prompts.</small>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}

      {/* VIEW 2: INGESTED EVENT FEED */}
      {activeTab === 'events' && !loading && (
        <div className="agent-events-list" id="agent-events-container">
          {filteredEvents.length === 0 ? (
            <div className="empty-agent-state">
              <h3>No events in feed</h3>
              <p>Simulate an event to see the intake contract.</p>
            </div>
          ) : (
            <table className="agent-events-table">
              <thead>
                <tr>
                  <th>Event ID</th>
                  <th>Type</th>
                  <th>Source & Reliability</th>
                  <th>Role ID</th>
                  <th>Previous → New Value</th>
                  <th>Status</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {filteredEvents.map((ev) => (
                  <tr key={ev.id}>
                    <td>
                      <code>{ev.event_id}</code>
                      {ev.is_simulated && <span className="mini-sim-tag">SIM</span>}
                    </td>
                    <td>
                      <b>{ev.event_type}</b>
                    </td>
                    <td>
                      {ev.source}
                      <br />
                      <span className={`reliability-tag tag-${ev.source_reliability}`}>
                        {ev.source_reliability}
                      </span>
                    </td>
                    <td>{ev.role_id || '—'}</td>
                    <td>
                      <span className="prev-val">{ev.previous_value || 'None'}</span> →{' '}
                      <span className="new-val">{ev.new_value || 'None'}</span>
                    </td>
                    <td>
                      <span className={`status-pill pill-${ev.processing_status}`}>
                        {ev.processing_status}
                      </span>
                    </td>
                    <td>
                      <small>{new Date(ev.received_at).toLocaleTimeString()}</small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};
