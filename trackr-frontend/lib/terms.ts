/**
 * The Terms + Privacy version this build shows, and sends back on registration.
 *
 * MUST MATCH trackr-backend/app/terms.py's CURRENT_TOS_VERSION. The server rejects a
 * registration carrying any other value, deliberately: a mismatch means the person was
 * shown one version and we would have recorded another, and a false acceptance record is
 * worse than no record at all.
 *
 * Bump BOTH, together with the text on app/terms/page.tsx, whenever the terms change in
 * a way someone would want to be asked about again. Existing accounts keep the version
 * they accepted — which is the whole reason a version is stored rather than a boolean.
 */
export const CURRENT_TOS_VERSION = "2026-09-terms-v1";
