export const MIN_BATCH_SELECTION = 2;
export const MAX_BATCH_SELECTION = 5;

export type BatchRequestGate = {
  current: boolean;
};

export function isSelectableOpenAlexId(value: string | null): value is string {
  return typeof value === "string" && /^W[0-9]{1,31}$/.test(value);
}

export function togglePaperSelection(
  selectedPaperIds: string[],
  openAlexId: string,
): string[] {
  if (!isSelectableOpenAlexId(openAlexId)) {
    return selectedPaperIds;
  }

  if (selectedPaperIds.includes(openAlexId)) {
    return selectedPaperIds.filter((paperId) => paperId !== openAlexId);
  }

  if (selectedPaperIds.length >= MAX_BATCH_SELECTION) {
    return selectedPaperIds;
  }

  return [...selectedPaperIds, openAlexId];
}

export function canAnalyzeSelection(selectedPaperIds: string[]): boolean {
  return (
    selectedPaperIds.length >= MIN_BATCH_SELECTION &&
    selectedPaperIds.length <= MAX_BATCH_SELECTION &&
    new Set(selectedPaperIds).size === selectedPaperIds.length &&
    selectedPaperIds.every(isSelectableOpenAlexId)
  );
}

export function claimBatchRequest(gate: BatchRequestGate): boolean {
  if (gate.current) {
    return false;
  }

  gate.current = true;
  return true;
}

export function releaseBatchRequest(gate: BatchRequestGate): void {
  gate.current = false;
}
