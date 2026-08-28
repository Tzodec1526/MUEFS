import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play } from 'lucide-react';
import { getCase, searchCases } from '../../api/cases';
import { getFilingChecklists, getFilingRequirements } from '../../api/courts';
import { getClerkQueue, listFilings } from '../../api/filings';
import { applyDemoRole, getDemoCourtId } from '../auth/LoginScreen';
import { logAgentActivity } from '../../webmcp/activity';
import { sanitizeAgentText } from '../../webmcp/output';
import { useToast } from '../common/Toast';

type StepResult = {
  tool: string;
  ok: boolean;
  detail: string;
};

type DemoKind = 'attorney' | 'clerk' | 'srl';

function FlagshipDemoRunner() {
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<StepResult[]>([]);
  const [nextPath, setNextPath] = useState<string | null>(null);

  const record = (tool: string, ok: boolean, detail: string, input: Record<string, unknown>) => {
    logAgentActivity(tool, input, ok, 0);
    setSteps((prev) => [...prev, { tool, ok, detail }]);
  };

  const runAttorney = async () => {
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
    setNextPath(path);
    record(
      'attorney_motion_workflow',
      true,
      `${sanitizeAgentText(docket.title)} · ${requirements.filter((r) => r.is_required).length} required docs · ${checklists.length} motion types · ${drafts.total} drafts`,
      { party_name: 'Smith' },
    );
    pushToast('Attorney workflow ready — open the wizard when ready', 'success');
  };

  const runClerk = async () => {
    applyDemoRole('clerk');
    record('sign_in_demo_role', true, 'Signed in as clerk', { role: 'clerk', via: 'flagship_demo' });
    const courtId = getDemoCourtId() || 3;
    const [submitted, review] = await Promise.all([
      getClerkQueue(courtId, 1, 'submitted'),
      getClerkQueue(courtId, 1, 'under_review'),
    ]);
    const oldest = submitted.filings[0];
    setNextPath('/clerk/queue');
    record(
      'clerk_triage_workflow',
      true,
      `${submitted.total} submitted · ${review.total} under review` +
        (oldest ? ` · oldest filing ${oldest.id}` : ''),
      { via: 'flagship_demo' },
    );
    if (oldest?.id) {
      record(
        'open_filing_for_review',
        true,
        `review_path=/clerk/queue?filing_id=${oldest.id}`,
        { filing_id: oldest.id },
      );
    }
    pushToast('Clerk triage ready — open the queue when ready', 'success');
  };

  const runSrl = async () => {
    applyDemoRole('srl');
    record('sign_in_demo_role', true, 'Signed in as SRL', { role: 'srl', via: 'flagship_demo' });
    const courtId = 3;
    const caseTypeId = 1;
    const [requirements, checklists] = await Promise.all([
      getFilingRequirements(courtId, caseTypeId, 'motion'),
      getFilingChecklists(courtId, caseTypeId),
    ]);
    const required = requirements.filter((r) => r.is_required);
    setNextPath('/cases/search');
    record(
      'explain_mcr_for_filing',
      true,
      `${required.length} required docs · ${checklists.length} motion guides`,
      { court_id: courtId, case_type_id: caseTypeId, filing_type: 'motion' },
    );
    pushToast('MCR explainer ready', 'success');
  };

  const run = async (kind: DemoKind) => {
    setRunning(true);
    setSteps([]);
    setNextPath(null);
    try {
      if (kind === 'attorney') await runAttorney();
      else if (kind === 'clerk') await runClerk();
      else await runSrl();
    } catch (err) {
      record('flagship_demo', false, err instanceof Error ? err.message : 'failed', { kind });
      pushToast('Demo failed', 'error');
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="agent-hub-demo">
      <h2>Flagship demos (video / no ChatGPT)</h2>
      <p className="agent-hub-note">
        Same paths agents call via WebMCP. Activity feed updates live. Record these when ChatGPT is unavailable.
      </p>
      <div className="agent-demo-actions">
        <button type="button" className="btn btn-primary" disabled={running} onClick={() => void run('attorney')}>
          <Play size={16} aria-hidden />
          Attorney · Smith motion
        </button>
        <button type="button" className="btn btn-secondary" disabled={running} onClick={() => void run('clerk')}>
          <Play size={16} aria-hidden />
          Clerk · triage
        </button>
        <button type="button" className="btn btn-secondary" disabled={running} onClick={() => void run('srl')}>
          <Play size={16} aria-hidden />
          SRL · explain MCR
        </button>
        {nextPath && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              logAgentActivity('navigate_to', { path: nextPath, via: 'flagship_demo' }, true, 0);
              navigate(nextPath);
            }}
          >
            Open result path
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
