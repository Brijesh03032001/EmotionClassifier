import type { Metadata } from "next";
import { Geist } from "next/font/google";
import { Playfair_Display } from "next/font/google";
import { PlayerProvider } from "@/lib/player-context";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const playfair = Playfair_Display({
  variable: "--font-heading",
  subsets: ["latin"],
  weight: ["400", "700", "900"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Moodify — AI Music for Every Feeling",
  description: "Describe your mood. Get a perfect playlist powered by AI.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${playfair.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col relative">
        {/* Fixed ambient background — always visible regardless of scroll */}
        <div className="ambient-bg" aria-hidden="true">
          <div className="ambient-blob-3" />
        </div>
        <div className="relative z-10 flex flex-col min-h-full">
          <PlayerProvider>{children}</PlayerProvider>
        </div>
      </body>
    </html>
  );
}

