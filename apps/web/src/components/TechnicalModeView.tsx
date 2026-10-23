import React, { useState } from 'react';
import { AgentActivityView } from './AgentActivityView';

interface TechnicalModeViewProps {
  onBackToStudent: () => void;
  onNavigateToMission: () => void;
  plan: any | null;
  onGeneratePlan: () => Promise<void>;
  planLoading: boolean;
  skills: any[];
}

const phase1Skills = [
  { name: 'C++', target: 2, weight: 5, mandatory: 1 },
  { name: 'Data Structures', target: 2, weight: 4, mandatory: 1 },
  { name: 'RTOS', target: 1, weight: 3, mandatory: 0 },
  { name: 'Git', target: 1, weight: 2, mandatory: 0 },
];

export const TechnicalModeView: React.FC<TechnicalModeViewProps> = ({
  onBackToStudent,
  onNavigateToMission,
  plan,
  onGeneratePlan,
  planLoading,
  skills,
}) => {
  const [subTab, setSubTab] = useState<'dsa' | 'agent' | 'match'>('dsa');
  const [viewMode, setViewMode] = useState<'stages' | 'graph'>('stages');
  const [selectedSkillNode, setSelectedSkillNode] = useState<any | null>(null);

  // Phase 1 match demo state
  const [matchLevels, setMatchLevels] = useState<number[]>([2, 1, 0, 1]);
  const [matchResult, setMatchResult] = useState<any | null>(null);
  const [matchError, setMatchError] = useState('');
  const [matchWorking, setMatchWorking] = useState(false);

  async function analyzeMatch() {
    setMatchError('');
    setMatchWorking(true);
    try {
      const response = await fetch('/v1/demo/match', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          student_levels: matchLevels,
          required_levels: phase1Skills.map((s) => s.target),
          weights: phase1Skills.map((s) => s.weight),
          mandatory: phase1Skills.map((s) => s.mandatory),
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `API HTTP ${response.status}`);
      }
      setMatchResult(await response.json());
    } catch (e) {
      setMatchError(e instanceof Error ? e.message : 'Unknown error');
      setMatchResult(null);
    } finally {
      setMatchWorking(false);
    }
  }

  return (
    <div className="technical-mode-container" id="technical-mode-view">
      {/* Top Banner: Mode Indicator and Return CTA */}
      <div className="tech-header-banner">
        <div className="tech-header-left">
          <div className="eyebrow-dsa">ACADEMIC & EVALUATOR WORKSPACE</div>
          <h1>🔬 Technical Inspector & DSA Demonstration Lab</h1>
          <p className="tech-lede">
            Inspect handwritten C++20 data structure traces, Kahn's algorithm topological sorting,
            agent decision audits, and verifiable human governance boundaries.
          </p>
        </div>
        <div className="tech-header-right">
          <button
            id="btn-return-student-mode"
            className="btn-return-student"
            onClick={onBackToStudent}
          >
            ← Return to Student Workspace
          </button>
        </div>
      </div>

      {/* Sub-Navigation Tabs */}
      <div className="tech-subnav">
        <button
          id="tech-tab-dsa"
          className={`tech-tab-btn ${subTab === 'dsa' ? 'active' : ''}`}
          onClick={() => setSubTab('dsa')}
        >
          📊 C++ DSA Engine & Graph Trace
        </button>
        <button
          id="tech-tab-agent"
          className={`tech-tab-btn ${subTab === 'agent' ? 'active' : ''}`}
          onClick={() => setSubTab('agent')}
        >
          🤖 Agent Inspector & Audit Log
        </button>
        <button
          id="tech-tab-match"
          className={`tech-tab-btn ${subTab === 'match' ? 'active' : ''}`}
          onClick={() => setSubTab('match')}
        >
          ▦ Phase 1 Scoring Demo
        </button>
      </div>

      {/* =================================================================== */}
      {/* SUBTAB 1: C++ DSA ENGINE & GRAPH PRESENTER                         */}
      {/* =================================================================== */}
      {subTab === 'dsa' && (
        <div className="dsa-presenter-content" id="dsa-presenter-section">
          {/* Engine Execution Header */}
          <div className="panel dsa-run-card">
            <div className="dsa-run-header">
              <div>
                <h3>C++20 LearningPathEngine Live Trace</h3>
                <p>Computes reverse prerequisite closure and Kahn's topological sort stages.</p>
              </div>
              <button
                id="btn-tech-run-engine"
                className="btn-primary"
                onClick={onGeneratePlan}
                disabled={planLoading}
              >
                {planLoading ? 'Running C++ Subprocess…' : '⚡ Run C++ Graph Engine'}
              </button>
            </div>

            {plan?.algorithm_trace ? (
              <div className="dsa-metrics-grid">
                <div className="dsa-metric-card">
                  <span className="dsa-metric-label">Graph Structure</span>
                  <strong className="dsa-metric-val">
                    {plan.algorithm_trace.graph_node_count} nodes / {plan.algorithm_trace.graph_edge_count} edges
                  </strong>
                  <small>HashTable&lt;int, DynamicArray&lt;int&gt;&gt;</small>
                </div>
                <div className="dsa-metric-card">
                  <span className="dsa-metric-label">Prerequisite Closure</span>
                  <strong className="dsa-metric-val">
                    {plan.algorithm_trace.prerequisite_closure_nodes_visited} visited
                  </strong>
                  <small>Reverse BFS via CircularQueue</small>
                </div>
                <div className="dsa-metric-card">
                  <span className="dsa-metric-label">Kahn Queue Ops</span>
                  <strong className="dsa-metric-val">
                    {plan.algorithm_trace.kahn_queue_enqueues} enq / {plan.algorithm_trace.kahn_queue_dequeues} deq
                  </strong>
                  <small>Zero in-degree queue tracking</small>
                </div>
                <div className="dsa-metric-card">
                  <span className="dsa-metric-label">Engine Latency</span>
                  <strong className="dsa-metric-val highlight">
                    {plan.algorithm_trace.execution_time_microseconds?.toFixed(2)} µs
                  </strong>
                  <small>std::chrono high_resolution_clock</small>
                </div>
              </div>
            ) : (
              <div className="dsa-metrics-placeholder">
                Click "Run C++ Graph Engine" above to execute the binary and capture microsecond traces.
              </div>
            )}
          </div>

          {/* View Toggle: Ordered Stages vs Interactive DAG */}
          {plan && (
            <div className="panel dsa-results-panel">
              <div className="results-header">
                <div className="view-toggle">
                  <button
                    className={viewMode === 'stages' ? 'active' : ''}
                    onClick={() => setViewMode('stages')}
                  >
                    Topological Stages ({plan.stages?.length || 0})
                  </button>
                  <button
                    className={viewMode === 'graph' ? 'active' : ''}
                    onClick={() => setViewMode('graph')}
                  >
                    Interactive SVG Graph (DAG)
                  </button>
                </div>
              </div>

              {viewMode === 'stages' && (
                <div className="stages-container">
                  {plan.stages?.map((stage: any) => (
                    <div key={stage.stage_number} className="stage-card">
                      <div className="stage-card-header">
                        <div>
                          <span className="stage-badge">Stage {stage.stage_number}</span>
                          <h4 className="stage-title">{stage.stage_title}</h4>
                        </div>
                        <div className="stage-effort-pill">
                          Est. Effort: {stage.stage_effort?.min_hours}–{stage.stage_effort?.max_hours} hrs
                        </div>
                      </div>
                      <p className="stage-parallel-note">
                        ⚡ <i>Concurrency:</i> Stage milestones have satisfied in-degrees and can be tackled in parallel.
                      </p>
                      <div className="upgrades-grid">
                        {stage.skills?.map((sk: any) => (
                          <div key={sk.skill_id} className="upgrade-card">
                            <div className="upgrade-card-top">
                              <strong>{sk.skill_name}</strong>
                              <span className="category-pill">{sk.category}</span>
                            </div>
                            <div className="level-progression-bar">
                              <span>Level {sk.current_level}</span>
                              <span>➔</span>
                              <span className="target-level-pill">Target Level {sk.target_level}</span>
                            </div>
                            <small className="rationale-text">{sk.rationale}</small>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {viewMode === 'graph' && (
                <div className="dag-canvas-container">
                  <svg className="dag-svg" viewBox="0 0 900 480" width="100%" height="450">
                    <defs>
                      <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
                        <polygon points="0 0, 8 3, 0 6" fill="#3288ff" />
                      </marker>
                    </defs>
                    {/* Directed Edges */}
                    <line x1="140" y1="80" x2="310" y2="70" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead)" />
                    <line x1="140" y1="80" x2="310" y2="160" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead)" />
                    <line x1="450" y1="70" x2="570" y2="90" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead)" />
                    <line x1="140" y1="360" x2="570" y2="110" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead)" />
                    <line x1="450" y1="160" x2="570" y2="180" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead)" />
                    <line x1="710" y1="100" x2="790" y2="140" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead)" />
                    <line x1="710" y1="180" x2="790" y2="160" stroke="#3288ff" strokeWidth="2" markerEnd="url(#arrowhead)" />

                    {/* Nodes */}
                    <g className="dag-node" transform="translate(40, 50)" onClick={() => setSelectedSkillNode(skills.find(s => s.id === 1))}>
                      <rect width="120" height="55" rx="8" fill="#1b3054" stroke="#4886e0" strokeWidth="2" />
                      <text x="60" y="26" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">Foundations (1)</text>
                      <text x="60" y="42" fill="#8cb7f5" fontSize="9" textAnchor="middle">Core Logic</text>
                    </g>
                    <g className="dag-node" transform="translate(320, 40)" onClick={() => setSelectedSkillNode(skills.find(s => s.id === 2))}>
                      <rect width="130" height="55" rx="8" fill="#1b3054" stroke="#4886e0" strokeWidth="2" />
                      <text x="65" y="26" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">Python (2)</text>
                      <text x="65" y="42" fill="#8cb7f5" fontSize="9" textAnchor="middle">Languages</text>
                    </g>
                    <g className="dag-node" transform="translate(320, 130)" onClick={() => setSelectedSkillNode(skills.find(s => s.id === 3))}>
                      <rect width="130" height="55" rx="8" fill="#203a66" stroke="#5ba0ff" strokeWidth="2" />
                      <text x="65" y="26" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">C++ Systems (3)</text>
                      <text x="65" y="42" fill="#ffd479" fontSize="9" fontWeight="700" textAnchor="middle">Stage 1</text>
                    </g>
                    <g className="dag-node" transform="translate(40, 330)" onClick={() => setSelectedSkillNode(skills.find(s => s.id === 9))}>
                      <rect width="120" height="55" rx="8" fill="#1b3054" stroke="#4886e0" strokeWidth="2" />
                      <text x="60" y="26" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">SQL / DB (9)</text>
                      <text x="60" y="42" fill="#8cb7f5" fontSize="9" textAnchor="middle">Backend</text>
                    </g>
                    <g className="dag-node" transform="translate(580, 70)" onClick={() => setSelectedSkillNode(skills.find(s => s.id === 4))}>
                      <rect width="130" height="55" rx="8" fill="#1b3054" stroke="#4886e0" strokeWidth="2" />
                      <text x="65" y="26" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">FastAPI (4)</text>
                      <text x="65" y="42" fill="#8cb7f5" fontSize="9" textAnchor="middle">Backend APIs</text>
                    </g>
                    <g className="dag-node" transform="translate(580, 160)" onClick={() => setSelectedSkillNode(skills.find(s => s.id === 5))}>
                      <rect width="130" height="55" rx="8" fill="#203a66" stroke="#5ba0ff" strokeWidth="2" />
                      <text x="65" y="26" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">DSA (5)</text>
                      <text x="65" y="42" fill="#ffd479" fontSize="9" fontWeight="700" textAnchor="middle">Stage 2</text>
                    </g>
                    <g className="dag-node" transform="translate(770, 130)" onClick={() => setSelectedSkillNode(skills.find(s => s.id === 6))}>
                      <rect width="120" height="55" rx="8" fill="#312244" stroke="#a78bfa" strokeWidth="2" />
                      <text x="60" y="26" fill="#fff" fontSize="11" fontWeight="700" textAnchor="middle">Dist. Systems (6)</text>
                      <text x="60" y="42" fill="#c084fc" fontSize="9" fontWeight="700" textAnchor="middle">Target Goal</text>
                    </g>
                  </svg>
                  {selectedSkillNode && (
                    <div className="node-detail-card">
                      <strong>Node #{selectedSkillNode.id}: {selectedSkillNode.name}</strong>
                      <p>{selectedSkillNode.description}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Academic Algorithms Explainer */}
          <div className="panel dsa-academic-panel">
            <h4>Academic DSA Architecture Reference</h4>
            <div className="dsa-explainer-cards">
              <div className="explainer-card">
                <h5>1. Directed Graph via Custom HashTable</h5>
                <p>Curriculum is represented as an adjacency list inside <code>HashTable&lt;int, DynamicArray&lt;int&gt;&gt;</code> with separate-chaining lists.</p>
              </div>
              <div className="explainer-card">
                <h5>2. Reverse Prerequisite Closure in O(V + E)</h5>
                <p>Reverse BFS using our custom <code>CircularQueue&lt;int&gt;</code> resolves transitive dependencies without recursion stack limits.</p>
              </div>
              <div className="explainer-card">
                <h5>3. Kahn's Topological Sorting</h5>
                <p>Computes parallelizable stages by peeling zero in-degree vertices level-by-level, detecting any cyclic dependencies.</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* SUBTAB 2: AGENT INSPECTOR & AUDIT TRAIL                            */}
      {/* =================================================================== */}
      {subTab === 'agent' && (
        <div className="agent-inspector-content" id="agent-inspector-section">
          <AgentActivityView onNavigateToMission={onNavigateToMission} />
        </div>
      )}

      {/* =================================================================== */}
      {/* SUBTAB 3: PHASE 1 MATCH CALCULATOR DEMO                           */}
      {/* =================================================================== */}
      {subTab === 'match' && (
        <div className="phase1-demo-content panel" id="phase1-match-section">
          <div className="panel-header">
            <div>
              <span className="demo-data-chip">ACADEMIC STARTER PROOF OF CONCEPT</span>
              <h3>Phase 1 Weighted Scoring Subprocess Demo</h3>
              <p>Demonstrates early CLI flag transport: <code>--student a,b --required a,b --weights a,b --mandatory 0,1</code></p>
            </div>
          </div>

          <div className="match-controls-grid">
            {phase1Skills.map((sk, idx) => (
              <div key={sk.name} className="match-skill-box">
                <div className="match-skill-top">
                  <strong>{sk.name}</strong>
                  <small>Weight: {sk.weight} • {sk.mandatory ? 'Mandatory' : 'Optional'}</small>
                </div>
                <div className="match-slider-row">
                  <span>Level {matchLevels[idx]}</span>
                  <input
                    type="range"
                    min="0"
                    max="3"
                    value={matchLevels[idx]}
                    onChange={(e) => {
                      const updated = [...matchLevels];
                      updated[idx] = Number(e.target.value);
                      setMatchLevels(updated);
                    }}
                  />
                  <span>Target: {sk.target}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="match-action-row">
            <button
              id="btn-run-phase1-match"
              className="btn-primary"
              onClick={analyzeMatch}
              disabled={matchWorking}
            >
              {matchWorking ? 'Analyzing C++ Process…' : 'Calculate Phase 1 Score'}
            </button>
            {matchError && <span className="text-danger">⚠️ {matchError}</span>}
          </div>

          {matchResult && (
            <div className="match-result-card">
              <h4>Phase 1 Result Payload:</h4>
              <div className="match-metrics-row">
                <span>Earned: <b>{matchResult.earned_points}</b> / {matchResult.max_points} pts</span>
                <span>Coverage: <b>{matchResult.coverage_percent}%</b></span>
                <span>Missing Mandatory: <b>{matchResult.missing_mandatory}</b></span>
                <span>Mandatory Met: <b>{matchResult.mandatory_requirements_met ? 'Yes ✓' : 'No ✗'}</b></span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
