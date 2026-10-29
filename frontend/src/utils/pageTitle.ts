import { useEffect } from 'react';

export function usePageTitle(...parts: (string | null | undefined)[]): void {
  const title = [...parts.filter(Boolean), 'MUEFS'].join(' · ');
  useEffect(() => {
    document.title = title;
  }, [title]);
}
