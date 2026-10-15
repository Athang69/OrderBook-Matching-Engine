import { useActiveSection } from "../../hooks/useActiveSection";

export const SECTIONS: [string, string][] = [
  ["summary", "Summary"],
  ["chart", "Chart"],
  ["depth", "Order book"],
  ["news", "News"],
  ["recommendations", "Recommendations"],
  ["account", "Portfolio"],
  ["others", "Other stocks"],
];

/** The left menu: jumps to each section and highlights the one on screen. */
export function SectionNav() {
  const active = useActiveSection(SECTIONS.map(([id]) => id));
  return (
    <nav className="section-nav" aria-label="On this page">
      <ul>
        {SECTIONS.map(([id, text]) => (
          <li key={id}>
            <a href={`#${id}`} aria-current={active === id ? "location" : undefined} className={active === id ? "active" : ""}>{text}</a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
