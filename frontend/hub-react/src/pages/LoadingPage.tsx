export default function LoadingPage() {
  return (
    <div
      className="fixed inset-0 flex flex-col items-center justify-center"
      style={{ background: '#EAF2FA' }}
    >
      {/* Spinner — cores névoa */}
      <div className="fade-in-up" style={{ animationDelay: '0.08s' }}>
        <div
          className="pl"
          style={
            {
              '--bg':       '#EAF2FA',
              '--primary1': '#1652BE',
              '--primary2': '#5B9BD5',
              '--fg-t':     'rgba(12,30,48,0.40)',
            } as React.CSSProperties
          }
        >
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="pl__dot" />
          ))}
          <div className="pl__text" style={{ color: 'rgba(12,30,48,0.55)' }}>
            amicus
          </div>
        </div>
      </div>

      {/* Label */}
      <p
        className="fade-in-up mt-14 text-[10px] font-semibold tracking-widest uppercase"
        style={{
          color: 'rgba(12,30,48,0.30)',
          animationDelay: '0.35s',
          letterSpacing: '0.22em',
        }}
      >
        Carregando
      </p>
    </div>
  )
}
