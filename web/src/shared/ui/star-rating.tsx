import { Star } from 'lucide-react'
import { useRef, useState, type KeyboardEvent } from 'react'
import { cn } from '../lib/utils'

/**
 * Five stars as a radio group: Tab reaches the group once, the arrow keys move between stars, Enter or Space rates.
 * Moving with the arrows only previews; a rating is sent on activation, never by moving (it triggers a request).
 * Each star is a 44 px target on narrow screens and 40 px from 640 px up (design D-8). While `disabled` (a rating for this
 * movie is in flight) the stars cannot be used. They are marked `aria-disabled` rather than natively disabled: a native
 * disabled button that has focus drops keyboard focus to <body>, so the user would lose their place on the card.
 */
export function StarRating({
  label,
  onRate,
  disabled = false,
  chosen = null,
}: {
  /** Accessible name of the group, e.g. "Chấm sao cho Pulp Fiction". */
  label: string
  onRate: (stars: number) => void
  disabled?: boolean
  /** The value being sent, kept lit while the request runs. */
  chosen?: number | null
}) {
  const [hover, setHover] = useState(0)
  const [focusIndex, setFocusIndex] = useState(1)
  const refs = useRef<Array<HTMLButtonElement | null>>([])
  const lit = disabled && chosen ? chosen : hover

  function move(to: number) {
    const next = to > 5 ? 1 : to < 1 ? 5 : to          // the arrow keys wrap around (ARIA radio group)
    setFocusIndex(next)
    setHover(next)
    refs.current[next - 1]?.focus()
  }

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, n: number) {
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
      e.preventDefault()
      move(n + 1)
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
      e.preventDefault()
      move(n - 1)
    } else if (e.key === 'Home') {
      e.preventDefault()
      move(1)
    } else if (e.key === 'End') {
      e.preventDefault()
      move(5)
    }
  }

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="flex flex-wrap gap-0.5"
      onMouseLeave={() => setHover(0)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setHover(0)
      }}
    >
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          ref={(el) => {
            refs.current[n - 1] = el
          }}
          type="button"
          role="radio"
          aria-checked={disabled && chosen === n}
          aria-label={`Chấm ${n} sao`}
          aria-disabled={disabled || undefined}
          tabIndex={n === focusIndex ? 0 : -1}
          onClick={() => {
            if (!disabled) onRate(n)
          }}
          onMouseEnter={() => setHover(n)}
          onFocus={() => {
            setFocusIndex(n)
            setHover(n)
          }}
          onKeyDown={(e) => onKeyDown(e, n)}
          className={cn(
            'inline-flex size-11 items-center justify-center rounded-md transition-colors sm:size-10',
            'text-muted-foreground hover:text-warning-text aria-disabled:cursor-default aria-disabled:hover:text-muted-foreground',
            n <= lit && 'text-warning-text',
          )}
        >
          <Star className={cn('size-6', n <= lit && 'fill-current')} aria-hidden="true" />
        </button>
      ))}
    </div>
  )
}
