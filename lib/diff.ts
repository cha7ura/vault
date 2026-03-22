export interface DiffWord {
  text: string;
  type: "match" | "insert" | "delete";
}

/**
 * Word-level diff using Longest Common Subsequence (LCS).
 * Compares two word arrays with case-insensitive matching and returns
 * annotated left/right arrays for side-by-side rendering.
 */
export function wordDiff(
  wordsA: string[],
  wordsB: string[]
): { left: DiffWord[]; right: DiffWord[] } {
  const m = wordsA.length;
  const n = wordsB.length;

  // Build LCS table
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array(n + 1).fill(0)
  );
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (wordsA[i - 1].toLowerCase() === wordsB[j - 1].toLowerCase()) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  // Backtrack to produce diff
  const left: DiffWord[] = [];
  const right: DiffWord[] = [];
  let i = m;
  let j = n;

  while (i > 0 || j > 0) {
    if (
      i > 0 &&
      j > 0 &&
      wordsA[i - 1].toLowerCase() === wordsB[j - 1].toLowerCase()
    ) {
      left.unshift({ text: wordsA[i - 1], type: "match" });
      right.unshift({ text: wordsB[j - 1], type: "match" });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      right.unshift({ text: wordsB[j - 1], type: "insert" });
      j--;
    } else {
      left.unshift({ text: wordsA[i - 1], type: "delete" });
      i--;
    }
  }

  return { left, right };
}
