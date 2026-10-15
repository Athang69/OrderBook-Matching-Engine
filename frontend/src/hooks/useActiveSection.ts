import { useEffect, useState } from "react";

/** Which of the page sections is currently in view, for highlighting the section menu. */
export function useActiveSection(ids: string[]): string {
  const [active, setActive] = useState(ids[0] ?? "");
  const key = ids.join(",");
  useEffect(() => {
    const visible = new Map<string, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) visible.set(entry.target.id, entry.isIntersecting ? entry.intersectionRatio : 0);
        const best = ids.find((id) => (visible.get(id) ?? 0) > 0);
        if (best) setActive(best);
      },
      { rootMargin: "-120px 0px -55% 0px", threshold: [0, 0.01, 0.5] },
    );
    for (const id of ids) {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    }
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return active;
}
