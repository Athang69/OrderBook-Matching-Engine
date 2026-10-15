/** A bar for a 0 to 1 confidence, with a tick at the confidence the user asked for (a percentage). */
export function ConfidenceMeter({ value, asked, text }: { value: number; asked: number; text: string }) {
  return (
    <span className="confidence-meter">
      <span className="track" aria-hidden="true">
        <span className="fill" style={{ width: `${Math.min(1, value) * 100}%` }} />
        <i style={{ left: `${asked}%` }} />
      </span>
      <span className="num">{text}</span>
    </span>
  );
}
