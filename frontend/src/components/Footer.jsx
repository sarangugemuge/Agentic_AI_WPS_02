const CURRENT_YEAR = new Date().getFullYear();

export function Footer({ onNavigate }) {
  return (
    <footer className="footer">
      <div className="container footer-content">
        <div className="footer-top">
          <div className="footer-brand">
            <div className="footer-logo-row">
              <img src="/logo.png" alt="SkillSync" className="footer-logo" />
              <span className="navbar-wordmark">SkillSync</span>
            </div>
            <p className="text-muted text-sm footer-desc">
              AI-powered skill verification and career coaching. Match real GitHub source code,
              commits, and project architectures against job descriptions with zero hallucinations.
            </p>
          </div>

          <div className="footer-links-grid">
            <div className="footer-col">
              <h4 className="footer-col-title">Navigation</h4>
              <ul className="footer-link-list">
                <li><button onClick={() => onNavigate('/')} className="footer-link">Home</button></li>
                <li><button onClick={() => onNavigate('/assess')} className="footer-link">New Assessment</button></li>
                <li><button onClick={() => onNavigate('/dashboard')} className="footer-link">Dashboard</button></li>
                <li><button onClick={() => onNavigate('/history')} className="footer-link">Assessment History</button></li>
              </ul>
            </div>

            <div className="footer-col">
              <h4 className="footer-col-title">Engine Features</h4>
              <ul className="footer-link-list">
                <li className="footer-static-item">Evidence-Backed Citations</li>
                <li className="footer-static-item">4-Tier Confidence Scoring</li>
                <li className="footer-static-item">Skill Gap Prioritization</li>
                <li className="footer-static-item">Owner-Controlled SQLite</li>
              </ul>
            </div>

            <div className="footer-col">
              <h4 className="footer-col-title">Architecture</h4>
              <ul className="footer-link-list">
                <li className="footer-static-item">FastAPI REST Services</li>
                <li className="footer-static-item">Gemini 2.0 Flash AI</li>
                <li className="footer-static-item">React 19 + Vite Frontend</li>
                <li className="footer-static-item">SQLAlchemy Async Engine</li>
              </ul>
            </div>
          </div>
        </div>

        <div className="footer-bottom">
          <div className="footer-legal">
            <span className="text-muted text-xs">
              © {CURRENT_YEAR} SkillSync. All assessment data stored locally in owner-controlled database.
            </span>
          </div>
          <div className="footer-tech-badges">
            <span className="badge badge-outline text-xs">FastAPI · Gemini AI · React</span>
          </div>
        </div>
      </div>
    </footer>
  );
}

