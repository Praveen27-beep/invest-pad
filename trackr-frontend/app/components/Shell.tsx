"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { OnboardingWizard } from "./onboarding/OnboardingWizard";

const PUBLIC_PATHS = ["/login", "/register"];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const { token, ready } = useAuth();
  const isPublic = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    if (ready && !token && !isPublic) router.replace("/login");
  }, [ready, token, isPublic, router]);

  if (isPublic) return <>{children}</>;

  if (!ready) {
    return <div className="flex min-h-screen items-center justify-center text-navy-400">Loading…</div>;
  }

  if (!token) return null; // redirect effect above is in flight

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header pathname={pathname} />
        <main key={pathname} className="flex-1 overflow-x-auto px-5 py-6 animate-fade-in-up sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
      <OnboardingWizard />
    </div>
  );
}
