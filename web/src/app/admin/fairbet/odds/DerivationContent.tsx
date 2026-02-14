import { americanToImplied, formatOdds, trueProbToAmerican } from "@/lib/api/fairbet";
import styles from "./styles.module.css";

export function DerivationContent({
  referencePrice,
  oppositeReferencePrice,
  trueProb,
}: {
  referencePrice: number;
  oppositeReferencePrice: number;
  trueProb: number;
}) {
  const impliedThis = americanToImplied(referencePrice);
  const impliedOther = americanToImplied(oppositeReferencePrice);
  const overround = impliedThis + impliedOther;
  const vigPct = overround - 1;

  return (
    <div className={styles.derivationPopover} onClick={(e) => e.stopPropagation()}>
      <div className={styles.derivationTitle}>Pinnacle Devig</div>
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
      <div className={styles.derivationDivider} />
      <div className={`${styles.derivationRow} ${styles.derivationFormula}`}>
        <span className={styles.derivationValue}>
          {(impliedThis * 100).toFixed(1)}% &divide; {(overround * 100).toFixed(1)}% = {(trueProb * 100).toFixed(1)}%
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
