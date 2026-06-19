import React from 'react'
import { useNavigate } from 'react-router-dom'

const cards = [
  {
    to: '/pdf-upload',
    eyebrow: 'Başlat',
    title: 'Vendor Dokümanı Yükle',
    desc: 'Tedarikçi belgesini yükleyin; SPEC SAP\u2019tan otomatik çekilir ve karşılaştırma başlar.',
    icon: (
      <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 3v4a1 1 0 0 0 1 1h4" />
        <path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z" />
        <path d="M12 11v6" />
        <path d="M9.5 13.5 12 11l2.5 2.5" />
      </svg>
    ),
  },
  {
    to: '/comparison-results',
    eyebrow: 'İncele',
    title: 'Karşılaştırma Sonuçları',
    desc: 'Geçmiş denetimleri görüntüleyin, bulguları onaylayın veya düzeltin, PDF rapor alın.',
    icon: (
      <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18" />
        <rect x="7" y="12" width="3" height="6" rx="0.5" />
        <rect x="12.5" y="8" width="3" height="10" rx="0.5" />
        <rect x="18" y="5" width="3" height="13" rx="0.5" transform="translate(-1 0)" />
      </svg>
    ),
  },
]

export default function Home() {
  const navigate = useNavigate()

  return (
    <div className="qc-home">
      <style>{`
        .qc-home {
          max-width: 960px;
          margin: 0 auto;
          padding: 56px 24px 72px;
        }
        .qc-home__hero {
          position: relative;
          text-align: center;
          padding: 48px 28px 52px;
          border-radius: 20px;
          overflow: hidden;
          background:
            radial-gradient(120% 120% at 50% -20%, rgba(37,99,235,0.10), transparent 60%),
            linear-gradient(180deg, #ffffff 0%, #f3f6fb 100%);
          border: 1px solid #e2e8f0;
          box-shadow: 0 12px 32px -12px rgba(30,64,175,0.18);
        }
        .qc-home__hero::before {
          content: "";
          position: absolute;
          inset: 0;
          background-image:
            linear-gradient(rgba(37,99,235,0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(37,99,235,0.05) 1px, transparent 1px);
          background-size: 28px 28px;
          mask-image: radial-gradient(circle at 50% 0%, black, transparent 72%);
          -webkit-mask-image: radial-gradient(circle at 50% 0%, black, transparent 72%);
          pointer-events: none;
        }
        .qc-home__eyebrow {
          position: relative;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 0.72rem;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          font-weight: 600;
          color: #2563eb;
          background: rgba(37,99,235,0.08);
          padding: 6px 14px;
          border-radius: 999px;
          margin-bottom: 22px;
        }
        .qc-home__dot {
          width: 7px; height: 7px; border-radius: 50%;
          background: #2563eb;
          box-shadow: 0 0 0 3px rgba(37,99,235,0.18);
        }
        .qc-home__title {
          position: relative;
          font-size: clamp(2rem, 5vw, 3rem);
          line-height: 1.05;
          font-weight: 800;
          letter-spacing: -0.02em;
          color: #0f172a;
          margin: 0 0 14px;
        }
        .qc-home__title span { color: #2563eb; }
        .qc-home__subtitle {
          position: relative;
          max-width: 540px;
          margin: 0 auto;
          font-size: 1.02rem;
          line-height: 1.6;
          color: #475569;
        }
        .qc-home__grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 20px;
          margin-top: 32px;
        }
        @media (max-width: 640px) {
          .qc-home__grid { grid-template-columns: 1fr; }
        }
        .qc-card {
          text-align: left;
          cursor: pointer;
          background: #ffffff;
          border: 1px solid #e2e8f0;
          border-radius: 16px;
          padding: 26px 24px;
          transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
          display: flex;
          flex-direction: column;
          gap: 14px;
          min-height: 168px;
        }
        .qc-card:hover {
          transform: translateY(-4px);
          box-shadow: 0 18px 36px -16px rgba(30,64,175,0.32);
          border-color: #bfdbfe;
        }
        .qc-card:focus-visible {
          outline: 3px solid rgba(37,99,235,0.45);
          outline-offset: 2px;
        }
        .qc-card__icon {
          width: 52px; height: 52px;
          border-radius: 12px;
          display: grid; place-items: center;
          color: #2563eb;
          background: linear-gradient(135deg, rgba(37,99,235,0.12), rgba(37,99,235,0.04));
        }
        .qc-card__eyebrow {
          font-size: 0.68rem; letter-spacing: 0.16em; text-transform: uppercase;
          font-weight: 700; color: #94a3b8;
        }
        .qc-card__title {
          font-size: 1.16rem; font-weight: 700; color: #0f172a; margin: 0;
        }
        .qc-card__desc {
          font-size: 0.9rem; line-height: 1.5; color: #64748b; margin: 0;
        }
        .qc-card__cta {
          margin-top: auto;
          display: inline-flex; align-items: center; gap: 6px;
          font-size: 0.85rem; font-weight: 600; color: #2563eb;
        }
        .qc-card:hover .qc-card__cta svg { transform: translateX(3px); }
        .qc-card__cta svg { transition: transform 0.18s ease; }
        @media (prefers-reduced-motion: reduce) {
          .qc-card, .qc-card__cta svg { transition: none; }
          .qc-card:hover { transform: none; }
        }
      `}</style>

      <section className="qc-home__hero">
        <span className="qc-home__eyebrow"><span className="qc-home__dot" /> Kalite Kontrol Otomasyonu</span>
        <h1 className="qc-home__title">Vendor<span>·</span>Spec<br/>Karşılaştırma Sistemi</h1>
        <p className="qc-home__subtitle">
          Tedarikçi dokümanlarını teknik Spec'e karşı otomatik denetleyin.
          OCR, değer karşılaştırma ve uygunluk raporu tek akışta.
        </p>

        <div className="qc-home__grid">
          {cards.map((c) => (
            <div
              key={c.to}
              className="qc-card"
              role="button"
              tabIndex={0}
              onClick={() => navigate(c.to)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') navigate(c.to) }}
            >
              <div className="qc-card__icon">{c.icon}</div>
              <span className="qc-card__eyebrow">{c.eyebrow}</span>
              <h2 className="qc-card__title">{c.title}</h2>
              <p className="qc-card__desc">{c.desc}</p>
              <span className="qc-card__cta">
                Aç
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12h14M13 6l6 6-6 6" />
                </svg>
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
