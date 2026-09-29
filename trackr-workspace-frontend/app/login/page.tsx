"use client";

import { SignIn } from "../components/SignIn";

/**
 * The explicit sign-in route. The shell already renders `SignIn` for any protected path
 * without a session, so this exists for a direct link and for the redirect target a
 * browser bookmark expects -- not as a second implementation.
 */
export default function Login() {
  return <SignIn />;
}
