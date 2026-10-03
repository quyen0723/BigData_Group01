/** The other page of this app, on the same UI version (design D-9): the new pages live at /app-next and /admin-next
 *  until the api serves them at /app and /admin, and a link must not jump from the new UI to the old one. */
export function siblingPage(kind: 'user' | 'admin', pathname: string = window.location.pathname): string {
  const next = pathname.startsWith('/app-next') || pathname.startsWith('/admin-next')
  if (kind === 'user') return next ? '/app-next' : '/app'
  return next ? '/admin-next' : '/admin'
}
