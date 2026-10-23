import { useState, useEffect, useCallback } from 'react';
import CareerMissionView, { CareerMission, EvidenceItem } from './components/CareerMissionView';
import { HomeView } from './components/HomeView';
import { CareersView, RoleItem } from './components/CareersView';
import { ReadinessView, Skill, StudentSkillState } from './components/ReadinessView';
import { TechnicalModeView } from './components/TechnicalModeView';
import { AssistantDrawer } from './components/AssistantDrawer';
import { OnboardingFlow } from './components/OnboardingFlow';

interface StudentProfile {
  id: number;
  name: string;
  email: string;
  target_role_id?: string | null;
  weekly_hours: number;
  is_demo: boolean;
  skills: Array<{
    skill_id: number;
    skill_name: string;
    category: string;
    declared_level: number;
    verified_level: number;
    is_verified: boolean;
  }>;
  evidence: EvidenceItem[];
}

export type MainTab = 'home' | 'careers' | 'roadmap' | 'readiness' | 'technical';

export default function App() {
  // Primary Student Navigation (default: 'home')
  const [activeTab, setActiveTab] = useState<MainTab>('home');
  const [assistantOpen, setAssistantOpen] = useState(false);

  // Guided Onboarding State (R1.2)
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [onboardingInitialRole, setOnboardingInitialRole] = useState<string | null>(null);
  const [activeMission, setActiveMission] = useState<CareerMission | null>(null);

  // Core Data State (persisted via FastAPI & database)
  const [skills, setSkills] = useState<Skill[]>([]);
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [selectedRoleId, setSelectedRoleId] = useState<string>('distributed-systems-intern');
  const [studentSkills, setStudentSkills] = useState<Record<number, StudentSkillState>>({});
  const [studentName, setStudentName] = useState('Alex Chen (Dev Mode)');
  const [weeklyHours, setWeeklyHours] = useState(15);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);

  // Profile save state
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSaveSuccess, setProfileSaveSuccess] = useState(false);
  const [profileSaveError, setProfileSaveError] = useState('');

  // C++ Learning Path Engine plan state
  const [plan, setPlan] = useState<any | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [, setPlanError] = useState('');

  // Load initial skills, roles, active mission, and persisted student profile
  const loadInitialData = useCallback(async () => {
    try {
      const [skillsRes, rolesRes, profileRes, missionRes] = await Promise.all([
        fetch('/v1/skills'),
        fetch('/v1/roles'),
        fetch('/v1/profile'),
        fetch('/v1/missions/active'),
      ]);

      if (missionRes.ok) {
        const missionData: CareerMission = await missionRes.json();
        setActiveMission(missionData);
      } else {
        setActiveMission(null);
      }

        if (skillsRes.ok && rolesRes.ok) {
          const loadedSkills: Skill[] = await skillsRes.json();
          const loadedRoles: RoleItem[] = await rolesRes.json();
          setSkills(loadedSkills);
          setRoles(loadedRoles);

          const initialMap: Record<number, StudentSkillState> = {};
          loadedSkills.forEach((s) => {
            initialMap[s.id] = { level: 0, is_verified: false };
          });

          if (profileRes.ok) {
            const profile: StudentProfile = await profileRes.json();
            setStudentName(profile.name);
            setWeeklyHours(profile.weekly_hours);
            if (profile.target_role_id) {
              setSelectedRoleId(profile.target_role_id);
            }
            if (profile.evidence) {
              setEvidenceList(profile.evidence);
            }
            profile.skills.forEach((ps) => {
              initialMap[ps.skill_id] = {
                level: ps.declared_level,
                is_verified: ps.is_verified,
              };
            });
          } else {
            // Default fallback
            if (initialMap[1]) initialMap[1] = { level: 2, is_verified: true };
            if (initialMap[2]) initialMap[2] = { level: 2, is_verified: true };
            if (initialMap[7]) initialMap[7] = { level: 1, is_verified: false };
          }
          setStudentSkills(initialMap);
        }
      } catch (err) {
        console.error('Failed to load initial data:', err);
      }
    },
    []
  );

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Launch guided onboarding (R1.2)
  function handleStartOnboarding(roleId?: string) {
    setOnboardingInitialRole(roleId || selectedRoleId || null);
    setOnboardingOpen(true);
  }

  // Handle successful onboarding completion
  function handleOnboardingComplete(newMission: CareerMission) {
    setActiveMission(newMission);
    if (newMission.target_role_id) {
      setSelectedRoleId(newMission.target_role_id);
    }
    setOnboardingOpen(false);
    setActiveTab('roadmap');
    loadInitialData();
  }

  // Update a single skill's declared or verified state
  function handleSkillChange(skillId: number, level: number, isVerified: boolean) {
    setStudentSkills((prev) => ({
      ...prev,
      [skillId]: { level, is_verified: isVerified },
    }));
  }

  // Persist Profile changes to DB (PUT /v1/profile)
  async function saveProfile() {
    setProfileSaving(true);
    setProfileSaveError('');
    setProfileSaveSuccess(false);
    try {
      const skillsPayload = Object.entries(studentSkills).map(([idStr, val]) => ({
        skill_id: Number(idStr),
        declared_level: val.level,
        verified_level: val.is_verified ? val.level : 0,
        is_verified: val.is_verified,
      }));

      const res = await fetch('/v1/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: studentName,
          target_role_id: selectedRoleId,
          weekly_hours: weeklyHours,
          skills: skillsPayload,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      setProfileSaveSuccess(true);
      setTimeout(() => setProfileSaveSuccess(false), 3500);
    } catch (err) {
      setProfileSaveError(err instanceof Error ? err.message : 'Failed to save profile');
    } finally {
      setProfileSaving(false);
    }
  }

  // Generate Learning Path via C++20 engine
  async function generateLearningPath() {
    setPlanError('');
    setPlanLoading(true);
    try {
      const studentPayload = Object.entries(studentSkills)
        .filter(([, val]) => val.level > 0)
        .map(([idStr, val]) => ({
          skill_id: Number(idStr),
          level: val.level,
          is_verified: val.is_verified,
        }));

      const response = await fetch('/v1/learning-path/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role_id: selectedRoleId,
          student_skills: studentPayload,
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `API HTTP ${response.status}`);
      }

      const generatedPlan = await response.json();
      setPlan(generatedPlan);
    } catch (e) {
      setPlanError(e instanceof Error ? e.message : 'Failed to generate learning plan');
      setPlan(null);
    } finally {
      setPlanLoading(false);
    }
  }

  const selectedRole = roles.find((r) => r.role_id === selectedRoleId);

  return (
    <div className="shell">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="brand" onClick={() => setActiveTab('home')} style={{ cursor: 'pointer' }}>
          <span className="mark">✦</span>
          <span>
            InternPath <b>AI</b>
          </span>
        </div>

        <div className="nav-label">STUDENT WORKSPACE</div>
        <nav>
          <div
            id="nav-home"
            className={`nav-item ${activeTab === 'home' ? 'active' : ''}`}
            onClick={() => setActiveTab('home')}
          >
            🏠 &nbsp; Home
          </div>

          <div
            id="nav-careers"
            className={`nav-item ${activeTab === 'careers' ? 'active' : ''}`}
            onClick={() => setActiveTab('careers')}
          >
            🎯 &nbsp; Careers & Roles
          </div>

          <div
            id="nav-roadmap"
            className={`nav-item ${activeTab === 'roadmap' ? 'active' : ''}`}
            onClick={() => setActiveTab('roadmap')}
          >
            🛤 &nbsp; Active Roadmap
          </div>

          <div
            id="nav-readiness"
            className={`nav-item ${activeTab === 'readiness' ? 'active' : ''}`}
            onClick={() => setActiveTab('readiness')}
          >
            ◈ &nbsp; Readiness Proof Map
          </div>
        </nav>

        <div className="nav-label" style={{ marginTop: '24px' }}>EVALUATION & LAB</div>
        <nav>
          <div
            id="nav-technical-mode"
            className={`nav-item nav-item-technical ${activeTab === 'technical' ? 'active' : ''}`}
            onClick={() => setActiveTab('technical')}
          >
            🔬 &nbsp; Technical Mode
            <span className="nav-pill-badge">Judge</span>
          </div>
        </nav>

        <div className="sidebar-bottom">
          <strong>REFINEMENT R1.1 • STUDENT SHELL</strong>
          <br />
          <small>The AI proposes. The algorithms validate. The student decides.</small>
        </div>
      </aside>

      {/* Main Content Area */}
      <main>
        {/* Top Header Bar */}
        <header className="topbar">
          <div className="topbar-section-title">
            <span>
              {activeTab === 'home' && 'Student Workspace Overview'}
              {activeTab === 'careers' && 'Internship Catalogue & Competencies'}
              {activeTab === 'roadmap' && 'Active Career Mission & Milestone Roadmap'}
              {activeTab === 'readiness' && 'Skills Assessment & Evidence Verification'}
              {activeTab === 'technical' && 'Academic Demonstrator & Engine Inspector'}
            </span>
          </div>

          <div className="topbar-actions">
            <button
              id="btn-open-assistant"
              className="pill-toggle pill-assistant"
              onClick={() => setAssistantOpen(true)}
              title="Open Contextual Assistant Drawer"
            >
              ✦ Assistant
            </button>

            <button
              id="btn-toggle-technical-mode"
              className={`pill-toggle ${activeTab === 'technical' ? 'active' : ''}`}
              onClick={() => setActiveTab(activeTab === 'technical' ? 'home' : 'technical')}
              title="Toggle Academic & Evaluator Workspace"
            >
              🔬 {activeTab === 'technical' ? 'Exit Technical Mode' : 'Technical / Judge Mode'}
            </button>

            <span className="pill pill-engine-verified" title="Handwritten C++20 Core Algorithms">
              ● C++20 Engine Verified
            </span>
          </div>
        </header>

        {/* View Routing Body */}
        <div className="content">
          {/* TAB 1: HOME VIEW */}
          {activeTab === 'home' && (
            <HomeView
              onNavigateToRoadmap={() => setActiveTab('roadmap')}
              onNavigateToCareers={() => setActiveTab('careers')}
              onNavigateToReadiness={() => setActiveTab('readiness')}
              onNavigateToTechnical={() => setActiveTab('technical')}
              onStartOnboarding={handleStartOnboarding}
            />
          )}

          {/* TAB 2: CAREERS VIEW */}
          {activeTab === 'careers' && (
            <CareersView
              roles={roles}
              selectedRoleId={selectedRoleId}
              onSelectRole={(id) => setSelectedRoleId(id)}
              onNavigateToRoadmap={() => setActiveTab('roadmap')}
              onNavigateToReadiness={() => setActiveTab('readiness')}
              onStartOnboarding={handleStartOnboarding}
              studentSkills={studentSkills}
            />
          )}

          {/* TAB 3: ROADMAP (CAREER MISSION) VIEW */}
          {activeTab === 'roadmap' && (
            <CareerMissionView
              onNavigateToPlanner={() => setActiveTab('careers')}
              availableRoles={roles}
              evidenceList={evidenceList}
              onStartOnboarding={handleStartOnboarding}
            />
          )}

          {/* TAB 4: READINESS PROOF MAP VIEW */}
          {activeTab === 'readiness' && (
            <ReadinessView
              skills={skills}
              studentSkills={studentSkills}
              onSkillChange={handleSkillChange}
              studentName={studentName}
              weeklyHours={weeklyHours}
              onWeeklyHoursChange={setWeeklyHours}
              evidenceList={evidenceList}
              onSaveProfile={saveProfile}
              saving={profileSaving}
              saveSuccess={profileSaveSuccess}
              saveError={profileSaveError}
              onNavigateToRoadmap={() => setActiveTab('roadmap')}
            />
          )}

          {/* TAB 5: TECHNICAL / JUDGE MODE */}
          {activeTab === 'technical' && (
            <TechnicalModeView
              onBackToStudent={() => setActiveTab('home')}
              onNavigateToMission={() => setActiveTab('roadmap')}
              plan={plan}
              onGeneratePlan={generateLearningPath}
              planLoading={planLoading}
              skills={skills}
            />
          )}
        </div>
      </main>

      {/* Contextual Assistant Slide-over Drawer */}
      <AssistantDrawer
        isOpen={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        onNavigateToRoadmap={() => setActiveTab('roadmap')}
        onNavigateToCareers={() => setActiveTab('careers')}
        studentName={studentName}
        activeRoleTitle={selectedRole?.title}
        weeklyHours={weeklyHours}
      />

      {/* Guided Student Onboarding Flow (R1.2) */}
      {onboardingOpen && (
        <OnboardingFlow
          initialRoleId={onboardingInitialRole}
          hasExistingActiveMission={Boolean(activeMission)}
          existingMissionTitle={activeMission?.title}
          onComplete={handleOnboardingComplete}
          onCancel={() => setOnboardingOpen(false)}
        />
      )}
    </div>
  );
}
