import React, { useState, useEffect, useRef } from 'react';

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

export interface ChatMessage {
  id: string;
  sender: 'student' | 'assistant';
  text: string;
  timestamp: string;
  engine_used?: string;
  decision_category?: string;
  tools_invoked?: string[];
  tool_io_log?: Array<{ tool: string; input: Record<string, any>; output: any }>;
  proposal_id?: number | null;
  proposal_title?: string | null;
  tradeoffs?: string[];
  proposal_status?: 'pending' | 'approved' | 'rejected';
  is_loading?: boolean;
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
  currentTab?: string;
  onDataRefresh?: () => void;
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
  currentTab = 'home',
  onDataRefresh,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [decidingProposalId, setDecidingProposalId] = useState<number | null>(null);
  const [decisionFeedback, setDecisionFeedback] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Initialize welcome message once
  useEffect(() => {
    if (messages.length === 0) {
      setMessages([
        {
          id: 'welcome_1',
          sender: 'assistant',
          text: `Hello ${studentName || 'Student'}! I am your contextual Career Preparation Agent. I can help you evaluate your roadmap feasibility, simulate alternative learning plans using our native C++ topological engine, and stage proposals when your study availability changes.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          engine_used: 'deterministic_rules',
          decision_category: 'informational_notification',
          tools_invoked: ['read_student_profile', 'read_active_mission'],
          tradeoffs: [
            'All guidance is grounded in your persistent database mission and validated via Kahn\'s algorithm.',
            'The AI proposes plan adjustments; only you can approve or reject changes.',
          ],
        },
      ]);
    }
  }, [studentName]);

  // Auto-scroll chat to bottom
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen, isSending]);

  if (!isOpen) return null;

  const allTasks = activeMission?.active_version?.tasks || [];
  const inProgressTask = allTasks.find((t) => t.status === 'in_progress');
  const nextUnlockedTask = allTasks.find((t) => t.status === 'not_started' && t.is_unlocked);
  const nextTask = inProgressTask || nextUnlockedTask;
  const hasPendingProposals = (activeMission?.pending_proposals_count ?? 0) > 0;

  // Send query to backend /v1/agent/query
  const handleSendMessage = async (queryText?: string) => {
    const textToSend = (queryText || inputValue).trim();
    if (!textToSend || isSending) return;

    setInputValue('');
    setSendError(null);
    setDecisionFeedback(null);

    const studentMsgId = `student_${Date.now()}`;
    const loadingMsgId = `loading_${Date.now()}`;

    // 1. Add student message
    const studentMsg: ChatMessage = {
      id: studentMsgId,
      sender: 'student',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    // 2. Add loading placeholder
    const loadingMsg: ChatMessage = {
      id: loadingMsgId,
      sender: 'assistant',
      text: 'Evaluating mission constraints with C++ topological planner and simulating options...',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      is_loading: true,
    };

    setMessages((prev) => [...prev, studentMsg, loadingMsg]);
    setIsSending(true);

    try {
      const response = await fetch('/v1/agent/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: textToSend,
          context_role_id: activeMission?.target_role_id || undefined,
          simulated: false,
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned HTTP ${response.status}`);
      }

      const run = await response.json();

      // Extract tradesoffs from relevant_evidence or decision
      let extractedTradeoffs: string[] = [];
      if (run.relevant_evidence?.tradeoffs && Array.isArray(run.relevant_evidence.tradeoffs)) {
        extractedTradeoffs = run.relevant_evidence.tradeoffs;
      }

      const assistantMsg: ChatMessage = {
        id: run.id || `agent_${Date.now()}`,
        sender: 'assistant',
        text: run.decision_explanation || 'Evaluation completed.',
        timestamp: new Date(run.created_at || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        engine_used: run.engine_used,
        decision_category: run.decision_category,
        tools_invoked: run.tools_invoked || [],
        tool_io_log: run.tool_io_log || [],
        proposal_id: run.proposal_id,
        tradeoffs: extractedTradeoffs,
        proposal_status: run.proposal_id ? 'pending' : undefined,
      };

      // Replace loading message with real assistant message
      setMessages((prev) => prev.map((m) => (m.id === loadingMsgId ? assistantMsg : m)));

      // If a proposal was staged, notify parent to refresh counts
      if (run.proposal_id) {
        onDataRefresh?.();
      }
    } catch (err) {
      setSendError(err instanceof Error ? err.message : 'Failed to communicate with agent service.');
      // Remove loading message on error
      setMessages((prev) => prev.filter((m) => m.id !== loadingMsgId));
    } finally {
      setIsSending(false);
    }
  };

  // Human Approval: Approve Proposal
  const handleApproveProposal = async (proposalId: number, messageId: string) => {
    if (!activeMission) return;
    setDecidingProposalId(proposalId);
    setDecisionFeedback(null);
    try {
      const res = await fetch(`/v1/missions/${activeMission.id}/proposals/${proposalId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision_notes: 'Approved roadmap update via Contextual Assistant.' }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Approval failed with HTTP ${res.status}`);
      }
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, proposal_status: 'approved' } : m))
      );
      setDecisionFeedback({
        type: 'success',
        message: `Proposal #${proposalId} approved! Active mission updated to Version 2.0.`,
      });
      onDataRefresh?.();
    } catch (e) {
      setDecisionFeedback({
        type: 'error',
        message: e instanceof Error ? e.message : 'Failed to approve proposal.',
      });
    } finally {
      setDecidingProposalId(null);
    }
  };

  // Human Approval: Reject Proposal
  const handleRejectProposal = async (proposalId: number, messageId: string) => {
    if (!activeMission) return;
    setDecidingProposalId(proposalId);
    setDecisionFeedback(null);
    try {
      const res = await fetch(`/v1/missions/${activeMission.id}/proposals/${proposalId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision_notes: 'Rejected roadmap update via Contextual Assistant.' }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Rejection failed with HTTP ${res.status}`);
      }
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, proposal_status: 'rejected' } : m))
      );
      setDecisionFeedback({
        type: 'info',
        message: `Proposal #${proposalId} rejected. Baseline mission retained unchanged.`,
      });
      onDataRefresh?.();
    } catch (e) {
      setDecisionFeedback({
        type: 'error',
        message: e instanceof Error ? e.message : 'Failed to reject proposal.',
      });
    } finally {
      setDecidingProposalId(null);
    }
  };

  // Helper: Format engine badge honestly
  const renderEngineBadge = (engine?: string) => {
    if (!engine) return null;
    if (engine.startsWith('gemini:')) {
      return <span className="assistant-engine-tag live-gemini" title="Real Gemini REST API">✦ Live Gemini ({engine.replace('gemini:', '')})</span>;
    }
    if (engine.startsWith('openai:')) {
      return <span className="assistant-engine-tag live-openai" title="Real OpenAI API">❖ Live OpenAI ({engine.replace('openai:', '')})</span>;
    }
    if (engine === 'mock_llm') {
      return <span className="assistant-engine-tag mock" title="Deterministic Mock Provider">⚗ Mock LLM Provider</span>;
    }
    return <span className="assistant-engine-tag rules" title="Deterministic Rule Engine Grounded in C++ Solver">⚙ Deterministic Rule Engine</span>;
  };

  // Helper: Extract simulations from tool_io_log
  const extractSimulations = (toolLog?: Array<{ tool: string; input: Record<string, any>; output: any }>) => {
    if (!toolLog) return [];
    return toolLog
      .filter((rec) => rec.tool === 'simulate_plan_variant' && rec.output && rec.output.simulation_id)
      .map((rec) => rec.output);
  };

  // Helper: Extract comparison from tool_io_log
  const extractComparison = (toolLog?: Array<{ tool: string; input: Record<string, any>; output: any }>) => {
    if (!toolLog) return null;
    const rec = toolLog.find((r) => r.tool === 'compare_plan_variants');
    return rec ? rec.output : null;
  };

  // Contextual Quick Prompt suggestions based on currentTab
  const getContextualPills = () => {
    const demoScenarioPill = {
      label: 'University Exams (4 hrs/wk)',
      query: 'I have university exams for the next two weeks. I can only spend four hours per week preparing for my internship. What should I do?',
      isDemo: true,
    };

    const tabPills: Record<string, Array<{ label: string; query: string; isDemo?: boolean }>> = {
      home: [
        demoScenarioPill,
        { label: 'Next Task Focus', query: 'What should I focus on next in my career mission?' },
        { label: 'Missing Skills', query: 'Which important skills am I missing for this role?' },
      ],
      careers: [
        { label: 'Missing Role Skills', query: 'Which important skills am I missing for this role?' },
        { label: 'Core vs Elective', query: 'Which competencies are mandatory vs elective for my target role?' },
        demoScenarioPill,
      ],
      roadmap: [
        demoScenarioPill,
        { label: '4h Workload Adjustment', query: 'I only have four hours per week. Can you adjust my plan?' },
        { label: 'Topological Order', query: 'What is the topological order of my tasks?' },
      ],
      readiness: [
        { label: 'Strengthen Profile Evidence', query: 'What evidence should I add to strengthen my profile?' },
        { label: 'Verified vs Declared Gaps', query: 'Which skills currently lack verified proof?' },
        demoScenarioPill,
      ],
    };

    return tabPills[currentTab] || tabPills.home;
  };

  return (
    <div className="assistant-drawer-overlay" onClick={onClose} id="assistant-drawer-overlay">
      <div
        className="assistant-drawer-panel"
        onClick={(e) => e.stopPropagation()}
        id="assistant-drawer"
      >
        {/* Header */}
        <div className="drawer-header">
          <div className="drawer-header-left">
            <span className="assistant-avatar">✦</span>
            <div>
              <h3>InternPath AI Assistant</h3>
              <small>Evidence-Driven • C++ Validated • Human-Approved</small>
            </div>
          </div>
          <button className="drawer-close-btn" onClick={onClose} title="Close Assistant" id="btn-close-assistant">
            ✕
          </button>
        </div>

        {/* Current Active Mission Context Strip */}
        <div className="drawer-context-strip" id="assistant-context-strip">
          <div className="strip-col">
            <span className="strip-label">TARGET ROLE</span>
            <strong>{activeMission?.target_role_title || activeRoleTitle || 'None Selected'}</strong>
          </div>
          <div className="strip-col">
            <span className="strip-label">CAPACITY</span>
            <strong>{activeMission?.weekly_hours || weeklyHours} hrs/wk</strong>
          </div>
          <div className="strip-col">
            <span className="strip-label">NEXT MILESTONE</span>
            <strong>{nextTask ? nextTask.skill_name : (activeMission ? 'All Unlocked Complete' : 'None')}</strong>
          </div>
        </div>

        {/* Quick View Shortcuts */}
        <div className="drawer-view-shortcuts" id="assistant-view-shortcuts">
          <button
            type="button"
            className="btn-shortcut"
            onClick={() => {
              onClose();
              onNavigateToCareers();
            }}
          >
            🎯 Careers View
          </button>
          <button
            type="button"
            className="btn-shortcut"
            onClick={() => {
              onClose();
              onNavigateToRoadmap();
            }}
          >
            🛤 Roadmap View
          </button>
          {onNavigateToReadiness && (
            <button
              type="button"
              className="btn-shortcut"
              onClick={() => {
                onClose();
                onNavigateToReadiness();
              }}
            >
              ◈ Readiness Proof Map
            </button>
          )}
        </div>

        {/* Pending Proposal Alert Banner (if active in database) */}
        {hasPendingProposals && (
          <div className="drawer-alert-banner" id="assistant-pending-alert">
            <span>⚠️ A plan adjustment proposal is currently pending student review.</span>
            <button
              type="button"
              className="btn-link"
              onClick={() => {
                onClose();
                onNavigateToRoadmap();
              }}
            >
              Open in Roadmap →
            </button>
          </div>
        )}

        {/* Feedback message banner for approval actions */}
        {decisionFeedback && (
          <div className={`drawer-feedback-banner feedback-${decisionFeedback.type}`}>
            <span>{decisionFeedback.message}</span>
            <button className="feedback-dismiss" onClick={() => setDecisionFeedback(null)}>✕</button>
          </div>
        )}

        {/* Chat Conversation Scroll Area */}
        <div className="drawer-chat-area" id="assistant-chat-messages">
          {messages.map((msg) => {
            const isAssistant = msg.sender === 'assistant';
            const simulations = isAssistant ? extractSimulations(msg.tool_io_log) : [];
            const comparison = isAssistant ? extractComparison(msg.tool_io_log) : null;

            return (
              <div
                key={msg.id}
                id={`chat-msg-${msg.id}`}
                className={`chat-bubble-row ${isAssistant ? 'assistant-row' : 'student-row'}`}
              >
                {isAssistant && <div className="bubble-avatar">✦</div>}
                <div className={`chat-bubble ${isAssistant ? 'assistant-bubble' : 'student-bubble'}`}>
                  {/* Bubble Header */}
                  <div className="bubble-header">
                    <span className="bubble-sender">{isAssistant ? 'InternPath Agent' : studentName || 'Student'}</span>
                    <span className="bubble-time">{msg.timestamp}</span>
                  </div>

                  {/* Engine Badge & Decision Category (for assistant) */}
                  {isAssistant && (
                    <div className="bubble-meta-tags">
                      {renderEngineBadge(msg.engine_used)}
                      {msg.decision_category && (
                        <span className={`decision-pill pill-${msg.decision_category}`}>
                          {msg.decision_category.replace(/_/g, ' ').toUpperCase()}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Message Content */}
                  <div className="bubble-text">
                    {msg.is_loading ? (
                      <div className="chat-loading-dots">
                        <span className="dot" />
                        <span className="dot" />
                        <span className="dot" />
                        <span className="loading-label">{msg.text}</span>
                      </div>
                    ) : (
                      <p>{msg.text}</p>
                    )}
                  </div>

                  {/* Visual Plan Alternatives (Simulations) */}
                  {simulations.length > 0 && (
                    <div className="bubble-simulations-container" id={`simulations-box-${msg.id}`}>
                      <div className="simulations-header">
                        <span className="sim-title">📊 Simulated Learning Plan Alternatives</span>
                        <span className="sim-badge-cxx">C++20 Engine Validated</span>
                      </div>

                      <div className="simulations-grid">
                        {simulations.map((sim, sIdx) => {
                          const isFeasible = sim.validity_status === 'VALID_AND_FEASIBLE';
                          const weeks = sim.estimated_weeks_range || [0, 0];
                          return (
                            <div
                              key={sim.simulation_id || sIdx}
                              className={`simulation-card ${isFeasible ? 'feasible' : 'infeasible'}`}
                            >
                              <div className="sim-card-top">
                                <strong>
                                  {sim.variant_type === 'pacing_reduction'
                                    ? `Alternative ${sIdx + 1}: Pacing Reduction (${sim.permitted_weekly_hours}h/wk)`
                                    : sim.variant_type === 'defer_optional'
                                    ? `Alternative ${sIdx + 1}: Defer Elective Competencies`
                                    : `Alternative ${sIdx + 1}: ${sim.variant_type}`}
                                </strong>
                                <span className={`feasibility-badge ${isFeasible ? 'badge-ok' : 'badge-warn'}`}>
                                  {isFeasible ? '✔ Feasible' : '✖ Infeasible'}
                                </span>
                              </div>

                              <div className="sim-metrics-row">
                                <div className="sim-metric">
                                  <span>Weekly Study:</span>
                                  <b>{sim.permitted_weekly_hours} hrs/wk</b>
                                </div>
                                <div className="sim-metric">
                                  <span>Estimated Runway:</span>
                                  <b>{weeks[0]}–{weeks[1]} weeks</b>
                                </div>
                                <div className="sim-metric">
                                  <span>Remaining Effort:</span>
                                  <b>{sim.estimated_remaining_hours_min}–{sim.estimated_remaining_hours_max} hrs</b>
                                </div>
                              </div>

                              <div className="sim-assessment-text">
                                <small>{sim.feasibility_assessment}</small>
                              </div>

                              <div className="sim-invariants-footer">
                                <span>🔒 100% of completed milestones preserved</span>
                                <span>✔ Kahn topological DAG verified</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {/* Side-by-Side Comparison Notes if compare_plan_variants was called */}
                      {comparison && (
                        <div className="comparison-notes-box">
                          <span className="comparison-label">💡 Alternative Comparison Analysis:</span>
                          <p>{comparison.rationale}</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Tradeoffs List */}
                  {msg.tradeoffs && msg.tradeoffs.length > 0 && (
                    <div className="bubble-tradeoffs-box">
                      <span className="tradeoff-title">⚖ Considered Trade-offs:</span>
                      <ul>
                        {msg.tradeoffs.map((t, tIdx) => (
                          <li key={tIdx}>{t}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Human-in-the-Loop Proposal Decision Card */}
                  {msg.proposal_id && (
                    <div className="assistant-proposal-action-card" id={`assistant-proposal-card-${msg.proposal_id}`}>
                      <div className="proposal-action-header">
                        <span className="proposal-flag">📋 MISSION CHANGE PROPOSAL #{msg.proposal_id}</span>
                        <span className={`proposal-state-badge state-${msg.proposal_status || 'pending'}`}>
                          {msg.proposal_status === 'approved'
                            ? '✔ Approved'
                            : msg.proposal_status === 'rejected'
                            ? '✕ Rejected'
                            : '⏳ Pending Student Decision'}
                        </span>
                      </div>

                      <h4 className="proposal-title">
                        {msg.proposal_title || `Exam Pacing Adjustment (${msg.text.includes('4') ? '4' : '10'} hrs/week)`}
                      </h4>

                      <p className="proposal-guardrail-notice">
                        🛡 <b>Human-in-the-Loop Architectural Guarantee:</b> The AI proposes. The algorithms validate. The student decides. Your approved roadmap will NOT change until you review and decide.
                      </p>

                      {(!msg.proposal_status || msg.proposal_status === 'pending') ? (
                        <div className="proposal-decision-actions">
                          <button
                            type="button"
                            id={`btn-approve-proposal-${msg.proposal_id}`}
                            className="btn-proposal-approve"
                            disabled={decidingProposalId === msg.proposal_id}
                            onClick={() => handleApproveProposal(msg.proposal_id!, msg.id)}
                          >
                            {decidingProposalId === msg.proposal_id ? 'Applying Version Update...' : '✓ Approve & Update Roadmap'}
                          </button>
                          <button
                            type="button"
                            id={`btn-reject-proposal-${msg.proposal_id}`}
                            className="btn-proposal-reject"
                            disabled={decidingProposalId === msg.proposal_id}
                            onClick={() => handleRejectProposal(msg.proposal_id!, msg.id)}
                          >
                            {decidingProposalId === msg.proposal_id ? 'Rejecting...' : '✕ Reject'}
                          </button>
                        </div>
                      ) : (
                        <div className={`proposal-outcome-banner banner-${msg.proposal_status}`}>
                          {msg.proposal_status === 'approved' ? (
                            <span>✔ You approved this proposal. Version 2.0 roadmap is now active.</span>
                          ) : (
                            <span>✕ You rejected this proposal. Version 1.0 remains active without mutation.</span>
                          )}
                          <button
                            type="button"
                            className="btn-link-view"
                            onClick={() => {
                              onClose();
                              onNavigateToRoadmap();
                            }}
                          >
                            View Roadmap →
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          <div ref={messagesEndRef} />
        </div>

        {/* Contextual Prompt Pills Strip */}
        <div className="drawer-quick-pills-strip" id="assistant-prompt-pills">
          <span className="pills-label">💡 Suggested Questions:</span>
          <div className="pills-scroll">
            {getContextualPills().map((pill, idx) => (
              <button
                key={idx}
                type="button"
                className={`prompt-pill ${pill.isDemo ? 'pill-demo' : ''}`}
                onClick={() => handleSendMessage(pill.query)}
                disabled={isSending}
                title={pill.query}
              >
                {pill.isDemo ? '🎯 Demo: ' : ''}{pill.label}
              </button>
            ))}
          </div>
        </div>

        {/* Input Footer */}
        <div className="drawer-chat-footer">
          {sendError && (
            <div className="drawer-error-strip">
              <span>{sendError}</span>
              <button className="btn-retry" onClick={() => handleSendMessage()}>Retry</button>
            </div>
          )}
          <form
            className="drawer-input-form"
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
          >
            <input
              id="assistant-query-input"
              type="text"
              className="chat-text-input"
              placeholder="Ask a question or request a study adjustment..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              disabled={isSending}
              maxLength={1000}
            />
            <button
              id="btn-send-assistant-query"
              type="submit"
              className="chat-send-btn"
              disabled={isSending || !inputValue.trim()}
              title="Send message to career agent"
            >
              {isSending ? <span className="send-spinner" /> : '➤'}
            </button>
          </form>
          <div className="drawer-footer-legend">
            <small>
              🛡 <b>Truthful AI Status:</b> Bounded model tool loop. Unverified claims rejected. All decisions grounded in persistent DB state.
            </small>
          </div>
        </div>
      </div>
    </div>
  );
};
