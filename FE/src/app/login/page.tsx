import Link from "next/link";
import { AppLayout } from "@/components/layout/app-layout";
export default function Page() { return <AppLayout><p>Đã đăng nhập.</p><Link href="/">Mở Dashboard</Link></AppLayout>; }
