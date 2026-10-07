import { notFound } from "next/navigation";
import { Landing, type PublicPage } from "../components/Landing";

const PUBLIC_PAGES = [
  "features",
  "pricing",
  "blog",
  "manifesto",
  "docs",
] as const;
export function generateStaticParams() {
  return PUBLIC_PAGES.map((info) => ({ info }));
}
export function generateMetadata({ params }: { params: { info: string } }) {
  return {
    title: `${params.info.charAt(0).toUpperCase() + params.info.slice(1)} | Invest-pad`,
  };
}
export default function PublicPageRoute({
  params,
}: {
  params: { info: string };
}) {
  if (!PUBLIC_PAGES.includes(params.info as PublicPage)) notFound();
  return <Landing page={params.info as PublicPage} />;
}
