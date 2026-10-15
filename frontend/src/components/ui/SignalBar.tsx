/** A value from -1 to +1 drawn from the centre: red to the left for sell, green to the right for buy. */
export function SignalBar({ value, label }: { value: number; label: string }) {
  const width = `${Math.min(1, Math.abs(value)) * 50}%`;
  return (
    <span className="signal-bar" role="img" aria-label={`${label}: ${value > 0 ? "+" : ""}${Math.round(value * 100)}`}
      title={`${label}: ${value > 0 ? "+" : ""}${Math.round(value * 100)}`}>
      <span className={value >= 0 ? "fill up" : "fill down"} style={value >= 0 ? { left: "50%", width } : { right: "50%", width }} />
    </span>
  );
}
