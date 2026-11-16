import type { ReactNode } from "react";
import "./globals.css";
import Top from "@/components/Top";

export const metadata = { title: "Invest-pad", description: "Your research. Your thinking. Your AI." };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Top />
        <main>{children}</main>
        <p className="note">Research and information, not investment advice.</p>
      </body>
    </html>
  );
}
