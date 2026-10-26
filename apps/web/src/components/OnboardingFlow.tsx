import React, { useState, useEffect, useRef } from 'react';
import { CareerMission } from './CareerMissionView';
import { RoleItem, RoleRequirementItem } from './CareersView';

export interface OnboardingFlowProps {
  onComplete: (mission: CareerMission) => void;
  onCancel: () => void;
  initialRoleId?: string | null;
  hasExistingActiveMission?: boolean;
  existingMissionTitle?: string | null;
}

export const OnboardingFlow: React.FC<OnboardingFlowProps> = ({
  onComplete,
  onCancel,
  initialRoleId = null,
  hasExistingActiveMission = false,
  existingMissionTitle = null,
}) => {
  // Step state: 1 = Goal, 2 = Skills, 3 = Time, 4 = Processing, 5 = Success
  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1);

  // Step 1: Roles
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [rolesLoading, setRolesLoading] = useState(true);
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(initialRoleId);

  // Step 2: Role Requirements & Student Ratings
  const [requirements, setRequirements] = useState<RoleRequirementItem[]>([]);
  const [reqsLoading, setReqsLoading] = useState(false);
  // skillId -> declaredLevel (0 = not learned, 1 = basic, 2 = intermediate, 3 = advanced)
  const [skillRatings, setSkillRatings] = useState<Record<number, number>>({});
  // skillId -> verified state preserved from profile
  const [profileVerifiedState, setProfileVerifiedState] = useState<
    Record<number, { is_verified: boolean; verified_level: number }>
  >({});

  // Step 3: Availability & Deadlines
  const [weeklyHours, setWeeklyHours] = useState<number>(15);
  const [customHoursInput, setCustomHoursInput] = useState<string>('15');
  const [hoursError, setHoursError] = useState<string | null>(null);

  // Step 4: Submission & Plan Generation
  const [submitting, setSubmitting] = useState(false);
  const [submissionPhase, setSubmissionPhase] = useState<string>('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showReplaceConfirmModal, setShowReplaceConfirmModal] = useState(false);
  const [conflictingMission, setConflictingMission] = useState<CareerMission | null>(null);

  // Step 5: Success Result
  const [createdMission, setCreatedMission] = useState<CareerMission | null>(null);
  const attemptIdemKeyRef = useRef<string | null>(null);

  // 1. Fetch available roles on mount
  useEffect(() => {
    async function fetchRoles() {
      setRolesLoading(true);
      try {
        const res = await fetch('/v1/roles');
        if (res.ok) {
          const data: RoleItem[] = await res.json();
          setRoles(data);
          if (!selectedRoleId && data.length > 0) {
            setSelectedRoleId(data[0].role_id);
          }
        }
      } catch (err) {
        console.error('Failed to load roles in onboarding:', err);
      } finally {
        setRolesLoading(false);
      }
    }
    fetchRoles();
  }, []);

  // 2. Fetch requirements whenever selectedRoleId changes
  useEffect(() => {
    if (!selectedRoleId) return;
    async function fetchReqs() {
      setReqsLoading(true);
      try {
        const [reqsRes, profileRes] = await Promise.all([
          fetch(`/v1/roles/${selectedRoleId}/requirements`),
          fetch('/v1/profile'),
        ]);

        const verifiedMap: Record<number, { is_verified: boolean; verified_level: number }> = {};
        const existingRatings: Record<number, number> = {};
        if (profileRes.ok) {
          const profile = await profileRes.json();
          if (profile.skills && Array.isArray(profile.skills)) {
            profile.skills.forEach((s: any) => {
              existingRatings[s.skill_id] = s.declared_level;
              verifiedMap[s.skill_id] = {
                is_verified: Boolean(s.is_verified),
                verified_level: Number(s.verified_level || 0),
              };
            });
          }
        }
        setProfileVerifiedState(verifiedMap);

        if (reqsRes.ok) {
          const detail = await reqsRes.json();
          const items: RoleRequirementItem[] = detail.requirements || [];
          setRequirements(items);

          // Populate ratings with existing profile or default to 0
          setSkillRatings((prev) => {
            const next = { ...prev };
            items.forEach((req) => {
              if (next[req.skill_id] === undefined) {
                next[req.skill_id] = existingRatings[req.skill_id] ?? 0;
              }
            });
            return next;
          });
        }
      } catch (err) {
        console.error('Failed to load role requirements:', err);
      } finally {
        setReqsLoading(false);
      }
    }
    fetchReqs();
  }, [selectedRoleId]);

  // Skill Rating selection handler
  function handleSelectSkillLevel(skillId: number, level: number) {
    setSkillRatings((prev) => ({
      ...prev,
      [skillId]: level,
    }));
  }

  // Weekly hours selection & validation
  function handlePresetHours(hrs: number) {
    setWeeklyHours(hrs);
    setCustomHoursInput(String(hrs));
    setHoursError(null);
  }

  function handleCustomHoursChange(e: React.ChangeEvent<HTMLInputElement>) {
    const valStr = e.target.value;
    setCustomHoursInput(valStr);
    const num = Number(valStr);
    if (isNaN(num) || num < 1 || num > 80) {
      setHoursError('Weekly hours must be between 1 and 80 hours/week.');
    } else {
      setHoursError(null);
      setWeeklyHours(num);
    }
  }

  // Plan generation execution pipeline
  async function executePlanGeneration(allowReplace = false) {
    if (!selectedRoleId) return;
    setSubmitting(true);
    setSubmitError(null);
    setStep(4);

    try {
      // Phase A: Persist role-relevant self-assessments to Student Profile (preserving verified status)
      setSubmissionPhase('Saving competency ratings to student profile...');
      const skillsPayload = Object.entries(skillRatings).map(([idStr, level]) => {
        const sid = Number(idStr);
        const ver = profileVerifiedState[sid];
        return {
          skill_id: sid,
          declared_level: level,
          verified_level: ver?.verified_level ?? 0,
          is_verified: ver?.is_verified ?? false,
        };
      });

      const profileRes = await fetch('/v1/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_role_id: selectedRoleId,
          weekly_hours: weeklyHours,
          skills: skillsPayload,
        }),
      });

      if (!profileRes.ok) {
        const body = await profileRes.json().catch(() => null);
        throw new Error(body?.detail ?? `Failed to update profile (HTTP ${profileRes.status})`);
      }

      // Phase B: Invoke C++20 LearningPathEngine and create persistent Career Mission with Idempotency Key
      setSubmissionPhase("Invoking C++20 LearningPathEngine (Kahn's topological sort & prerequisite closure)...");
      if (!attemptIdemKeyRef.current || allowReplace) {
        attemptIdemKeyRef.current = `onboard-${selectedRoleId}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      }
      const currentIdemKey = attemptIdemKeyRef.current;

      const missionRes = await fetch('/v1/missions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': currentIdemKey,
        },
        body: JSON.stringify({
          target_role_id: selectedRoleId,
          weekly_hours: weeklyHours,
          allow_replace_active: allowReplace,
          idempotency_key: currentIdemKey,
        }),
      });

      if (missionRes.status === 409) {
        // Active mission conflict: an active mission already exists and requires explicit student confirmation
        try {
          const activeCheck = await fetch('/v1/missions/active');
          if (activeCheck.ok) {
            const activeData: CareerMission = await activeCheck.json();
            setConflictingMission(activeData);
          }
        } catch {
          // Fall through to confirmation modal
        }

        setShowReplaceConfirmModal(true);
        setSubmitting(false);
        setStep(3); // return to Step 3 so student can review or confirm replace
        return;
      }

      if (!missionRes.ok) {
        const body = await missionRes.json().catch(() => null);
        throw new Error(body?.detail ?? `Failed to create Career Mission (HTTP ${missionRes.status})`);
      }

      setSubmissionPhase('Structuring initial milestones and registered tasks...');
      const created: CareerMission = await missionRes.json();
      attemptIdemKeyRef.current = null; // Clear key on completed creation
      setCreatedMission(created);
      setStep(5); // Advance to Success Screen
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Plan generation failed');
    } finally {
      setSubmitting(false);
    }
  }

  const selectedRole = roles.find((r) => r.role_id === selectedRoleId);

  return (
    <div className="onboarding-overlay" id="onboarding-flow-container">
      <div className="onboarding-modal-card">
        {/* Onboarding Stepper Header */}
        <div className="onboarding-stepper-header">
          <div className="onboarding-brand">
            <span className="onboarding-mark">✦</span>
            <span>
              InternPath <b>Onboarding</b>
            </span>
          </div>

          <div className="stepper-dots-container">
            <div className={`step-dot-item ${step === 1 ? 'active' : step > 1 ? 'completed' : ''}`}>
              <span className="dot-num">{step > 1 ? '✓' : '1'}</span>
              <span className="dot-label">Goal</span>
            </div>
            <div className="stepper-connector" />
            <div className={`step-dot-item ${step === 2 ? 'active' : step > 2 ? 'completed' : ''}`}>
              <span className="dot-num">{step > 2 ? '✓' : '2'}</span>
              <span className="dot-label">Skills</span>
            </div>
            <div className="stepper-connector" />
            <div className={`step-dot-item ${step === 3 ? 'active' : step > 3 ? 'completed' : ''}`}>
              <span className="dot-num">{step > 3 ? '✓' : '3'}</span>
              <span className="dot-label">Time</span>
            </div>
            <div className="stepper-connector" />
            <div className={`step-dot-item ${step >= 4 ? 'active' : ''}`}>
              <span className="dot-num">{step === 5 ? '✓' : '4'}</span>
              <span className="dot-label">Roadmap</span>
            </div>
          </div>

          <button
            id="btn-onboarding-cancel"
            className="onboarding-close-btn"
            onClick={onCancel}
            title="Exit Onboarding"
          >
            ✕
          </button>
        </div>

        {/* STEP 1: YOUR GOAL */}
        {step === 1 && (
          <div className="onboarding-step-body" id="onboarding-step-1">
            <div className="step-intro-box">
              <div className="eyebrow">STEP 1 • CAREER OBJECTIVE</div>
              <h2>What internship are you preparing for?</h2>
              <p className="step-subtext">
                Choose a career path. We'll help you understand what employers require and build a
                realistic, prerequisite-aware learning plan.
              </p>
            </div>

            <div className="onboarding-demo-notice">
              <span>
                ℹ <b>Illustrative Catalogue Fixtures:</b> Sample roles demonstrate genuine C++20 graph
                planning. Real Sri Lankan Embedded / IoT vacancies will be expanded in Refinement R3.
              </span>
            </div>

            {rolesLoading ? (
              <div className="loading-state">
                <span className="spinner" /> Loading internship catalogue...
              </div>
            ) : (
              <div className="onboarding-roles-grid">
                {roles.map((r) => {
                  const isSelected = r.role_id === selectedRoleId;
                  return (
                    <div
                      key={r.role_id}
                      id={`onboarding-role-card-${r.role_id}`}
                      className={`onboarding-role-card ${isSelected ? 'selected' : ''}`}
                      onClick={() => setSelectedRoleId(r.role_id)}
                      tabIndex={0}
                      role="button"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          setSelectedRoleId(r.role_id);
                        }
                      }}
                    >
                      <div className="role-card-top-row">
                        <strong className="role-title">{r.title}</strong>
                        <span className="role-demo-pill">DEMO ROLE</span>
                      </div>
                      <div className="role-meta-row">
                        <span className="badge-dept">{r.department}</span>
                        <span className="badge-location">📍 {r.location}</span>
                      </div>
                      <p className="role-card-desc">{r.description}</p>
                      <div className="role-card-bottom-row">
                        <span className="req-count">{r.requirements_count} required competencies</span>
                        <span className="select-check">{isSelected ? '✓ Selected' : 'Select →'}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="onboarding-footer-actions">
              <button className="btn-secondary" onClick={onCancel}>
                Cancel
              </button>
              <button
                id="btn-onboarding-step1-continue"
                className="btn-primary"
                disabled={!selectedRoleId}
                onClick={() => setStep(2)}
              >
                Continue to Skills Assessment →
              </button>
            </div>
          </div>
        )}

        {/* STEP 2: YOUR SKILLS */}
        {step === 2 && (
          <div className="onboarding-step-body" id="onboarding-step-2">
            <div className="step-intro-box">
              <div className="eyebrow">STEP 2 • SELF-ASSESSMENT</div>
              <h2>What do you already know?</h2>
              <p className="step-subtext">
                You don't need to be an expert. Select the level that best describes you today for{' '}
                <b>{selectedRole?.title}</b>. We will fill any missing gaps in your roadmap.
              </p>
            </div>

            <div className="level-legend-card">
              <div className="legend-title">Canonical Proficiency Scale (0–3):</div>
              <div className="legend-items-grid">
                <div className="legend-item">
                  <span className="legend-pill level-0">0: Not Learned</span>
                  <span>Never studied or built projects with this technology</span>
                </div>
                <div className="legend-item">
                  <span className="legend-pill level-1">1: Basic</span>
                  <span>Understand core syntax, basic terminology, or coursework</span>
                </div>
                <div className="legend-item">
                  <span className="legend-pill level-2">2: Working</span>
                  <span>Can implement functional components and debug independently</span>
                </div>
                <div className="legend-item">
                  <span className="legend-pill level-3">3: Advanced</span>
                  <span>Production-grade design, performance profiling, optimization</span>
                </div>
              </div>
            </div>

            {reqsLoading ? (
              <div className="loading-state">
                <span className="spinner" /> Loading role competency requirements...
              </div>
            ) : requirements.length === 0 ? (
              <div className="empty-state">
                <p>No specific competency requirements found for this role.</p>
              </div>
            ) : (
              <div className="skills-assessment-list">
                {requirements.map((req) => {
                  const currentLevel = skillRatings[req.skill_id] ?? 0;
                  return (
                    <div
                      key={req.skill_id}
                      id={`skill-assessment-row-${req.skill_id}`}
                      className="skill-assessment-card"
                    >
                      <div className="skill-card-header">
                        <div className="skill-title-group">
                          <strong>{req.skill_name}</strong>
                          <span className="skill-req-target">
                            Target: Level {req.required_level}/3
                          </span>
                        </div>
                        <div>
                          {req.mandatory ? (
                            <span className="badge-mandatory">★ Mandatory Core</span>
                          ) : (
                            <span className="badge-optional">○ Preferred Elective</span>
                          )}
                        </div>
                      </div>

                      <div className="skill-context-hint">
                        {req.role_context || 'Standard role requirement.'}
                      </div>

                      {/* 0 to 3 Level Buttons */}
                      <div className="competency-selector-row">
                        <span className="selector-label">Your Current Level:</span>
                        <div className="selector-buttons-group">
                          {[0, 1, 2, 3].map((lvl) => {
                            const isChosen = currentLevel === lvl;
                            return (
                              <button
                                key={lvl}
                                type="button"
                                className={`rating-btn ${isChosen ? 'active' : ''}`}
                                onClick={() => handleSelectSkillLevel(req.skill_id, lvl)}
                              >
                                <span className="btn-lvl-num">{lvl}</span>
                                <span className="btn-lvl-name">
                                  {lvl === 0
                                    ? 'None'
                                    : lvl === 1
                                    ? 'Basic'
                                    : lvl === 2
                                    ? 'Working'
                                    : 'Advanced'}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="onboarding-footer-actions">
              <button className="btn-secondary" onClick={() => setStep(1)}>
                ← Back
              </button>
              <button
                id="btn-onboarding-step2-continue"
                className="btn-primary"
                onClick={() => setStep(3)}
              >
                Continue to Availability →
              </button>
            </div>
          </div>
        )}

        {/* STEP 3: YOUR TIME */}
        {step === 3 && (
          <div className="onboarding-step-body" id="onboarding-step-3">
            <div className="step-intro-box">
              <div className="eyebrow">STEP 3 • WEEKLY AVAILABILITY</div>
              <h2>How much time can you spend learning?</h2>
              <p className="step-subtext">
                Be realistic with your university coursework. Our C++ planner uses your weekly
                availability to estimate milestones and ensure your plan is achievable.
              </p>
            </div>

            {/* Presets Grid */}
            <div className="hours-presets-grid">
              {[
                { hrs: 5, label: 'Steady Pace', desc: '5 hours/week • Steady pace alongside academic courses' },
                { hrs: 10, label: 'Moderate Pace', desc: '10 hours/week • Balanced semester commitment' },
                { hrs: 15, label: 'Dedicated Track', desc: '15 hours/week • Focused skill building' },
                { hrs: 20, label: 'Intensive Track', desc: '20 hours/week • Vacation or dedicated study period' },
              ].map((preset) => {
                const isSelected = weeklyHours === preset.hrs;
                return (
                  <div
                    key={preset.hrs}
                    className={`hours-preset-card ${isSelected ? 'selected' : ''}`}
                    onClick={() => handlePresetHours(preset.hrs)}
                  >
                    <div className="preset-top">
                      <span className="preset-hrs">{preset.hrs}</span>
                      <span className="preset-unit">hrs/wk</span>
                      {isSelected && <span className="preset-check">✓</span>}
                    </div>
                    <strong>{preset.label}</strong>
                    <p>{preset.desc}</p>
                  </div>
                );
              })}
            </div>

            {/* Custom Hours Input */}
            <div className="custom-hours-box">
              <label htmlFor="custom-hours-input">
                <strong>Or enter custom weekly hours:</strong>
              </label>
              <div className="custom-hours-input-row">
                <input
                  id="custom-hours-input"
                  type="number"
                  min="1"
                  max="80"
                  value={customHoursInput}
                  onChange={handleCustomHoursChange}
                  className="hours-input-field"
                />
                <span className="input-suffix">hours per week</span>
              </div>
              {hoursError && <div className="hours-error-text">⚠️ {hoursError}</div>}
            </div>

            {/* Truthful Deadline Notice */}
            <div className="deadline-status-card">
              <div className="deadline-header">
                <span className="deadline-icon">ℹ</span>
                <strong>Internship deadline not confirmed</strong>
              </div>
              <p>
                Verified employer application closing dates will be shown here when officially
                announced. Your roadmap is organized into topological stages so you can begin
                mastering foundational skills immediately.
              </p>
            </div>

            <div className="onboarding-footer-actions">
              <button className="btn-secondary" onClick={() => setStep(2)}>
                ← Back
              </button>
              <button
                id="btn-onboarding-build-roadmap"
                className="btn-primary btn-large"
                disabled={Boolean(hoursError) || submitting}
                onClick={() => {
                  if (hasExistingActiveMission) {
                    setShowReplaceConfirmModal(true);
                  } else {
                    executePlanGeneration(false);
                  }
                }}
              >
                {submitting ? 'Generating...' : '🚀 Build My Roadmap'}
              </button>
            </div>
          </div>
        )}

        {/* STEP 4: PROCESSING / LOADING STATE */}
        {step === 4 && (
          <div className="onboarding-step-body onboarding-step-loading" id="onboarding-step-4">
            <div className="engine-processing-box">
              <div className="spinner-large" />
              <h3>Generating Your Personalized Career Mission</h3>
              <p className="processing-phase-text">{submissionPhase}</p>

              <div className="engine-checklist">
                <div className="chk-item active">
                  <span className="chk-icon">⚙</span>
                  <span>C++20 LearningPathEngine: Kahn's topological sort</span>
                </div>
                <div className="chk-item active">
                  <span className="chk-icon">🛡</span>
                  <span>Prerequisite closure validation & cycle detection</span>
                </div>
                <div className="chk-item active">
                  <span className="chk-icon">◈</span>
                  <span>Creating immutable Version 1.0 Career Mission</span>
                </div>
              </div>

              {submitError && (
                <div className="onboarding-error-banner">
                  <strong>⚠️ Generation Error:</strong> {submitError}
                  <div style={{ marginTop: '12px' }}>
                    <button
                      className="btn-primary"
                      disabled={submitting}
                      onClick={() => executePlanGeneration(false)}
                    >
                      Try Again
                    </button>
                    <button
                      className="btn-secondary"
                      style={{ marginLeft: '8px' }}
                      onClick={() => setStep(3)}
                    >
                      Adjust Inputs
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* STEP 5: SUCCESS & SUMMARY */}
        {step === 5 && createdMission && (
          <div className="onboarding-step-body" id="onboarding-step-5">
            <div className="success-hero-box">
              <div className="success-check-badge">✓</div>
              <div className="eyebrow-accent">ROADMAP INITIALIZED</div>
              <h2>Your roadmap is ready!</h2>
              <p className="success-subtext">
                Your career mission for <b>{createdMission.title}</b> has been generated by the C++20
                planning engine and saved to your profile.
              </p>
            </div>

            {/* Generated Metrics Grid */}
            <div className="mission-stats-summary-grid">
              <div className="mission-summary-card">
                <span className="stat-label">Planned Stages</span>
                <span className="stat-val">
                  {createdMission.active_version?.stages.length || 0} Stages
                </span>
                <small className="stat-desc">Topologically partitioned</small>
              </div>

              <div className="mission-summary-card">
                <span className="stat-label">Total Milestones</span>
                <span className="stat-val">{createdMission.total_tasks} Tasks</span>
                <small className="stat-desc">Atomic competencies</small>
              </div>

              <div className="mission-summary-card">
                <span className="stat-label">Total Effort</span>
                <span className="stat-val">
                  {createdMission.estimated_remaining_hours_min}–
                  {createdMission.estimated_remaining_hours_max} hrs
                </span>
                <small className="stat-desc">
                  Pacing estimate: ~{Math.ceil((createdMission.estimated_remaining_hours_max || 10) / weeklyHours)} weeks
                  at {weeklyHours} hrs/wk (actual duration depends on prior background)
                </small>
              </div>
            </div>

            {/* Initial Recommended Task Card */}
            {createdMission.active_version?.tasks && createdMission.active_version.tasks.length > 0 && (
              <div className="first-task-preview-card">
                <div className="first-task-header">
                  <span className="badge-first-action">🎯 INITIAL RECOMMENDED TASK</span>
                  <span className="badge-category">
                    {createdMission.active_version.tasks[0].category}
                  </span>
                </div>
                <h4>{createdMission.active_version.tasks[0].skill_name}</h4>
                <p className="criteria-text">
                  <b>Completion Criteria:</b>{' '}
                  {createdMission.active_version.tasks[0].completion_criteria}
                </p>
                <div className="task-effort-tag">
                  Estimated Effort: {createdMission.active_version.tasks[0].estimated_hours_min}–
                  {createdMission.active_version.tasks[0].estimated_hours_max} hours
                </div>
              </div>
            )}

            <div className="onboarding-footer-actions success-footer">
              <button
                id="btn-onboarding-goto-roadmap"
                className="btn-primary btn-large"
                onClick={() => onComplete(createdMission)}
              >
                Go to My Roadmap →
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Confirmation Modal for Overwriting Existing Active Mission */}
      {showReplaceConfirmModal && (
        <div className="modal-backdrop-alert" id="onboarding-confirm-replace-modal">
          <div className="modal-dialog-alert">
            <div className="alert-icon-top">⚠️</div>
            <h3>Active Career Mission Detected</h3>
            <p>
              You already have an active Career Mission{' '}
              {conflictingMission ? (
                <b>({conflictingMission.target_role_title || conflictingMission.title})</b>
              ) : existingMissionTitle ? (
                <b>({existingMissionTitle})</b>
              ) : (
                'in progress'
              )}
              .
            </p>
            {conflictingMission && (
              <div className="alert-detail-box" style={{ background: '#f8fafc', padding: '12px', borderRadius: '8px', marginBottom: '12px', fontSize: '0.85rem' }}>
                <div>• <b>Created:</b> {conflictingMission.created_at ? new Date(conflictingMission.created_at).toLocaleDateString() : 'Active session'}</div>
                <div>• <b>Progress:</b> {conflictingMission.completed_tasks} of {conflictingMission.total_tasks} tasks completed ({conflictingMission.progress_percent}%)</div>
                <div>• <b>Weekly Capacity:</b> {conflictingMission.weekly_hours} hrs/week</div>
              </div>
            )}
            <p className="alert-detail-text">
              Generating a new mission will <b>archive your current mission</b> while preserving all
              previously completed tasks and attached evidence records in your historical audit trail.
            </p>
            <div className="modal-actions-row" style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              {conflictingMission && (
                <button
                  type="button"
                  id="btn-keep-existing-mission"
                  className="btn-primary"
                  onClick={() => {
                    setShowReplaceConfirmModal(false);
                    onComplete(conflictingMission);
                  }}
                >
                  Keep Existing Mission & View Roadmap →
                </button>
              )}
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setShowReplaceConfirmModal(false)}
              >
                Back to Settings
              </button>
              <button
                type="button"
                id="btn-confirm-replace-mission"
                className="btn-danger"
                onClick={() => {
                  setShowReplaceConfirmModal(false);
                  executePlanGeneration(true);
                }}
              >
                Archive & Create New Mission →
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
