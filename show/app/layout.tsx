import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "UE ITPS 关系浏览器",
  description: "在本地只读浏览 UE ITPS 工程信息池 SQLite 快照。",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
