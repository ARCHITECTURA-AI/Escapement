import type { Metadata, Viewport } from "next";
import { Footer, Nav } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Escapement: prove what your AI agent can do", template: "%s · Escapement" },
  description:
    "An open-source arena where engineers prove what their AI agents can do. Server-enforced puzzle rooms, hash-chained replays and signed Run Certificates.",
  openGraph: { siteName: "Escapement", type: "website" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8f7f3" },
    { media: "(prefers-color-scheme: dark)", color: "#0e0e0c" },
  ],
};

// Set the theme before first paint so there is no flash.
const themeScript = `(function(){try{var t=localStorage.getItem('esc-theme');if(!t){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme='light'}})()`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="flex min-h-dvh flex-col">
        <Nav />
        <div id="main" className="flex-1">
          {children}
        </div>
        <Footer />
      </body>
    </html>
  );
}
