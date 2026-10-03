import { useSyncExternalStore } from 'react'

export type LogKind = 'info' | 'ok' | 'err'
export interface LogEntry {
  id: number
  time: string
  text: string
  kind: LogKind
}

const KEY = 'mladmin.log'
const MAX = 300

/** "hh:mm:ss.mmm" in 24-hour time, as on the old page. */
export function timeLabel(d: Date): string {
  const pad = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`
}

/** The session's event log, newest first, kept in sessionStorage so a reload does not lose it (storage that throws is ignored). */
export class EventLog {
  private entries: readonly LogEntry[]
  private listeners = new Set<() => void>()
  private nextId = 1

  constructor(
    private readonly storage: () => Storage | null = () => (typeof window === 'undefined' ? null : window.sessionStorage),
    private readonly now: () => Date = () => new Date(),
  ) {
    this.entries = this.load()
    this.nextId = this.entries.reduce((m, e) => Math.max(m, e.id), 0) + 1
  }

  subscribe = (l: () => void) => {
    this.listeners.add(l)
    return () => {
      this.listeners.delete(l)
    }
  }

  getSnapshot = (): readonly LogEntry[] => this.entries

  add(text: string, kind: LogKind = 'info') {
    const entry: LogEntry = { id: this.nextId++, time: timeLabel(this.now()), text, kind }
    this.entries = [entry, ...this.entries].slice(0, MAX)
    this.save()
    for (const l of this.listeners) l()
  }

  clear() {
    this.entries = []
    this.save()
    for (const l of this.listeners) l()
  }

  private load(): LogEntry[] {
    try {
      const raw = this.storage()?.getItem(KEY)
      const parsed: unknown = raw ? JSON.parse(raw) : []
      return Array.isArray(parsed)
        ? parsed.filter((e): e is LogEntry => typeof e?.id === 'number' && typeof e?.text === 'string' && typeof e?.time === 'string' && ['info', 'ok', 'err'].includes(e?.kind)).slice(0, MAX)
        : []
    } catch {
      return []
    }
  }

  private save() {
    try {
      this.storage()?.setItem(KEY, JSON.stringify(this.entries))
    } catch {
      /* no storage: the log lives in memory only */
    }
  }
}

export const eventLog = new EventLog()

export function useEventLog(): readonly LogEntry[] {
  return useSyncExternalStore(eventLog.subscribe, eventLog.getSnapshot)
}
