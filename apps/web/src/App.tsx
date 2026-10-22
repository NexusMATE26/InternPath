import { useState } from 'react';

type Result = { earned_points: number; max_points: number; missing_mandatory: number; mandatory_requirements_met: boolean; coverage_percent: number };
const skills = [
  { name: 'C++', target: 2, weight: 5, mandatory: 1 },
  { name: 'Data Structures', target: 2, weight: 4, mandatory: 1 },
  { name: 'RTOS', target: 1, weight: 3, mandatory: 0 },
  { name: 'Git', target: 1, weight: 2, mandatory: 0 },
];

export default function App() {
  const [levels, setLevels] = useState<number[]>([2, 1, 0, 1]);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);

  async function analyze() {
    setError(''); setWorking(true);
    try {
      const response = await fetch('/v1/demo/match', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ student_levels: levels, required_levels: skills.map(s => s.target),
          weights: skills.map(s => s.weight), mandatory: skills.map(s => s.mandatory) }) });
      if (!response.ok) { const body = await response.json().catch(() => null); throw new Error(body?.detail ?? `API HTTP ${response.status}`); }
      setResult(await response.json());
    } catch (e) { setError(e instanceof Error ? e.message : 'Unknown error'); setResult(null); }
    finally { setWorking(false); }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="mark">✦</span><span>InternPath <b>AI</b></span></div>
        <div className="nav-label">WORKSPACE</div>
        <nav><div className="nav-item active">▦ &nbsp; Dashboard</div><div className="nav-item">⌕ &nbsp; Opportunities <i>soon</i></div><div className="nav-item">◈ &nbsp; Skills & Evidence <i>soon</i></div><div className="nav-item">☑ &nbsp; Career Mission <i>soon</i></div><div className="nav-item">✧ &nbsp; Agent Activity <i>soon</i></div></nav>
        <div className="sidebar-bottom">PHASE 1 • WORKING FOUNDATION<br/><small>Student features beyond this demo are not yet built.</small></div>
      </aside>
      <main>
        <header className="topbar"><span>Internship readiness / Development preview</span><span className="pill">● Local prototype</span></header>
        <div className="content">
          <div className="eyebrow">INTERNPATH ENGINE TEST</div>
          <h1>Build the path to your next opportunity.</h1>
          <p className="lede">Our first real integration: edit a sample student's declared skill levels and ask the C++20 engine to calculate requirement coverage.</p>
          <section className="hero-grid">
            <div className="panel form-panel">
              <div className="panel-header"><div><h2>Sample skill profile</h2><p>Illustrative Embedded Systems role — not a verified posting.</p></div><span className="mini-icon">⌘</span></div>
              <div className="skills-head"><span>SKILL</span><span>YOUR LEVEL</span><span>REQUIRED</span></div>
              {skills.map((skill, index) => (
                <div className="skill-row" key={skill.name}>
                  <div><strong>{skill.name}</strong><span className="metadata">{skill.mandatory ? 'Mandatory' : 'Preferred'}</span></div>
                  <select aria-label={`${skill.name} student level`} value={levels[index]} onChange={e => setLevels(old => old.map((v, i) => i === index ? Number(e.target.value) : v))}>
                    <option value={0}>0 — Not declared</option><option value={1}>1 — Basic</option><option value={2}>2 — Intermediate</option><option value={3}>3 — Advanced</option>
                  </select>
                  <span className="required-tag">Level {skill.target}</span>
                </div>
              ))}
              <button onClick={analyze} disabled={working}>{working ? 'Calculating…' : 'Recalculate with C++ Engine →'}</button>
              {error && <p className="error" role="alert">{error}</p>}
              <p className="footnote">Self-reported levels are illustrative. This number is not a hiring probability.</p>
            </div>
            <div className="panel result-panel">
              <div className="eyebrow">LIVE ENGINE OUTPUT</div>
              <div className="score">{result ? `${result.coverage_percent.toFixed(2)}%` : '—'}</div>
              <p className="result-label">Requirement coverage</p>
              <div className="progress-track"><div className="progress-fill" style={{width:`${result?.coverage_percent ?? 0}%`}} /></div>
              <div className="stat-divider" />
              <div className="stat"><span>Earned points</span><strong>{result ? `${result.earned_points} / ${result.max_points}` : '—'}</strong></div>
              <div className="stat"><span>Missing mandatory requirements</span><strong>{result?.missing_mandatory ?? '—'}</strong></div>
              <div className="stat"><span>Mandatory levels met</span><strong>{result ? (result.mandatory_requirements_met ? 'Yes' : 'Not yet') : '—'}</strong></div>
              <div className="engine-note">✓ Browser → FastAPI → C++20 → FastAPI → Browser</div>
            </div>
          </section>
          <section className="next"><div><div className="eyebrow">WHAT COMES NEXT</div><h2>A real Career Mission, not just a score.</h2><p>The next implementation stages add sourced internship requirements, evidence records, custom data structures, a prerequisite graph and the adaptive AI agent.</p></div><div className="next-mark">01 / 06</div></section>
          <footer>InternPath AI · Demo fixture only · Phase 1 starter</footer>
        </div>
      </main>
    </div>
  );
}
