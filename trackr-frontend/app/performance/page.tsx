"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// Commented out 2026-09-08. Every figure this page showed -- both XIRR variants,
// absolute return, benchmark comparison -- already lives on the Dashboard
// (app/page.tsx), and this screen never got the ds/ redesign the rest of the app did,
// so it read as a different product. Nothing here is deleted: uncomment the block
// below (and the nav entry in ../components/nav.ts) to bring it back, whether as-is or
// redesigned.
//
// import { PerformanceTab } from "../components/tabs/PerformanceTab";
// import { PageHeader } from "../components/PageHeader";
// import { PageBody } from "../components/Shell";
//
// export default function PerformancePage() {
//   return (
//     <>
//       <PageHeader
//         title="Performance"
//         subtitle="XIRR, TWRR and realised gains, solved from the ledger's own cash flows."
//       />
//       <PageBody>
//         <PerformanceTab />
//       </PageBody>
//     </>
//   );
// }

/** Sends anyone who still has this URL saved to the Dashboard, where the same numbers
 *  live now. */
export default function PerformancePage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/");
  }, [router]);
  return null;
}
