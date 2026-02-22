import { americanToImplied, formatOdds, shinDevig, trueProbToAmerican } from "@/lib/api/fairbet";
import styles from "./styles.module.css";

export function DerivationContent({
  referencePrice,
  oppositeReferencePrice,
  trueProb,
  evMethod,
  estimatedSharpPrice,
  extrapolationRefLine,
  extrapolationDistance,
}: {
  referencePrice: number;
  oppositeReferencePrice: number;
  trueProb: number;
  evMethod?: string | null;
  estimatedSharpPrice?: number | null;
  extrapolationRefLine?: number | null;
  extrapolationDistance?: number | null;
}) {
  if (evMethod === "pinnacle_extrapolated") {
    return (
      <div className={styles.derivationPopover} onClick={(e) => e.stopPropagation()}>
        <div className={styles.derivationTitle}>Pinnacle Extrapolated</div>
        <div className={styles.derivationDivider} />
        {extrapolationRefLine != null && (
          <div className={styles.derivationRow}>
            <span className={styles.derivationLabel}>Ref. line</span>
            <span className={styles.derivationValue}>{extrapolationRefLine}</span>
          </div>
        )}
        {extrapolationDistance != null && (
          <div className={styles.derivationRow}>
            <span className={styles.derivationLabel}>Distance</span>
            <span className={styles.derivationValue}>{extrapolationDistance} half-pts</span>
          </div>
        )}
        <div className={styles.derivationRow}>
          <span className={styles.derivationLabel}>Ref. PIN price</span>
          <span className={styles.derivationValue}>{formatOdds(referencePrice)}</span>
        </div>
        {estimatedSharpPrice != null && (
          <div className={styles.derivationRow}>
            <span className={styles.derivationLabel}>Est. PIN at target</span>
            <span className={styles.derivationValue}>{formatOdds(estimatedSharpPrice)}</span>
          </div>
        )}
        <div className={styles.derivationDivider} />
        <div className={`${styles.derivationRow} ${styles.derivationResult}`}>
          <span className={styles.derivationLabel}>Fair prob</span>
          <span className={styles.derivationValue}>
            {(trueProb * 100).toFixed(1)}% &rarr; {formatOdds(trueProbToAmerican(trueProb))}
          </span>
        </div>
      </div>
    );
  }

  // Default: direct Pinnacle devig (Shin's method)
  const impliedThis = americanToImplied(referencePrice);
  const impliedOther = americanToImplied(oppositeReferencePrice);
  const overround = impliedThis + impliedOther;
  const vigPct = overround - 1;
  const z = 1 - 1 / overround;
  const shinProb = shinDevig(impliedThis, impliedOther);

  return (
    <div className={styles.derivationPopover} onClick={(e) => e.stopPropagation()}>
      <div className={styles.derivationTitle}>Pinnacle Devig (Shin)</div>
      <div className={styles.derivationDivider} />
      <div className={styles.derivationRow}>
        <span className={styles.derivationLabel}>This side</span>
        <span className={styles.derivationValue}>
          {formatOdds(referencePrice)} &rarr; {(impliedThis * 100).toFixed(1)}%
        </span>
      </div>
      <div className={styles.derivationRow}>
        <span className={styles.derivationLabel}>Other side</span>
        <span className={styles.derivationValue}>
          {formatOdds(oppositeReferencePrice)} &rarr; {(impliedOther * 100).toFixed(1)}%
        </span>
      </div>
      <div className={styles.derivationRow}>
        <span className={styles.derivationLabel}>Overround</span>
        <span className={styles.derivationValue}>
          {(overround * 100).toFixed(1)}% (+{(vigPct * 100).toFixed(1)}% vig)
        </span>
      </div>
      <div className={styles.derivationRow}>
        <span className={styles.derivationLabel}>Shin z</span>
        <span className={styles.derivationValue}>
          {(z * 100).toFixed(2)}%
        </span>
      </div>
      <div className={styles.derivationDivider} />
      <div className={`${styles.derivationRow} ${styles.derivationFormula}`}>
        <span className={styles.derivationValue}>
          Shin({(impliedThis * 100).toFixed(1)}%, z={z.toFixed(3)}) = {(shinProb * 100).toFixed(1)}%
        </span>
      </div>
      <div className={`${styles.derivationRow} ${styles.derivationResult}`}>
        <span className={styles.derivationLabel}>Fair prob</span>
        <span className={styles.derivationValue}>
          {(trueProb * 100).toFixed(1)}% &rarr; {formatOdds(trueProbToAmerican(trueProb))}
        </span>
      </div>
    </div>
  );
}
