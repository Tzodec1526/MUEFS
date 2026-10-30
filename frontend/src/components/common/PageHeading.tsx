import { useContext, useEffect, useRef, type ReactNode, type RefObject } from 'react';
import { UNSAFE_NavigationContext, useLocation, useNavigationType, type Navigator } from 'react-router-dom';

const lastNavigation = new WeakMap<Navigator, { key: string; pathname: string }>();

export default function PageHeading({ children, headingRef }: {
  children: ReactNode; headingRef?: RefObject<HTMLHeadingElement>;
}) {
  const ownRef = useRef<HTMLHeadingElement>(null);
  const ref = headingRef ?? ownRef;
  const { navigator } = useContext(UNSAFE_NavigationContext);
  const { key, pathname } = useLocation();
  const navigationType = useNavigationType();
  useEffect(() => {
    const previous = lastNavigation.get(navigator);
    if (previous?.key === key) return;
    lastNavigation.set(navigator, { key, pathname });
    if (previous ? previous.pathname === pathname : navigationType !== 'PUSH') return;
    ref.current?.focus();
  }, [navigator, ref, key, pathname, navigationType]);
  return <h1 ref={ref} tabIndex={-1}>{children}</h1>;
}
