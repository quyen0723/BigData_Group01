import { CircleCheck, CircleX } from 'lucide-react'
import type { ModelVersion, RetrainProgress } from '@/shared/api/types'
import { useSystemStatus } from '@/shared/hooks/queries'
import { cn } from '@/shared/lib/utils'
import { Progress } from '@/shared/ui/progress'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/ui/table'

const stamp = (iso: string | null) => (iso ?? '—').replace('T', ' ').slice(0, 19)

/** A version's status as a chip: the word is always there, colour only reinforces it. */
function StatusChip({ status }: { status: string }) {
  const tone =
    status === 'active'
      ? 'border-success/40 bg-success/10 text-success'
      : status === 'rejected'
        ? 'border-destructive/40 bg-destructive/10 text-destructive'
        : 'border-border bg-muted text-muted-foreground'
  return <span className={cn('inline-block rounded-full border px-2.5 py-0.5 text-xs font-semibold', tone)}>{status}</span>
}

/** Every gate check with an icon and the word PASS or FAIL (not colour alone); a failed one also shows why. */
function GateChecks({ version }: { version: ModelVersion }) {
  const checks = version.gateChecks
  if (checks.length === 0) return <span className="text-muted-foreground">—</span>
  const passed = checks.filter((c) => c.passed).length
  return (
    <div className="space-y-1.5">
      <div className="font-medium">{passed}/{checks.length} đạt</div>
      <ul className="space-y-1">
        {checks.map((c) => (
          <li key={c.name} className="flex items-start gap-1.5 text-xs">
            {c.passed ? (
              <CircleCheck className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden="true" />
            ) : (
              <CircleX className="mt-0.5 size-3.5 shrink-0 text-destructive" aria-hidden="true" />
            )}
            <span>
              <span className={cn('font-semibold', c.passed ? 'text-success' : 'text-destructive')}>{c.passed ? 'PASS' : 'FAIL'}</span>{' '}
              {c.name}
              {!c.passed && c.detail && <span className="text-muted-foreground"> — {c.detail}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function RetrainProgressBar({ progress }: { progress: RetrainProgress }) {
  const pct = progress.nMin > 0 ? Math.min(100, Math.round((progress.pending / progress.nMin) * 100)) : 0
  return (
    <div className="space-y-2">
      <Progress value={pct} aria-label={`Tiến độ retrain: ${progress.pending} trên ${progress.nMin} event`} className="h-2.5 bg-primary/15" />
      <p className="text-sm text-muted-foreground">
        {progress.pending} / {progress.nMin} event đã áp dụng kể từ lần bàn giao gần nhất
        {progress.watermark ? ` (${stamp(progress.watermark)})` : ' (chưa có lần bàn giao nào)'}
        {progress.pending >= progress.nMin ? ' — đủ ngưỡng, trigger sẽ tạo gói bàn giao' : ''}
      </p>
    </div>
  )
}

/** Model lifecycle (read only): versions with their gate checks, and the retrain progress. */
export function ModelPanel() {
  const system = useSystemStatus({ refetchInterval: 10_000 })
  return (
    <div className="space-y-4">
      <section aria-labelledby="versions-title" className="space-y-3 rounded-xl border bg-card p-4">
        <h2 id="versions-title" className="text-lg font-semibold">
          Vòng đời model (chỉ xem)
        </h2>
        {system.isPending && <p className="text-muted-foreground">Đang tải…</p>}
        {system.isError && (
          <p role="alert" className="text-destructive">
            Không tải được trạng thái hệ thống.
          </p>
        )}
        {system.data && (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Version</TableHead>
                  <TableHead>Trạng thái</TableHead>
                  <TableHead>Nạp lúc</TableHead>
                  <TableHead>Cổng kiểm (gate)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {system.data.versions.map((v) => (
                  <TableRow key={v.version} className="align-top">
                    <TableCell className="font-mono">{v.version}</TableCell>
                    <TableCell>
                      <StatusChip status={v.status} />
                    </TableCell>
                    <TableCell className="font-mono text-xs">{stamp(v.importedAt)}</TableCell>
                    <TableCell>
                      <GateChecks version={v} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <section aria-labelledby="retrain-title" className="space-y-3 rounded-xl border bg-card p-4">
        <h2 id="retrain-title" className="text-lg font-semibold">
          Tiến độ retrain
        </h2>
        {system.data && <RetrainProgressBar progress={system.data.retrainProgress} />}
        <p className="text-sm text-muted-foreground">
          Lịch chốt: 1 tuần/lần — chưa có scheduler chạy thật, hiện trigger theo số event hoặc <code className="font-mono">--force</code>. Việc train chạy
          trên Colab (Person 1); trang này không có nút kích hoạt.
        </p>
      </section>
    </div>
  )
}
