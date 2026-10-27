import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ENEM em Foco",
  description: "Estude com provas oficiais do ENEM, correção, histórico pessoal e VideoAulas.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body className="antialiased">{children}</body>
    </html>
  );
}
