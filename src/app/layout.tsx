import type { Metadata } from "next";
import "./globals.css";

const SITE_URL = "https://trees.canada.nshipyard.com";
const TITLE = "Toronto Tree Canopy: will trees block your build?";
const DESCRIPTION =
  "Type a Toronto address and get a per-lot tree screening from 2023 airborne LiDAR: tall-canopy area, tallest surface, canopy percent, and the calibrated chance a mature tree stands on the lot, for the lot and the 6 m neighbour buffer. Covers all 498,463 Toronto parcels. Built from City of Toronto open data. Screening signal only; not a permit determination.";

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
