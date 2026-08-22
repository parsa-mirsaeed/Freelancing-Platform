import styles from "./talent.module.css";

export default function TalentLoading() {
  return (
    <main className={styles.page} aria-busy="true" aria-label="Loading talent marketplace">
      <section className={styles.intro}><div className={styles.introInner}><div className={styles.skeletonTitle} /><div className={styles.skeletonText} /></div></section>
      <section className={styles.workspace}><div className={styles.skeletonFilter} /><div className={styles.results}><div className={styles.skeletonCard} /><div className={styles.skeletonCard} /></div></section>
    </main>
  );
}
