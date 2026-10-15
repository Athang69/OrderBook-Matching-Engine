interface Props<T extends string> {
  label: string;
  value: T;
  options: [T, string][];
  /** Called on every click, including on the option already selected. */
  onSelect: (value: T) => void;
  /** Colour the selected option as buy (green) or sell (red) by its value. */
  sideColours?: boolean;
}

export function Segmented<T extends string>({ label, value, options, onSelect, sideColours }: Props<T>) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map(([option, text]) => (
        <button key={option} type="button" aria-pressed={value === option}
          className={[value === option ? "on" : "", sideColours ? option.toLowerCase() : ""].join(" ").trim()}
          onClick={() => onSelect(option)}>
          {text}
        </button>
      ))}
    </div>
  );
}
