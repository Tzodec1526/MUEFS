import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play } from 'lucide-react';
import { getCase, searchCases } from '../../api/cases';
import { getFilingChecklists, getFilingRequirements } from '../../api/courts';
import { listFilings } from '../../api/filings';
import { applyDemoRole } from '../auth/LoginScreen';
import { logAgentActivity } from '../../webmcp/activity';
import { sanitizeAgentText } from '../../webmcp/output';
import { useToast } from '../common/Toast';

type StepResult = {
  tool: string;
  ok: boolean;
  detail: string;
};

/**
 * Runs the flagship attorney motion path in-page so judges and video
 * recording can show tool activity without ChatGPT WebMCP.
 */
function FlagshipDemoRunner() {
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<StepResult[]>([]);
  const [wizardPath, setWizardPath] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setSteps([]);
    setWizardPath(null);
    const record = (tool: string, ok: boolean, detail: string, input: Record<string, unknown>) => {
      logAgentActivity(tool, input, ok, 0);
      setSteps((prev) => [...prev, { tool, ok, detail }]);
    };

    try {
      applyDemoRole('attorney');
      record('sign_in_demo_role', true, 'Signed in as attorney', { role: 'attorney', via: 'flagship_demo' });

      const search = await searchCases({ party_name: 'Smith', page: 1 });
      if (!search.cases?.length) {
        record('attorney_motion_workflow', false, 'No public case for Smith', { party_name: 'Smith' });
        pushToast('No Smith case in demo seed', 'error');
        return;
      }
      const hit = search.cases[0];
      const docket = await getCase(hit.id);
      const [requirements, checklists, drafts] = await Promise.all([
        getFilingRequirements(docket.court_id, docket.case_type_id, 'subsequent'),
        getFilingChecklists(docket.court_id, docket.case_type_id),
        listFilings({ status: 'draft', page: 1 }),
      ]);
      const params = new URLSearchParams({
        case_id: String(docket.id),
        court_id: String(docket.court_id),
        case_type_id: String(docket.case_type_id),
        case_title: docket.title,
      });
      const path = `/filing/new?${params}`;
      setWizardPath(path);
      record(
        'attorney_motion_workflow',
        true,
        `${sanitizeAgentText(docket.title)} · ${requirements.filter((r) => r.is_required).length} required docs · ${checklists.length} motion types · ${drafts.total} drafts`,
        { party_name: 'Smith' },
      );
      pushToast('Flagship workflow complete — open the wizard when ready', 'success');
    } catch (err) {
      record('attorney_motion_workflow', false, err instanceof Error ? err.message : 'failed', {
        party_name: 'Smith',
      });
      pushToast('Flagship demo failed', 'error');
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="agent-hub-demo">
      <h2>Flagship demo (video / no ChatGPT)</h2>
      <p className="agent-hub-note">
        Runs the same attorney motion path the agent would call. Activity feed updates live. Use this for screen capture when WebMCP is off.
      </p>
      <div className="agent-demo-actions">
        <button type="button" className="btn btn-primary" disabled={running} onClick={() => void run()}>
          <Play size={16} aria-hidden />
          {running ? 'Running…' : 'Run attorney_motion_workflow for Smith'}
        </button>
        {wizardPath && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              logAgentActivity('navigate_to', { path: wizardPath, via: 'flagship_demo' }, true, 0);
              navigate(wizardPath);
            }}
          >
            Open filing wizard
          </button>
        )}
      </div>
      {steps.length > 0 && (
        <ol className="agent-demo-steps">
          {steps.map((s, i) => (
            <li key={`${s.tool}-${i}`} className={s.ok ? 'ok' : 'fail'}>
              <code>{s.tool}</code> {s.detail}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export default FlagshipDemoRunner;
