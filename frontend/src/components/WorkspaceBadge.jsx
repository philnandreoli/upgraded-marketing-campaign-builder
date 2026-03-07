import { Link } from "react-router-dom";

/**
 * WorkspaceBadge — inline pill badge showing a workspace name.
 *
 * Variants:
 *   default   — teal/primary pill, links to /workspaces/:id
 *   personal  — adds 🏠 icon (workspace.is_personal === true)
 *   orphaned  — amber/warning pill with ⚠️ icon and "Orphaned" text
 *
 * Props:
 *   workspace  { id, name, is_personal }  — workspace object
 *   orphaned   boolean                    — force orphaned variant
 *   linkTo     boolean (default true)     — wrap in <Link> for default variant
 */
export default function WorkspaceBadge({ workspace, orphaned = false, linkTo = true }) {
  if (orphaned || !workspace) {
    return (
      <span className="workspace-badge workspace-badge--orphaned" aria-label="Orphaned campaign">
        ⚠️ Orphaned
      </span>
    );
  }

  const isPersonal = workspace.is_personal;
  const className = `workspace-badge${isPersonal ? " workspace-badge--personal" : ""}`;
  const content = (
    <>
      {isPersonal && <span className="workspace-badge-icon" aria-hidden="true">🏠</span>}
      <span className="workspace-badge-name">{workspace.name}</span>
    </>
  );

  if (linkTo && workspace.id) {
    return (
      <Link to={`/workspaces/${workspace.id}`} className={className}>
        {content}
      </Link>
    );
  }

  return <span className={className}>{content}</span>;
}
