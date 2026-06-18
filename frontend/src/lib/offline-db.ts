// TODO: Phase 2 — Dexie dependency was intentionally skipped. This file
// currently provides an in-memory fallback with the same interface so the
// rest of the port compiles. Wire up IndexedDB/Dexie if offline persistence
// is required in production.

export type OfflineAction = 'create' | 'update' | 'delete';

export interface OfflineChange {
  id?: number;
  table: string;
  action: OfflineAction;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
  timestamp: number;
  synced: boolean;
}

class OfflineDBStub {
  private _changes: OfflineChange[] = [];

  get changes(): OfflineChange[] {
    return this._changes;
  }

  async addChange(change: Omit<OfflineChange, 'id' | 'timestamp'>): Promise<OfflineChange> {
    const entry: OfflineChange = { ...change, id: Date.now(), timestamp: Date.now() };
    this._changes.push(entry);
    return entry;
  }

  async getPendingChanges(): Promise<OfflineChange[]> {
    return this._changes.filter((c) => !c.synced);
  }

  async markSynced(id: number): Promise<void> {
    const change = this._changes.find((c) => c.id === id);
    if (change) change.synced = true;
  }

  async clearSynced(): Promise<void> {
    this._changes = this._changes.filter((c) => !c.synced);
  }
}

export const offlineDb = new OfflineDBStub();
