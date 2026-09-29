import Link from "next/link";

/**
 * Unknown paths stay 404s in both applications -- `docs/PRODUCT_ARCHITECTURE.md`
 * section 3. A research URL typed on this deployment by a Plus-only account does not
 * land here; it reaches the capability screen, because the route exists and the answer
 * is "not on this account" rather than "no such page". The two are different facts and
 * are reported differently.
 */
export default function NotFound() {
  return (
    <div className="ws-panel" style={{ maxWidth: 480, padding: 24 }}>
      <h1 className="ws-h1">Not found</h1>
      <p className="ws-sub" style={{ marginBottom: 16 }}>
        There is no page at this address.
      </p>
      <Link href="/" className="ws-btn ws-btn--primary">
        Go to Portfolio
      </Link>
    </div>
  );
}
