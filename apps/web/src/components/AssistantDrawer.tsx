import React from 'react';

interface AssistantDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigateToRoadmap: () => void;
  onNavigateToCareers: () => void;
  studentName: string;
  activeRoleTitle?: string | null;
  weeklyHours: number;
}

export const AssistantDrawer: React.FC<AssistantDrawerProps> = ({
  isOpen,
  onClose,
  onNavigateToRoadmap,
  onNavigateToCareers,
  studentName,
  activeRoleTitle,
  weeklyHours,
}) => {
  if (!isOpen) return null;

  return (
    <div className="assistant-drawer-overlay" onClick={onClose} id="assistant-drawer-overlay">
      <div className="assistant-drawer-panel" onClick={(e) => e.stopPropagation()} id="assistant-drawer">
        <div className="drawer-header">
          <div className="drawer-header-left">
            <span className="assistant-avatar">✦</span>
            <div>
              <h3>InternPath Assistant</h3>
              <small>Contextual Mission Companion</small>
            </div>
          </div>
          <button className="drawer-close-btn" onClick={onClose} title="Close Assistant">
            ✕
          </button>
        </div>

        <div className="drawer-body">
          {/* Active Context Card */}
          <div className="drawer-context-card">
            <span className="context-label">CURRENT ACTIVE CONTEXT</span>
            <h4>{studentName || 'Student'}</h4>
            <div className="context-meta-row">
              <span>🎯 Goal: <b>{activeRoleTitle || 'None selected'}</b></span>
              <span>⏱ Capacity: <b>{weeklyHours} hrs/wk</b></span>
            </div>
          </div>

          {/* Assistant Advisory Notice */}
          <div className="drawer-notice-box">
            <span className="notice-icon">💡</span>
            <div>
              <strong>Contextual Readiness Guidance</strong>
              <p>
                The Assistant analyzes your active mission and verified prerequisites to suggest actionable steps.
              </p>
            </div>
          </div>

          {/* Quick Contextual Actions */}
          <div className="drawer-actions-section">
            <h5>Recommended Inquiries</h5>
            <div className="drawer-prompts-list">
              <button
                className="drawer-prompt-btn"
                onClick={() => {
                  onClose();
                  onNavigateToRoadmap();
                }}
              >
                <span>🛤</span>
                <div>
                  <strong>"What is my next priority milestone?"</strong>
                  <small>Inspects unlocked tasks in your active roadmap</small>
                </div>
              </button>

              <button
                className="drawer-prompt-btn"
                onClick={() => {
                  onClose();
                  onNavigateToCareers();
                }}
              >
                <span>🎯</span>
                <div>
                  <strong>"What competencies are mandatory vs elective?"</strong>
                  <small>Compares target role requirements</small>
                </div>
              </button>
            </div>
          </div>

          {/* R2 Roadmap Disclosure */}
          <div className="drawer-future-roadmap">
            <small>
              🛡 <b>Truthful AI Capability Disclosure:</b> In R1.1, this assistant summarizes verified
              database state and prerequisite graph rules. Model-selected tool loops and natural language
              constraint simulation (<code>simulate_plan_variant</code>) are arriving in <b>Refinement R2</b>.
            </small>
          </div>
        </div>
      </div>
    </div>
  );
};
