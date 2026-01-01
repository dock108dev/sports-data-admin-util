"use client";

import { useEffect, useRef } from "react";

declare global {
  interface Window {
    twttr?: {
      widgets: {
        load: (element?: HTMLElement) => void;
        createTweet: (
          tweetId: string,
          container: HTMLElement,
          options?: object
        ) => Promise<HTMLElement | undefined>;
      };
    };
  }
}

type TwitterEmbedProps = {
  tweetUrl: string;
};

/**
 * Renders a Twitter/X embed widget for video posts.
 * Uses Twitter's official widget.js for native video playback.
 */
export function TwitterEmbed({ tweetUrl }: TwitterEmbedProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const embedCreatedRef = useRef(false);

  // Extract tweet ID from URL (handles both twitter.com and x.com)
  const tweetId = tweetUrl.match(/status\/(\d+)/)?.[1];

  useEffect(() => {
    if (!tweetId || !containerRef.current || embedCreatedRef.current) return;

    const container = containerRef.current;

    const embedTweet = () => {
      if (!window.twttr || !container || embedCreatedRef.current) return;
      if (container.querySelector("twitter-widget")) return; // Already has embed
      
      embedCreatedRef.current = true;
      
      window.twttr.widgets.createTweet(tweetId, container, {
        theme: "dark",
        conversation: "none",
        cards: "visible",
      });
    };

    // Load Twitter widget script if not already loaded
    if (!window.twttr) {
      const existingScript = document.querySelector(
        'script[src="https://platform.twitter.com/widgets.js"]'
      );
      if (!existingScript) {
        const script = document.createElement("script");
        script.src = "https://platform.twitter.com/widgets.js";
        script.async = true;
        script.onload = embedTweet;
        document.body.appendChild(script);
      } else {
        // Script exists but twttr not ready yet, wait for it
        const checkTwttr = setInterval(() => {
          if (window.twttr) {
            clearInterval(checkTwttr);
            embedTweet();
          }
        }, 100);
        // Clear interval after 5 seconds to prevent memory leak
        setTimeout(() => clearInterval(checkTwttr), 5000);
      }
    } else {
      embedTweet();
    }
  }, [tweetId]);

  if (!tweetId) {
    return (
      <a href={tweetUrl} target="_blank" rel="noopener noreferrer">
        View on X →
      </a>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{ 
        minHeight: 200, 
        display: "flex", 
        justifyContent: "center",
        overflow: "hidden",
        maxWidth: "100%",
      }}
    />
  );
}

