interface PaginationProps {
  currentPage: number
  totalPages: number
  onPageChange: (page: number) => void
  totalItems?: number
}

export function Pagination({ currentPage, totalPages, onPageChange, totalItems }: PaginationProps) {
  if (totalPages <= 1) return null

  const pages: number[] = []
  const maxVisible = 7

  let start = Math.max(1, currentPage - Math.floor(maxVisible / 2))
  let end = Math.min(totalPages, start + maxVisible - 1)

  if (end - start < maxVisible - 1) {
    start = Math.max(1, end - maxVisible + 1)
  }

  for (let i = start; i <= end; i++) {
    pages.push(i)
  }

  return (
    <div
      className="pagination"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        marginTop: 16,
        flexWrap: 'wrap',
      }}
    >
      <button
        className="btn btn-sm btn-secondary"
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
      >
        ← Anterior
      </button>

      {start > 1 && (
        <>
          <button className="btn btn-sm btn-secondary" onClick={() => onPageChange(1)}>
            1
          </button>
          {start > 2 && <span style={{ color: 'var(--text-muted)', padding: '0 4px' }}>...</span>}
        </>
      )}

      {pages.map((p) => (
        <button
          key={p}
          className={`btn btn-sm ${p === currentPage ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => onPageChange(p)}
        >
          {p}
        </button>
      ))}

      {end < totalPages && (
        <>
          {end < totalPages - 1 && <span style={{ color: 'var(--text-muted)', padding: '0 4px' }}>...</span>}
          <button className="btn btn-sm btn-secondary" onClick={() => onPageChange(totalPages)}>
            {totalPages}
          </button>
        </>
      )}

      <button
        className="btn btn-sm btn-secondary"
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
      >
        Próxima →
      </button>

      {totalItems && (
        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 8 }}>
          Total: {totalItems} {totalItems === 1 ? 'item' : 'itens'}
        </span>
      )}
    </div>
  )
}
