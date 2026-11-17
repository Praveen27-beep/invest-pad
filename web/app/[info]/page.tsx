import { notFound } from "next/navigation";
import { Landing, type PublicPage } from "@/components/public/Landing";

const PUBLIC_PAGES = ["features", "pricing", "blog", "manifesto", "docs"] as const;

export const dynamicParams = false;

export function generateStaticParams() {
  return PUBLIC_PAGES.map((info) => ({ info }));
}

export async function generateMetadata({ params }: { params: Promise<{ info: string }> }) {
  const { info } = await params;
  return { title: `${info.charAt(0).toUpperCase() + info.slice(1)} | Invest-pad` };
}

export default async function PublicPageRoute({ params }: { params: Promise<{ info: string }> }) {
  const { info } = await params;
  if (!PUBLIC_PAGES.includes(info as PublicPage)) notFound();
  return <Landing page={info as PublicPage} />;
}
