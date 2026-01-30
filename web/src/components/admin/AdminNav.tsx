"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./AdminNav.module.css";

interface NavItem {
  href: string;
  label: string;
}

const navSections: { title: string; items: NavItem[] }[] = [
  {
    title: "Sports",
    items: [
      { href: "/admin/sports/browser", label: "Data Browser" },
      { href: "/admin/sports/ingestion", label: "Scraper Runs" },
      { href: "/admin/sports/story-generator", label: "Flow Generator" },
    ],
  },
];

export function AdminNav() {
  const pathname = usePathname();

  const isActive = (href: string) => pathname.startsWith(href);

  return (
    <div className={styles.navContainer}>
      <div className={styles.logo}>
        <div className={styles.logoText}>Sports Admin</div>
        <div className={styles.logoSub}>Data Management</div>
      </div>

      <nav className={styles.nav}>
        {navSections.map((section) => (
          <div key={section.title} className={styles.navSection}>
            <div className={styles.navSectionTitle}>{section.title}</div>
            {section.items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`${styles.navLink} ${isActive(item.href) ? styles.navLinkActive : ""}`}
              >
                {item.label}
              </Link>
            ))}
          </div>
        ))}
      </nav>

      <div className={styles.footer}>
        <Link href="/" className={styles.footerLink}>
          Back to Home
        </Link>
      </div>
    </div>
  );
}
