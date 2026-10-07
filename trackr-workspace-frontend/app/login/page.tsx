"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@trackr/core";
import { PublicHeader } from "../components/Landing";
import { SignIn } from "../components/SignIn";

/**
 * The explicit sign-in route. The shell already renders `SignIn` for any protected path
 * without a session, so this exists for a direct link and for the redirect target a
 * browser bookmark expects -- not as a second implementation.
 */
export default function Login() {
  const { token, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (ready && token) router.replace("/explorer");
  }, [ready, token, router]);
  if (token) return null;
  return (
    <div className="ip-public">
      <PublicHeader />
      <SignIn />
    </div>
  );
}
