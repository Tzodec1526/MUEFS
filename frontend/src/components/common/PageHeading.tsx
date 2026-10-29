import { useEffect, useRef, type ReactNode, type RefObject } from 'react';
import { useLocation } from 'react-router-dom';

let focusedNavigation: string | null = null;

export default function PageHeading({ children, headingRef }: {
  children: ReactNode; headingRef?: RefObject<HTMLHeadingElement>;
}) {
  const ownRef = useRef<HTMLHeadingElement>(null);
  const ref = headingRef ?? ownRef;
  const { key, pathname } = useLocation();
  const navigation = useRef(key);
  useEffect(() => {
    navigation.current = key;
  }, [key]);
  useEffect(() => {
    const target = navigation.current;
    if (target === 'default' || focusedNavigation === target) return;
    focusedNavigation = target;
    ref.current?.focus();
  }, [ref, pathname]);
  return <h1 ref={ref} tabIndex={-1}>{children}</h1>;
}
