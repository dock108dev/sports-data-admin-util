"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./LogsDrawer.module.css";
import { fetchDockerLogs } from "@/lib/api/sportsAdmin";

export type LogsTab = {
  label: string;
  container: string;
};

const DEFAULT_TABS: LogsTab[] = [
  { label: "API", container: "sports-api" },
  { label: "Scraper", container: "sports-scraper" },
  { label: "Social Scraper", container: "sports-social-scraper" },
];

type LogsDrawerProps = {
  open: boolean;
  onClose: () => void;
  tabs?: LogsTab[];
};

export function LogsDrawer({ open, onClose, tabs = DEFAULT_TABS }: LogsDrawerProps) {
  const [activeTab, setActiveTab] = useState(0);
  const [logs, setLogs] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logAreaRef = useRef<HTMLDivElement>(null);

  const loadLogs = useCallback(async (tabIndex: number) => {
    const tab = tabs[tabIndex];
    setLoading(true);
    setError(null);
    try {
      const result = await fetchDockerLogs(tab.container);
      setLogs(result.logs);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setLogs("");
    } finally {
      setLoading(false);
    }
  }, [tabs]);

  useEffect(() => {
    if (open) {
      loadLogs(activeTab);
    }
  }, [open, activeTab, loadLogs]);

  // Auto-scroll to bottom when logs change
  useEffect(() => {
    if (logAreaRef.current) {
      logAreaRef.current.scrollTop = logAreaRef.current.scrollHeight;
    }
  }, [logs]);

  const handleTabClick = (index: number) => {
    setActiveTab(index);
  };

  const handleRefresh = () => {
    loadLogs(activeTab);
  };

  return (
    <>
      <div
        className={`${styles.backdrop} ${open ? styles.backdropOpen : ""}`}
        onClick={onClose}
      />
      <div className={`${styles.panel} ${open ? styles.panelOpen : ""}`}>
        <div className={styles.header}>
          <h2>Container Logs</h2>
          <div className={styles.headerActions}>
            <button
              className={styles.refreshButton}
              onClick={handleRefresh}
              disabled={loading}
            >
              {loading ? "Loading..." : "Refresh"}
            </button>
            <button className={styles.closeButton} onClick={onClose}>
              ✕
            </button>
          </div>
        </div>

        <div className={styles.tabs}>
          {tabs.map((tab, i) => (
            <button
              key={tab.container}
              className={`${styles.tab} ${i === activeTab ? styles.tabActive : ""}`}
              onClick={() => handleTabClick(i)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className={styles.loading}>Loading logs...</div>
        ) : error ? (
          <div className={styles.errorMessage}>{error}</div>
        ) : (
          <div className={styles.logArea} ref={logAreaRef}>
            <pre className={styles.logContent}>{logs || "No logs available."}</pre>
          </div>
        )}

        <div className={styles.footer}>
          Showing last 1000 lines from <strong>{tabs[activeTab].container}</strong>
        </div>
      </div>
    </>
  );
}
