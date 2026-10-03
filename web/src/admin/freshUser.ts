/** A random user with no history for the "fresh user" cases (1, 7 and 9): ids 500000..599998, up to `tries` attempts. The
 *  old page returned the last id it drew even when that user had ratings, so a run never ends without a user. */
export async function pickFreshUser(deps: {
  hasHistory: (userId: number) => Promise<boolean>
  rand?: () => number
  tries?: number
}): Promise<number> {
  const rand = deps.rand ?? Math.random
  const tries = deps.tries ?? 5
  let id = 500000
  for (let i = 0; i < tries; i++) {
    id = 500000 + Math.floor(rand() * 99999)
    if (!(await deps.hasHistory(id))) return id
  }
  return id
}
