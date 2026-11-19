import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MPVpaper Hub · Fonds animés pour Linux",
  description: "Découvre des fonds d’écran issus de plusieurs sources, conserve leurs crédits et retrouve tes favoris avec les notes communes MPVpaper.",
  openGraph: {
    images: [{ url: "/mpvpaper-engine-banner.png", width: 1672, height: 941, alt: "MPVpaper Engine — Animated Wallpapers for Linux" }],
  },
  icons: {
    icon: "/mpvpaper-engine.png",
    shortcut: "/mpvpaper-engine.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr" className="dark">
      <body className="antialiased">{children}</body>
    </html>
  );
}
