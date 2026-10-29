import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { getDemoRole, registerRoleTools } = vi.hoisted(() => ({
  getDemoRole: vi.fn((): string | null => 'attorney'),
  registerRoleTools: vi.fn(async () => {}),
}));
vi.mock('../components/auth/LoginScreen', () => ({ getDemoRole }));
vi.mock('./registerTools', () => ({ registerRoleTools }));

describe('WebMCP host registration updates', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.useFakeTimers();
    getDemoRole.mockReturnValue('attorney');
    registerRoleTools.mockReset().mockResolvedValue(undefined);
    vi.stubGlobal('window', new EventTarget());
    vi.stubGlobal('document', {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('notifies the hub when a late host registers without emitting toolchange', async () => {
    const { initMuefsWebMcp, webMcpStatus } = await import('./registry');
    const changed = vi.fn();
    window.addEventListener('muefs-webmcp-tools-changed', changed);
    initMuefsWebMcp();
    expect(webMcpStatus().available).toBe(false);

    document.modelContext = { registerTool: vi.fn() };
    await vi.advanceTimersByTimeAsync(250);

    expect(registerRoleTools).toHaveBeenCalledOnce();
    expect(changed).toHaveBeenCalledOnce();
    expect(webMcpStatus().available).toBe(true);
  });

  it('keeps registered tools until the role actually changes', async () => {
    const { initMuefsWebMcp } = await import('./registry');
    document.modelContext = { registerTool: vi.fn() };
    initMuefsWebMcp();
    await vi.waitFor(() => expect(registerRoleTools).toHaveBeenCalledOnce());

    // Profile refreshes and court switches reuse this signal without a new role.
    window.dispatchEvent(new Event('muefs-demo-role-changed'));
    await vi.advanceTimersByTimeAsync(0);
    expect(registerRoleTools).toHaveBeenCalledOnce();

    getDemoRole.mockReturnValue('clerk');
    window.dispatchEvent(new Event('muefs-demo-role-changed'));
    await vi.waitFor(() => expect(registerRoleTools).toHaveBeenCalledTimes(2));
    expect(registerRoleTools).toHaveBeenLastCalledWith(document.modelContext, 'clerk', expect.any(AbortSignal));
  });

  it('does not publish a registration that finished after a role change', async () => {
    const { refreshMuefsWebMcpTools } = await import('./registry');
    document.modelContext = { registerTool: vi.fn() };
    const changed = vi.fn();
    window.addEventListener('muefs-webmcp-tools-changed', changed);
    let finishOldRegistration!: () => void;
    registerRoleTools.mockImplementationOnce(() => new Promise<void>(resolve => { finishOldRegistration = resolve; }));
    const oldRegistration = refreshMuefsWebMcpTools();
    await vi.waitFor(() => expect(registerRoleTools).toHaveBeenCalledOnce());

    getDemoRole.mockReturnValue('clerk');
    await refreshMuefsWebMcpTools();
    expect(changed).toHaveBeenCalledOnce();
    finishOldRegistration();
    await oldRegistration;
    expect(changed).toHaveBeenCalledOnce();
  });
});
