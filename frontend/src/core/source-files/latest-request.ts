export type LatestRequest = {
  sequence: number;
  signal: AbortSignal;
};

export function createLatestRequestTracker() {
  let latestSequence = 0;
  let activeController: AbortController | null = null;

  return {
    start(): LatestRequest {
      activeController?.abort();
      activeController = new AbortController();
      latestSequence += 1;
      return {
        sequence: latestSequence,
        signal: activeController.signal,
      };
    },

    isCurrent(sequence: number) {
      return sequence === latestSequence;
    },

    finish(sequence: number) {
      if (sequence === latestSequence) {
        activeController = null;
      }
    },

    cancel() {
      activeController?.abort();
      activeController = null;
      latestSequence += 1;
    },
  };
}
