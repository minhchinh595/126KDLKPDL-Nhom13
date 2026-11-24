import type { Metadata } from "next";
import "./globals.css";
import { SessionProvider } from "@/components/auth/session-provider";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Electricity Consumption Analytics | Phân tích & Dự đoán Nhu cầu Điện",
  description: "Hệ thống phân tích mức tiêu thụ điện năng nhằm nhận diện quy luật sử dụng và dự đoán nhu cầu điện",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className={cn("h-full", "antialiased")}>
      <body className="min-h-full flex flex-col bg-background text-foreground"><SessionProvider>{children}</SessionProvider></body>
    </html>
  );
}
