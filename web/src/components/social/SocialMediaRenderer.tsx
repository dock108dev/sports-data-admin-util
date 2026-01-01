"use client";

import { useMemo, useState } from "react";
import styles from "./SocialMediaRenderer.module.css";
import { ENABLE_INLINE_X_VIDEO } from "@/lib/featureFlags";

type SocialMediaRendererProps = {
  mediaType?: string | null;
  imageUrl?: string | null;
  videoUrl?: string | null;
  postUrl: string;
  linkClassName?: string;
};

export function SocialMediaRenderer({
  mediaType,
  imageUrl,
  videoUrl,
  postUrl,
  linkClassName,
}: SocialMediaRendererProps) {
  const [videoFailed, setVideoFailed] = useState(false);
  const hasImage = Boolean(imageUrl);
  const hasVideo = Boolean(videoUrl);
  const isVideoPost = mediaType === "video";

  const shouldRenderVideo = useMemo(() => {
    return ENABLE_INLINE_X_VIDEO && hasVideo && !videoFailed;
  }, [hasVideo, videoFailed]);

  const showImage = !shouldRenderVideo && hasImage;
  // Show video placeholder for video posts without captured media
  const showVideoPlaceholder = !shouldRenderVideo && !hasImage && isVideoPost;
  const showPlaceholder = !shouldRenderVideo && !hasImage && !isVideoPost;
  const title = mediaType ? `X post media (${mediaType})` : "X post media";
  const showVideoOverlay = showImage && isVideoPost;

  // #region agent log
  fetch('http://127.0.0.1:7242/ingest/bbcc1fde-07f2-48ee-a458-9336304655ab',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'SocialMediaRenderer.tsx:render',message:'SocialMediaRenderer props and computed values',data:{mediaType,imageUrl:imageUrl?.substring(0,50),videoUrl:videoUrl?.substring(0,50),hasImage,hasVideo,isVideoPost,shouldRenderVideo,showImage,showVideoPlaceholder,showPlaceholder,showVideoOverlay,ENABLE_INLINE_X_VIDEO},timestamp:Date.now(),sessionId:'debug-session',hypothesisId:'H1-H4'})}).catch(()=>{});
  // #endregion

  // TODO: Handle expiring X CDN URLs with refresh logic.
  // TODO: Support multi-media posts (multiple images/videos) in future.
  // TODO: Revisit autoplay behavior across browsers and user settings.
  return (
    <div className={styles.container}>
      <div className={styles.aspectContainer} aria-label={title}>
        {shouldRenderVideo && videoUrl ? (
          <video
            className={styles.media}
            controls
            muted
            autoPlay
            playsInline
            preload="none"
            poster={imageUrl ?? undefined}
            onError={() => setVideoFailed(true)}
          >
            <source src={videoUrl} />
            Your browser does not support the video tag.
          </video>
        ) : null}
        {showImage && imageUrl ? (
          <>
            <img
              src={imageUrl}
              alt="X post media"
              className={styles.media}
              loading="lazy"
            />
            {showVideoOverlay ? (
              <span className={styles.playOverlay} aria-hidden="true">
                ▶
              </span>
            ) : null}
          </>
        ) : null}
        {showVideoPlaceholder ? (
          <a
            href={postUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.videoPlaceholder}
          >
            <span className={styles.videoIcon}>▶</span>
            <span className={styles.videoLabel}>Watch on X</span>
          </a>
        ) : null}
        {showPlaceholder ? (
          <div className={styles.placeholder}>Media unavailable</div>
        ) : null}
      </div>
      <a
        href={postUrl}
        target="_blank"
        rel="noopener noreferrer"
        className={linkClassName ?? styles.link}
      >
        View on X →
      </a>
    </div>
  );
}
