"use client";

import type { ScrapeRunConfig } from "@/lib/api/sportsAdmin/types";
import styles from "./RunTaskBadges.module.css";

interface RunTaskBadgesProps {
  config: ScrapeRunConfig | null;
}

const TASK_LABELS: { key: keyof ScrapeRunConfig; label: string }[] = [
  { key: "boxscores", label: "Box" },
  { key: "odds", label: "Odds" },
  { key: "social", label: "Social" },
  { key: "pbp", label: "PBP" },
];

export function RunTaskBadges({ config }: RunTaskBadgesProps) {
  if (!config) return <span>—</span>;

  const activeTasks = TASK_LABELS.filter(({ key }) => config[key]);

  if (activeTasks.length === 0) return <span>—</span>;

  return (
    <span className={styles.container}>
      {activeTasks.map(({ key, label }) => (
        <span key={key} className={styles.pill}>
          {label}
        </span>
      ))}
    </span>
  );
}
