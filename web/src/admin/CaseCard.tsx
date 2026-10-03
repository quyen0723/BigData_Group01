import type { CaseDef } from './caseData'

/** The use-case card: the five cells of the team's table, what was observed, the decision and the steps to follow. */
export function CaseCard({ def, observed }: { def: CaseDef; observed: string }) {
  const rows: Array<[string, string]> = [
    ['Điều gì xảy ra', def.what],
    ['Recommendation', def.rec],
    ['Streaming', def.streaming],
    ['ALS Retrain', def.retrain],
    ['Chốt', def.chot],
  ]
  return (
    <section aria-labelledby="case-title" className="space-y-3 rounded-xl border bg-card p-4">
      <h2 id="case-title" className="text-lg font-semibold">
        {def.title}
      </h2>
      <table className="w-full text-sm">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k} className="border-b align-top">
              <th scope="row" className="w-36 py-1.5 pr-3 text-left font-normal text-muted-foreground sm:w-40">
                {k}
              </th>
              <td className="py-1.5">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="rounded-md bg-muted px-3 py-2 font-mono text-xs" data-testid="observed">
        {observed}
      </div>
      {def.decision && <p className="text-sm text-warning-text">{def.decision}</p>}
      {def.how.length > 0 && (
        <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
          {def.how.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      )}
    </section>
  )
}
