import type { Metadata } from "next";
import "./globals.css";

const SITE_URL = "https://trees.canada.nshipyard.com";
const TITLE = "Toronto Tree Canopy: will trees block your build?";
const DESCRIPTION =
  "Type a Toronto address and get a per-lot tree screening from the Ward 12 (Davenport) pilot: detected crowns, estimated trunk diameters with prediction intervals, the probability any tree clears the Private Tree By-law thresholds, and a plain-English verdict. Built from City of Toronto open data. Screening signal only; not a permit determination.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: SITE_URL },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: "Toronto Tree Canopy",
    title: TITLE,
    description: DESCRIPTION,
  },
  twitter: {
    card: "summary",
    title: TITLE,
    description: DESCRIPTION,
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
