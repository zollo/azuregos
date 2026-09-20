import type { FieldDefinition } from "../types";

interface Props {
  field: FieldDefinition;
  value: unknown;
  onChange: (value: unknown) => void;
}

// Renders a single portal form field based on its definition.
export default function FieldRenderer({ field, value, onChange }: Props) {
  const common = { id: field.name, placeholder: field.placeholder || "" };

  const control = () => {
    switch (field.type) {
      case "textarea":
        return (
          <textarea
            {...common}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        );
      case "number":
        return (
          <input
            {...common}
            type="number"
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
          />
        );
      case "date":
        return (
          <input
            {...common}
            type="date"
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        );
      case "email":
        return (
          <input
            {...common}
            type="email"
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        );
      case "checkbox":
        return (
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
            style={{ width: "auto" }}
          />
        );
      case "select":
        return (
          <select value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)}>
            <option value="">— Select —</option>
            {field.options.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        );
      case "multiselect": {
        const selected = Array.isArray(value) ? (value as string[]) : [];
        const toggle = (opt: string) =>
          onChange(
            selected.includes(opt)
              ? selected.filter((s) => s !== opt)
              : [...selected, opt],
          );
        return (
          <div>
            {field.options.map((o) => (
              <label key={o} style={{ fontWeight: 400, display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={selected.includes(o)}
                  onChange={() => toggle(o)}
                  style={{ width: "auto" }}
                />
                {o}
              </label>
            ))}
          </div>
        );
      }
      default:
        return (
          <input
            {...common}
            type="text"
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        );
    }
  };

  return (
    <div className="field">
      <label htmlFor={field.name}>
        {field.label} {field.required && <span className="req">*</span>}
      </label>
      {control()}
      {field.help_text && <div className="help">{field.help_text}</div>}
    </div>
  );
}
