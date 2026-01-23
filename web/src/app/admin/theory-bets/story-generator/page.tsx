"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { GameSummary } from "@/lib/api/sportsAdmin/types";
import { listGames } from "@/lib/api/sportsAdmin";
import { bulkGenerateStoriesAsync, getBulkGenerateStatus } from "@/lib/api/sportsAdmin/chapters";
import styles from "./story-generator.module.css";

/**
 * Story Generator Landing Page
 * 
 * ISSUE 13: Admin UI for Chapters-First System
 * 
 * Lists games with story generation status and provides bulk generation tools.
 */
export default function StoryGeneratorLandingPage() {
  const [games, setGames] = useState<GameSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Bulk generation state
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedLeagues, setSelectedLeagues] = useState<string[]>(["NBA"]);
  const [generating, setGenerating] = useState(false);
  const [generationResult, setGenerationResult] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ current: number; total: number; status: string } | null>(null);

  useEffect(() => {
    loadGames();
  }, []);

  const loadGames = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await listGames({
        leagues: ["NBA", "NHL", "NCAAB"],
        limit: 50,
        offset: 0,
      });
      
      // Filter to games with PBP (only those can have stories)
      const gamesWithPbp = response.games.filter(g => g.has_pbp);
      setGames(gamesWithPbp);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load games");
    } finally {
      setLoading(false);
    }
  };

  const handleBulkGenerate = async () => {
    if (!startDate || !endDate) {
      setGenerationResult("Please select both start and end dates");
      return;
    }
    
    setGenerating(true);
    setGenerationResult(null);
    setProgress(null);
    
    try {
      // Start the background job
      const job = await bulkGenerateStoriesAsync({
        start_date: startDate,
        end_date: endDate,
        leagues: selectedLeagues,
        force: false,
      });
      
      setJobId(job.job_id);
      setGenerationResult("Story generation started...");
      
      // Poll for status
      const pollInterval = setInterval(async () => {
        try {
          const status = await getBulkGenerateStatus(job.job_id);
          
          if (status.state === "PROGRESS") {
            setProgress({
              current: status.current || 0,
              total: status.total || 0,
              status: status.status || "Processing...",
            });
            setGenerationResult(
              `Processing: ${status.current || 0}/${status.total || 0} games (${status.successful || 0} successful, ${status.failed || 0} failed, ${status.skipped || 0} skipped)`
            );
          } else if (status.state === "SUCCESS") {
            clearInterval(pollInterval);
            setGenerating(false);
            setProgress(null);
            const result = status.result;
            if (result) {
              setGenerationResult(
                `✓ Generated stories for ${result.successful} of ${result.total_games} games. ${result.failed > 0 ? `${result.failed} failed.` : ""} (${result.skipped} skipped, ${result.generated} newly generated)`
              );
            }
            // Reload games to show updated status
            await loadGames();
          } else if (status.state === "FAILURE") {
            clearInterval(pollInterval);
            setGenerating(false);
            setProgress(null);
            setGenerationResult(`✗ Generation failed: ${status.status}`);
          }
        } catch (err) {
          console.error("Failed to poll status:", err);
        }
      }, 2000); // Poll every 2 seconds
      
      // Clean up interval after 10 minutes max
      setTimeout(() => {
        clearInterval(pollInterval);
        if (generating) {
          setGenerating(false);
          setGenerationResult("✗ Generation timed out. Check server logs.");
        }
      }, 600000);
      
    } catch (err) {
      setGenerationResult(`✗ ${err instanceof Error ? err.message : "Generation failed"}`);
      setGenerating(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>Loading games...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>Error: {error}</div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Story Generator</h1>
        <p className={styles.subtitle}>
          Chapters-First narrative generation for NBA games
        </p>
      </div>

      {/* Bulk Generation Tool */}
      <div className={styles.bulkGenerationPanel}>
        <h2>Bulk Generate Stories</h2>
        <p className={styles.helpText}>
          Generate chapter-based stories for all games with PBP data in a date range.
        </p>
        
        <div className={styles.bulkGenerationForm}>
          <div className={styles.formRow}>
            <label>
              Start Date:
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className={styles.dateInput}
              />
            </label>
            
            <label>
              End Date:
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className={styles.dateInput}
              />
            </label>
          </div>
          
          <div className={styles.formRow}>
            <label>
              Leagues:
              <div className={styles.checkboxGroup}>
                {["NBA", "NHL", "NCAAB"].map((league) => (
                  <label key={league} className={styles.checkbox}>
                    <input
                      type="checkbox"
                      checked={selectedLeagues.includes(league)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedLeagues([...selectedLeagues, league]);
                        } else {
                          setSelectedLeagues(selectedLeagues.filter(l => l !== league));
                        }
                      }}
                    />
                    {league}
                  </label>
                ))}
              </div>
            </label>
          </div>
          
          <button
            onClick={handleBulkGenerate}
            disabled={generating || !startDate || !endDate || selectedLeagues.length === 0}
            className={styles.generateButton}
          >
            {generating ? "Generating..." : "Generate Stories"}
          </button>
          
          {progress && (
            <div className={styles.progressBar}>
              <div className={styles.progressFill} style={{ width: `${(progress.current / progress.total) * 100}%` }} />
              <div className={styles.progressText}>
                {progress.current} / {progress.total} games
              </div>
            </div>
          )}
          
          {generationResult && (
            <div className={generationResult.startsWith("✓") ? styles.successMessage : styles.errorMessage}>
              {generationResult}
            </div>
          )}
        </div>
      </div>

      <div className={styles.gamesGrid}>
        {games.map((game) => (
          <Link
            key={game.id}
            href={`/admin/theory-bets/story-generator/${game.id}`}
            className={styles.gameCard}
          >
            <div className={styles.gameHeader}>
              <span className={styles.gameDate}>
                {new Date(game.game_date).toLocaleDateString()}
              </span>
              <span className={styles.league}>{game.league_code}</span>
            </div>
            
            <div className={styles.gameMatchup}>
              <div className={styles.team}>
                {game.away_team}
                {game.away_score !== null && (
                  <span className={styles.score}>{game.away_score}</span>
                )}
              </div>
              <div className={styles.at}>@</div>
              <div className={styles.team}>
                {game.home_team}
                {game.home_score !== null && (
                  <span className={styles.score}>{game.home_score}</span>
                )}
              </div>
            </div>

            <div className={styles.gameStats}>
              <span className={styles.stat}>
                {game.play_count} plays
              </span>
              {game.has_pbp && (
                <span className={styles.statusBadge}>✓ PBP</span>
              )}
            </div>
          </Link>
        ))}
      </div>

      {games.length === 0 && (
        <div className={styles.emptyState}>
          <p>No games with play-by-play data found.</p>
        </div>
      )}
    </div>
  );
}
