import React, { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  getReport,
  getReviewRegions,
  overrideFinding,
  reportPdfUrl,
} from '../services/api'
import '../styles/inspector.css'

const STATUS_LABEL = {
  COMPLIANT: 'UYUMLU',
  PARTIAL: 'SINIRDA',
  NON_COMPLIANT: 'UYUMSUZ',
  MISSING: 'EKSIK',
  NOT_COVERED: 'KAPSAM DISI',
}

const SUMMARY_META = [
  { key: 'COMPLIANT', label: 'Uyumlu', color: 'var(--qc-compliant)' },
  { key: 'PARTIAL', label: 'Sinirda', color: 'var(--qc-partial)' },
  { key: 'NON_COMPLIANT', label: 'Uyumsuz', color: 'var(--qc-noncompliant)' },
  { key: 'MISSING', label: 'Eksik', color: 'var(--qc-missing)' },
  { key: 'NOT_COVERED', label: 'Kapsam disi', color: 'var(--qc-notcovered)' },
]

function FindingRow({ finding, onOverride }) {
  const [expanded, setExpanded] = useState(false)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  const handleAction = async (action, newStatus) => {
    setSaving(true)
    try {
      await onOverride(finding.id, { action, newStatus, note })
      setNote('')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="qc-finding-row">
        <div className="qc-cell qc-expand-toggle" onClick={() => setExpanded(!expanded)}>
          <span className="param-name">
            {expanded ? '▾ ' : '▸ '}{finding.parameter}
            {finding.has_override && <span className="qc-override-flag"> · düzenlendi</span>}
          </span>
          {finding.spec_section && <span className="param-section">§ {finding.spec_section}</span>}
        </div>
        <div className="qc-cell">
          <span className="value value-dim">{finding.spec_value || '—'}</span>
          <span className="qc-source-tag">spec</span>
        </div>
        <div className="qc-cell">
          <span className="value">{finding.vendor_value || '—'}</span>
          <span className="qc-source-tag">{finding.source === 'llm' ? 'AI yorumu' : 'ölçülen'}</span>
        </div>
        <div className="qc-cell">
          <span className={`qc-status ${finding.status}`}>
            {STATUS_LABEL[finding.status] || finding.status}
          </span>
        </div>
        <div className="qc-cell">
          <span className={`qc-sev ${finding.severity}`}>{finding.severity}</span>
        </div>
      </div>

      {expanded && (
        <div className="qc-finding-row">
          <div className="qc-finding-detail">
            <div className="qc-rationale">
              {finding.rationale || 'Gerekçe verilmedi.'}
              {finding.deviation_pct != null && (
                <> &nbsp;·&nbsp; Sapma: <strong>{finding.deviation_pct}%</strong></>
              )}
              {finding.override_note && (
                <><br /><em>Denetçi notu: {finding.override_note}</em></>
              )}
            </div>
            <div className="qc-override-bar">
              <button
                className="qc-btn qc-btn-approve"
                disabled={saving}
                onClick={() => handleAction('approve', null)}
              >
                ✓ Onayla
              </button>
              <button
                className="qc-btn qc-btn-reject"
                disabled={saving}
                onClick={() => handleAction('reject', 'NON_COMPLIANT')}
              >
                ✕ Uyumsuz işaretle
              </button>
              <button
                className="qc-btn"
                disabled={saving}
                onClick={() => handleAction('edit', 'COMPLIANT')}
              >
                Uyumlu işaretle
              </button>
              <input
                className="qc-override-note"
                placeholder="Denetçi notu (opsiyonel)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default function InspectorReport() {
  const { id } = useParams()
  const [report, setReport] = useState(null)
  const [reviewRegions, setReviewRegions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const [data, regions] = await Promise.all([
        getReport(id),
        getReviewRegions(id).catch(() => []),
      ])
      setReport(data)
      setReviewRegions(regions)
    } catch (err) {
      setError(err.detail || err.message || 'Rapor yüklenemedi')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  const handleOverride = async (findingId, payload) => {
    await overrideFinding(findingId, payload)
    await load() // durumlari tazele
  }

  if (loading) return <div className="qc-inspector"><div className="qc-empty">Rapor yükleniyor…</div></div>
  if (error) return <div className="qc-inspector"><div className="qc-empty">{error}</div></div>
  if (!report) return null

  const findings = report.findings || []
  const summary = report.summary || {}

  return (
    <div className="qc-inspector">
      <div className="qc-header">
        <div>
          <h1>Uygunluk Denetimi</h1>
          <div className="qc-header-meta">
            {report.po_number && <span>PO <strong>{report.po_number}</strong></span>}
            {report.po_item && <span>Kalem <strong>{report.po_item}</strong></span>}
            {report.material && <span>Malzeme <strong>{report.material}</strong></span>}
            <span>Bulgu <strong>{findings.length}</strong></span>
          </div>
        </div>
        <div className="qc-actions">
          <Link to="/comparison-results" className="qc-btn">← Geçmiş</Link>
          <a className="qc-btn qc-btn-primary" href={reportPdfUrl(id)} target="_blank" rel="noreferrer">
            PDF indir
          </a>
        </div>
      </div>

      {reviewRegions.length > 0 && (
        <div className="qc-review-banner">
          ⚠ <strong>{reviewRegions.length}</strong> bölge düşük güvenle okundu — gözden geçirilmesi önerilir.
        </div>
      )}

      <div className="qc-summary">
        {SUMMARY_META.map(({ key, label, color }) => (
          <div className="qc-summary-card" key={key} style={{ '--accent': color }}>
            <div className="count" style={{ color }}>{summary[key] || 0}</div>
            <div className="label">{label}</div>
          </div>
        ))}
      </div>

      <div className="qc-split">
        <div className="qc-split-head">Şartname gereksinimi</div>
        <div className="qc-split-head">Vendor belgesi · karar</div>
      </div>

      <div className="qc-findings">
        <div className="qc-finding-row head">
          <div className="qc-cell">Parametre</div>
          <div className="qc-cell">Spec değeri</div>
          <div className="qc-cell">Vendor değeri</div>
          <div className="qc-cell">Durum</div>
          <div className="qc-cell">Kritiklik</div>
        </div>
        {findings.length === 0 ? (
          <div className="qc-empty">Bu rapor için yapısal bulgu yok.</div>
        ) : (
          findings.map((f) => (
            <FindingRow key={f.id} finding={f} onOverride={handleOverride} />
          ))
        )}
      </div>
    </div>
  )
}
