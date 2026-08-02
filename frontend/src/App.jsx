import { useState, useEffect } from 'react';
import { Sparkles, CheckCircle, Clock, AlertTriangle, FileText, ChevronRight } from 'lucide-react';
import './index.css';

const API_BASE = 'http://localhost:8000';

function App() {
  const [objective, setObjective] = useState('');
  const [runId, setRunId] = useState(null);
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(false);

  // Connect to SSE when runId is present
  useEffect(() => {
    if (!runId) return;

    const evtSource = new EventSource(`${API_BASE}/research/${runId}/feed`);
    
    evtSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.error) {
        console.error("SSE Error:", data.error);
        return;
      }
      setState(data);
      
      if (data.status === 'COMPLETED' || data.status === 'FAILED') {
        evtSource.close();
      }
    };

    evtSource.onerror = () => {
      evtSource.close();
    };

    return () => evtSource.close();
  }, [runId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!objective.trim()) return;
    
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/research`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: objective })
      });
      const data = await res.json();
      setRunId(data.run_id);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleApprovePlan = async () => {
    try {
      await fetch(`${API_BASE}/research/${runId}/approve_plan`, { method: 'POST' });
    } catch (err) {
      console.error(err);
    }
  };
  
  const handleResolveEscalation = async (taskId, resolution) => {
    try {
      await fetch(`${API_BASE}/research/${runId}/resolve_escalation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId, resolution })
      });
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="container">
      {/* Hero Section (Only show if not started) */}
      {!runId && (
        <div className="hero animate-fade-in">
          <h1 className="gradient-text" style={{ fontSize: '3rem' }}>Agentic Research Copilot</h1>
          <p className="text-muted" style={{ fontSize: '1.2rem', marginBottom: '40px' }}>
            Multi-agent research workflows with human-in-the-loop orchestration.
          </p>
          
          <form onSubmit={handleSubmit} className="glass-panel" style={{ maxWidth: '600px', margin: '0 auto', display: 'flex', gap: '16px' }}>
            <input 
              type="text" 
              className="glass-input" 
              placeholder="e.g. Compare the architecture of LLaMA-3 and GPT-4" 
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
              disabled={loading}
            />
            <button type="submit" className="glass-button" disabled={loading}>
              <Sparkles size={20} />
              {loading ? 'Starting...' : 'Research'}
            </button>
          </form>
        </div>
      )}

      {/* Main Dashboard (Once started) */}
      {runId && state && (
        <div className="animate-fade-in">
          <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
            <div>
              <h2 className="gradient-text" style={{ margin: 0 }}>Research Run</h2>
              <p className="text-muted">{runId}</p>
            </div>
            <div className={`status-badge ${state.status.toLowerCase()}`}>
              {state.status.replace(/_/g, ' ')}
            </div>
          </header>

          {/* Plan Approval View */}
          {state.status === 'WAITING_FOR_APPROVAL' && (
            <div className="glass-panel animate-fade-in">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Clock size={24} className="text-warning" />
                Plan Review Required
              </h3>
              <p className="text-muted">The Planner Agent has generated the following tasks. Please approve to continue.</p>
              
              <div style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {Object.keys(state.tasks).map((taskId) => (
                  <div key={taskId} style={{ padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', border: '1px solid var(--glass-border)' }}>
                    <strong>{taskId}</strong>
                    {state.task_details && state.task_details[taskId] && (
                        <p className="text-muted" style={{ marginTop: '8px', fontSize: '0.95rem' }}>{state.task_details[taskId]}</p>
                    )}
                  </div>
                ))}
              </div>

              <div style={{ marginTop: '32px', display: 'flex', gap: '16px' }}>
                <button className="glass-button" onClick={handleApprovePlan}>Approve Plan</button>
              </div>
            </div>
          )}

          {/* Live DAG Feed */}
          {state.status !== 'WAITING_FOR_APPROVAL' && state.status !== 'PLANNING' && (
            <div className="grid">
              <div className="glass-panel">
                <h3>Live Execution Feed</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '24px' }}>
                  {Object.entries(state.tasks).map(([taskId, status]) => (
                    <div key={taskId} style={{ padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', border: '1px solid var(--glass-border)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <strong>{taskId}</strong>
                        <span className={`status-badge ${status.toLowerCase()}`}>{status}</span>
                      </div>
                      
                      {state.task_details && state.task_details[taskId] && (
                        <div style={{ marginTop: '8px', fontSize: '0.9rem', color: 'var(--text-main)' }}>
                          {state.task_details[taskId]}
                        </div>
                      )}
                      
                      {state.findings[taskId] && (
                        <div style={{ marginTop: '12px', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                          <em>"{state.findings[taskId]}"</em>
                        </div>
                      )}
                      
                      {status === 'ESCALATED' && (
                        <div style={{ marginTop: '16px', padding: '16px', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '8px', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
                          <h4 style={{ color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: '8px', margin: '0 0 12px 0' }}>
                            <AlertTriangle size={18} />
                            Action Required
                          </h4>
                          <p style={{ fontSize: '0.9rem', marginBottom: '16px' }}>The evaluator flagged a conflict or low confidence.</p>
                          <div style={{ display: 'flex', gap: '12px' }}>
                            <button className="glass-button secondary" style={{ padding: '8px 16px', fontSize: '0.9rem' }} onClick={() => handleResolveEscalation(taskId, 'retry')}>Force Retry</button>
                            <button className="glass-button" style={{ padding: '8px 16px', fontSize: '0.9rem' }} onClick={() => handleResolveEscalation(taskId, 'accept')}>Accept Anyway</button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Final Report View */}
              {state.report && (
                <div className="glass-panel animate-fade-in" style={{ gridColumn: 'span 2' }}>
                  <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <FileText size={24} className="text-primary" />
                    Synthesis Report
                  </h3>
                  
                  <div style={{ marginTop: '24px' }}>
                    <h4 className="gradient-text">Executive Recommendation</h4>
                    <p style={{ lineHeight: 1.6 }}>{state.report.executive_recommendation}</p>
                    
                    <h4 className="gradient-text" style={{ marginTop: '32px' }}>Comparison</h4>
                    <table>
                      <thead>
                        <tr>
                          <th>Feature / Metric</th>
                          <th>Details</th>
                        </tr>
                      </thead>
                      <tbody>
                        {state.report.comparison_table.map((row, i) => (
                          <tr key={i}>
                            <td style={{ fontWeight: 500 }}>{row.feature_or_metric}</td>
                            <td className="text-muted">{row.details}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                    <h4 className="gradient-text" style={{ marginTop: '32px' }}>Limitations & Confidence</h4>
                    <p style={{ lineHeight: 1.6, color: 'var(--text-muted)' }}>{state.report.confidence_limitations}</p>

                    <h4 className="gradient-text" style={{ marginTop: '32px' }}>Citations</h4>
                    <ul style={{ listStyle: 'none', padding: 0 }}>
                      {Object.entries(state.report.citations || {}).map(([key, url]) => (
                        <li key={key} style={{ marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <ChevronRight size={16} className="text-primary" />
                          <strong>{key}:</strong> 
                          <a href={url} target="_blank" rel="noreferrer" style={{ color: 'var(--secondary)' }}>{url}</a>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default App;
