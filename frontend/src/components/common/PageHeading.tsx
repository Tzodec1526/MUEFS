import { useEffect, useRef, type ReactNode, type RefObject } from 'react';
import { useLocation } from 'react-router-dom';

let focusedNavigation: string | null = null;

export default function PageHeading({ children, headingRef }: {
  children: ReactNode; headingRef?: RefObject<HTMLHeadingElement>;
}) {
  const ownRef = useRef<HTMLHeadingElement>(null);
  const ref = headingRef ?? ownRef;
  const navigation = useRef(useLocation().key);
  useEffect(() => {
    const key = navigation.current;
    if (key === 'default' || focusedNavigation === key) return;
    focusedNavigation = key;
    ref.current?.focus();
  }, [ref]);
  return <h1 ref={ref} tabIndex={-1}>{children}</h1>;
}
