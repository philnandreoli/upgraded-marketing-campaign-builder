import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

function joinClassNames(...classNames) {
  return classNames.filter(Boolean).join(" ");
}

export default function MarkdownRenderer({ content = "", className = "" }) {
  if (!content) {
    return null;
  }

  return (
    <div className={joinClassNames("markdown-content", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a
              {...props}
              target="_blank"
              rel="noreferrer"
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}