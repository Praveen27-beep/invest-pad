import { Redirect } from "../components/Redirect";

/**
 * Compatibility only. Every figure this URL showed is on the Dashboard, in both apps -- see
 * Plus's own `/performance`. Kept as a working redirect for saved links, and deliberately NOT
 * a destination: it is absent from `PORTFOLIO_GROUPS`, so no launcher or tab strip offers it.
 */
export default function Performance() {
  return <Redirect to="/" />;
}
