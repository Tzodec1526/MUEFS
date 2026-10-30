import { createContext, useCallback, useContext, useEffect, useRef, type ReactNode, type RefObject } from 'react';
import { useLocation, useNavigationType, type NavigationType } from 'react-router-dom';

interface HeadingMemory {
  last?: { key: string; pathname: string };
  focusKey?: string;
  focusedKey?: string;
}

type ClaimFocus = (key: string, pathname: string, navigationType: NavigationType) => boolean;

const HeadingFocusContext = createContext<ClaimFocus | null>(null);

function recordNavigation(memory: HeadingMemory, key: string, pathname: string, navigationType: NavigationType, heading: boolean) {
  if (memory.last?.key === key || (!memory.last && !heading)) return;
  const focus = memory.last ? memory.last.pathname !== pathname : navigationType === 'PUSH';
  memory.last = { key, pathname };
  memory.focusKey = focus ? key : undefined;
}

export function HeadingFocusScope({ children }: { children: ReactNode }) {
  const memory = useRef<HeadingMemory>({});
  const { key, pathname } = useLocation();
  const navigationType = useNavigationType();
  useEffect(() => {
    recordNavigation(memory.current, key, pathname, navigationType, false);
  }, [key, pathname, navigationType]);
  const claimFocus = useCallback<ClaimFocus>((headingKey, headingPathname, headingNavigationType) => {
    const state = memory.current;
    recordNavigation(state, headingKey, headingPathname, headingNavigationType, true);
    if (state.focusKey !== headingKey || state.focusedKey === headingKey) return false;
    state.focusedKey = headingKey;
    return true;
  }, []);
  return <HeadingFocusContext.Provider value={claimFocus}>{children}</HeadingFocusContext.Provider>;
}

export default function PageHeading({ children, headingRef }: {
  children: ReactNode; headingRef?: RefObject<HTMLHeadingElement>;
}) {
  const ownRef = useRef<HTMLHeadingElement>(null);
  const ref = headingRef ?? ownRef;
  const claimFocus = useContext(HeadingFocusContext);
  const { key, pathname } = useLocation();
  const navigationType = useNavigationType();
  useEffect(() => {
    if (claimFocus?.(key, pathname, navigationType)) ref.current?.focus();
  }, [claimFocus, ref, key, pathname, navigationType]);
  return <h1 ref={ref} tabIndex={-1}>{children}</h1>;
}
