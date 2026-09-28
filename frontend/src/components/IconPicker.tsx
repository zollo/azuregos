import Icon, { ICON_NAMES } from "./Icon";

// A compact grid picker. Empty value ("") means "no icon" — for portals this
// inherits the category icon; for categories it uses the default.
export default function IconPicker({
  value,
  onChange,
  noneLabel = "Default",
}: {
  value: string;
  onChange: (value: string) => void;
  noneLabel?: string;
}) {
  return (
    <div className="icon-grid">
      <button
        type="button"
        className={`icon-cell${!value ? " selected" : ""}`}
        onClick={() => onChange("")}
        title={noneLabel}
      >
        <span className="muted" style={{ fontSize: 10, lineHeight: 1.1 }}>{noneLabel}</span>
      </button>
      {ICON_NAMES.map((n) => (
        <button
          key={n}
          type="button"
          className={`icon-cell${value === n ? " selected" : ""}`}
          onClick={() => onChange(n)}
          title={n}
        >
          <Icon name={n} size={20} />
        </button>
      ))}
    </div>
  );
}
