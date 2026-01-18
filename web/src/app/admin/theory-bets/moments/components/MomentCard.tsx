"use client";

import { useState, useEffect } from "react";
import styles from "../styles.module.css";
import { PlayTrace } from "./PlayTrace";
import type { MomentTraceDetail } from "@/lib/api/sportsAdmin";

interface MomentCardProps {
  trace: MomentTraceDetail;
  isExpanded: boolean;
  onToggle: () => void;
  gameId: number;
}

const MOMENT_TYPE_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  LEAD_BUILD: { icon: "📈", color: "#22c55e", label: "Lead Extended" },
  CUT: { icon: "✂️", color: "#3b82f6", label: "Comeback" },
  TIE: { icon: "⚖️", color: "#f59e0b", label: "Game Tied" },
  FLIP: { icon: "🔄", color: "#8b5cf6", label: "Lead Change" },
  CLOSING_CONTROL: { icon: "🔒", color: "#dc2626", label: "Game Control" },
  HIGH_IMPACT: { icon: "⚡", color: "#ef4444", label: "Key Moment" },
  NEUTRAL: { icon: "📊", color: "#64748b", label: "Game Flow" },
  OPENER: { icon: "🏀", color: "#6366f1", label: "Period Start" },
};

/**
 * Single moment card with expandable trace details.
 * Shows why the moment was created and which plays contributed.
 */
export function MomentCard({ trace, isExpanded, onToggle, gameId }: MomentCardProps) {
  const config = MOMENT_TYPE_CONFIG[trace.moment_type.toUpperCase()] ?? {
    icon: "📌",
    color: "#64748b",
    label: trace.moment_type,
  };

  const signals = trace.signals || {};
  const validation = trace.validation || {};

  return (
    <div className={styles.momentCard}>
      {/* Header - always visible */}
      <div className={styles.momentCardHeader} onClick={onToggle}>
        <div className={styles.momentCardLeft}>
          <span className={styles.momentIcon}>{config.icon}</span>
          <div className={styles.momentInfo}>
            <h3>{config.label}</h3>
            <div className={styles.momentMeta}>
              <span>#{trace.moment_id}</span>
              <span>•</span>
              <span>Plays {trace.input_start_idx}–{trace.input_end_idx}</span>
              <span>•</span>
              <span>{trace.play_count} plays</span>
            </div>
          </div>
        </div>
        <div className={styles.momentCardRight}>
          <span
            className={styles.typeBadge}
            style={{ background: `${config.color}20`, color: config.color }}
          >
            {trace.trigger_type}
          </span>
          <span className={`${styles.expandIcon} ${isExpanded ? styles.expandIconOpen : ""}`}>
            ▼
          </span>
        </div>
      </div>

      {/* Expanded body */}
      {isExpanded && (
        <div className={styles.momentCardBody}>
          {/* Trigger explanation */}
          <div className={styles.traceSection}>
            <div className={styles.traceSectionTitle}>Why This Moment Exists</div>
            <div className={styles.traceGrid}>
              <div className={styles.traceItem}>
                <span className={styles.traceLabel}>Trigger</span>
                <span className={styles.traceValue}>{trace.trigger_type}</span>
              </div>
              <div className={styles.traceItem}>
                <span className={styles.traceLabel}>Description</span>
                <span className={styles.traceValue}>
                  {trace.trigger_description || "No description"}
                </span>
              </div>
            </div>
          </div>

          {/* Signals */}
          <div className={styles.traceSection}>
            <div className={styles.traceSectionTitle}>Signals</div>
            <div className={styles.traceGrid}>
              {signals.lead_before !== undefined && (
                <div className={styles.traceItem}>
                  <span className={styles.traceLabel}>Lead Before</span>
                  <span className={styles.traceValue}>{String(signals.lead_before)}</span>
                </div>
              )}
              {signals.lead_after !== undefined && (
                <div className={styles.traceItem}>
                  <span className={styles.traceLabel}>Lead After</span>
                  <span className={styles.traceValue}>{String(signals.lead_after)}</span>
                </div>
              )}
              {signals.tier_before !== undefined && (
                <div className={styles.traceItem}>
                  <span className={styles.traceLabel}>Tier Before</span>
                  <span className={styles.traceValue}>{String(signals.tier_before)}</span>
                </div>
              )}
              {signals.tier_after !== undefined && (
                <div className={styles.traceItem}>
                  <span className={styles.traceLabel}>Tier After</span>
                  <span className={styles.traceValue}>{String(signals.tier_after)}</span>
                </div>
              )}
              {signals.leader_before !== undefined && (
                <div className={styles.traceItem}>
                  <span className={styles.traceLabel}>Leader Before</span>
                  <span className={styles.traceValue}>
                    {String(signals.leader_before) || "tied"}
                  </span>
                </div>
              )}
              {signals.leader_after !== undefined && (
                <div className={styles.traceItem}>
                  <span className={styles.traceLabel}>Leader After</span>
                  <span className={styles.traceValue}>
                    {String(signals.leader_after) || "tied"}
                  </span>
                </div>
              )}
              {signals.run_team !== undefined && (
                <div className={styles.traceItem}>
                  <span className={styles.traceLabel}>Run</span>
                  <span className={styles.traceValue}>
                    {String(signals.run_points)}-0 {String(signals.run_team)}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Validation */}
          <div className={styles.traceSection}>
            <div className={styles.traceSectionTitle}>Validation</div>
            <div className={styles.traceGrid}>
              <div className={styles.traceItem}>
                <span className={styles.traceLabel}>Passed</span>
                <span className={styles.traceValue}>
                  {validation.passed ? "✅ Yes" : "❌ No"}
                </span>
              </div>
              {Array.isArray(validation.issues) && validation.issues.length > 0 && (
                <div className={styles.traceItem}>
                  <span className={styles.traceLabel}>Issues</span>
                  <span className={styles.traceValue} style={{ color: "#dc2626" }}>
                    {(validation.issues as string[]).join(", ")}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Action history */}
          {trace.actions && trace.actions.length > 0 && (
            <div className={styles.traceSection}>
              <div className={styles.traceSectionTitle}>Action History</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {trace.actions.map((action, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "0.5rem 0.75rem",
                      background: "#ffffff",
                      border: "1px solid #e2e8f0",
                      borderRadius: "6px",
                      fontSize: "0.85rem",
                    }}
                  >
                    <strong style={{ color: "#3b82f6" }}>{String(action.action ?? "")}</strong>
                    {action.reason !== undefined && (
                      <span style={{ color: "#64748b" }}> — {String(action.reason)}</span>
                    )}
                    {action.timestamp !== undefined && (
                      <span style={{ color: "#94a3b8", marginLeft: "0.5rem" }}>
                        @ {new Date(String(action.timestamp)).toLocaleTimeString()}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Absorbed moments (if any) */}
          {trace.absorbed_moment_ids && trace.absorbed_moment_ids.length > 0 && (
            <div className={styles.traceSection}>
              <div className={styles.traceSectionTitle}>Absorbed Moments</div>
              <div style={{ fontSize: "0.85rem", color: "#64748b" }}>
                This moment absorbed: {trace.absorbed_moment_ids.join(", ")}
              </div>
            </div>
          )}

          {/* Contributing plays */}
          <div className={styles.traceSection}>
            <div className={styles.traceSectionTitle}>
              Contributing Plays ({trace.input_start_idx} – {trace.input_end_idx})
            </div>
            <PlayTrace
              gameId={gameId}
              startPlay={trace.input_start_idx}
              endPlay={trace.input_end_idx}
            />
          </div>
        </div>
      )}
    </div>
  );
}
