import Link from "next/link";
import { AdminNav } from "@/components/admin/AdminNav";
import { RunsDrawer } from "@/components/admin/RunsDrawer";
import styles from "./layout.module.css";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.adminShell}>
      <header className={styles.header}>
        <div className={styles.headerLogo}>DOCK108</div>
        <Link href="https://dock108.ai" className={styles.headerLink}>
          Back to hub
        </Link>
      </header>
      <aside className={styles.sidebar}>
        <AdminNav />
      </aside>
      <main className={styles.main}>{children}</main>
      <RunsDrawer />
    </div>
  );
}
