import ReactMarkdown from "react-markdown";

// Renders markdown safely: react-markdown does not render raw HTML by default,
// so user-authored descriptions can't inject markup.
export default function Markdown({ children }: { children: string }) {
  if (!children?.trim()) return null;
  return (
    <div className="markdown">
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  );
}
