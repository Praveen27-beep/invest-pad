import { Icon, type IconName } from "./Icon";

/**
 * The stand-in for a research destination that is reachable but not built.
 *
 * IT LOOKS LIKE A REAL PAGE ON PURPOSE -- crumb, serif title, subtitle, and one bordered
 * block -- because the alternative reads as a broken route. What it does NOT do is fill
 * that block with a sample: demo.html's Monitors and Skills screens are populated from a
 * fixture in the same file, and transcribing those rows here would put invented research
 * in front of someone who would have no way to tell it apart from their own.
 *
 * So the layout is the demo's and the content is the truth: this is not built, here is
 * which session builds it.
 */
export function ResearchPending({
  title,
  icon,
  purpose,
  delivers,
}: {
  title: string;
  icon: IconName;
  purpose: string;
  delivers: string;
}) {
  return (
    <div>
      <div className="ws-crumb">Research &middot; {title}</div>
      <h1 className="ws-h1">{title}</h1>
      <p className="ws-sub">{purpose}</p>

      <div className="ws-sechead">
        <h2>Not built yet</h2>
        <div className="ws-hint">nothing is shown rather than sampled</div>
      </div>

      <div className="ws-panel" style={{ maxWidth: 640 }}>
        <div className="ws-row">
          <span
            className="ws-exrow-icon"
            aria-hidden="true"
            style={{ paddingTop: 2, color: "var(--ws-brass)" }}
          >
            <Icon name={icon} size={14} />
          </span>
          <span className="ws-row-grow">
            <span className="ws-row-t">
              This account has Workspace access, so this destination is open.
            </span>
            <span className="ws-row-m">
              The screen and the records behind it land in <strong>{delivers}</strong>.
              Nothing is shown in the meantime, because the alternative would be invented
              research.
            </span>
          </span>
          <span className="ws-chip ws-chip--open">Pending</span>
        </div>
      </div>
    </div>
  );
}
