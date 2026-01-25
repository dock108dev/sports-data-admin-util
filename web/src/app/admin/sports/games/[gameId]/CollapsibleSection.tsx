"use client";

import { useState, type ReactNode } from "react";
import styles from "./styles.module.css";

export function CollapsibleSection({
  title,
  defaultOpen = true,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <div className={styles.card}>
      <button
        type="button"
        className={styles.collapsibleHeader}
        onClick={() => setIsOpen(!isOpen)}
      >
        <h2>{title}</h2>
        <span className={styles.chevron}>{isOpen ? "▼" : "▶"}</span>
      </button>
      {isOpen && <div className={styles.collapsibleContent}>{children}</div>}
    </div>
  );
}
