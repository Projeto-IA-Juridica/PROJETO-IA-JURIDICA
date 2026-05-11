interface Props {
  className?: string
}

export default function Skeleton({ className = '' }: Props) {
  return <div className={`skeleton ${className}`} />
}

export function ClienteSkeleton() {
  return (
    <div className="flex items-center gap-3 p-3 border-l-2 border-transparent">
      <Skeleton className="w-8 h-8 rounded-full flex-shrink-0" />
      <div className="flex-1 space-y-1.5">
        <Skeleton className="h-3 w-3/4" />
        <Skeleton className="h-2.5 w-1/2" />
      </div>
    </div>
  )
}
