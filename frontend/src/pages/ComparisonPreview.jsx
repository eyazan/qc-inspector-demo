import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import axios from 'axios'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorAlert from '../components/ErrorAlert'
import { API_BASE_URL } from '../config'

const POLL_MS = 3000

export default function ComparisonPreview() {
  const { runId } = useParams()
  const navigate = useNavigate()

  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [comparing, setComparing] = useState(false)
  const [compareStep, setCompareStep] = useState('')
  const pollRef = useRef(null)

  // Resumable Stage-2 poller: reused by the Compare button AND on mount when a
  // comparison is already running on the server (continue where you left off).
  const startPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current)
    setComparing(true)
    const poll = async () => {
      try {
        const s = await axios.get(`${API_BASE_URL}/api/processing-status/${encodeURIComponent(runId)}`)
        const st = s.data
        setCompareStep(st.current_step || 'İşleniyor...')
        if (!st.is_processing) {
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
          if (st.status === 'failed') {
            setError('Karşılaştırma sırasında hata oluştu.')
            setComparing(false)
          } else {
            navigate(`/report/${encodeURIComponent(runId)}`)
          }
        }
      } catch (e) { /* yut */ }
    }
    poll()
    pollRef.current = setInterval(poll, POLL_MS)
  }

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const res = await axios.get(`${API_BASE_URL}/api/spec-preview/${encodeURIComponent(runId)}`)
        if (!cancelled) setPreview(res.data)
        // Resume: if Stage-2 is still running (or already done) on the server,
        // pick it up instead of showing a fresh "Karşılaştır" button.
        const s = await axios.get(`${API_BASE_URL}/api/processing-status/${encodeURIComponent(runId)}`)
        if (!cancelled) {
          if (s.data?.is_processing) startPolling()
          else if (s.data?.status === 'completed') navigate(`/report/${encodeURIComponent(runId)}`)
        }
      } catch (err) {
        if (!cancelled) setError('Önizleme verisi alınamadı.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [runId])

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const specText = preview?.sap_spec_text || ''
  const specTextFound = specText.trim().length > 0
  const specDocStatus = preview?.spec_doc_status || ''
  const specMissing = specDocStatus.toLowerCase().includes('bulunamam')
  const specIndexed = specDocStatus.toLowerCase().includes('indeks') || specDocStatus.toLowerCase().includes("network")

  const vendorUrl = `${API_BASE_URL}/api/document/${encodeURIComponent(runId)}/vendor`
  const specPdfUrl = `${API_BASE_URL}/api/spec-document/${encodeURIComponent(runId)}`

  const canCompare = specTextFound || specIndexed

  const handleCompare = async () => {
    setComparing(true)
    setError(null)
    setCompareStep('Karşılaştırma başlatılıyor...')
    try {
      const res = await axios.post(`${API_BASE_URL}/api/start-comparison/${encodeURIComponent(runId)}`)
      if (res.data?.status === 'rejected') {
        setError(res.data?.message || 'Karşılaştırma başlatılamadı.')
        setComparing(false)
        return
      }
      const poll = async () => {
        try {
          const s = await axios.get(`${API_BASE_URL}/api/processing-status/${encodeURIComponent(runId)}`)
          const st = s.data
          setCompareStep(st.current_step || 'İşleniyor...')
          if (!st.is_processing) {
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
            if (st.status === 'failed') {
              setError('Karşılaştırma sırasında hata oluştu.')
              setComparing(false)
            } else {
              navigate(`/report/${encodeURIComponent(runId)}`)
            }
          }
        } catch (e) { /* yut */ }
      }
      poll()
      pollRef.current = setInterval(poll, POLL_MS)
    } catch (err) {
      setError('Karşılaştırma başlatılamadı.')
      setComparing(false)
    }
  }

  if (loading) {
    return <div className="form-container"><LoadingSpinner /><p>Önizleme yükleniyor...</p></div>
  }

  return (
    <div className="cmp-preview">
      <style>{`
        .cmp-preview { max-width: 1400px; margin: 0 auto; padding: 24px 16px 60px; }
        .cmp-head { display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-bottom: 16px; }
        .cmp-title { font-size:1.45rem; font-weight:700; color:#0f172a; margin:0; }
        .cmp-meta { display:flex; gap:14px; flex-wrap:wrap; font-size:0.85rem; color:#475569; margin-top:6px; }
        .cmp-meta b { color:#0f172a; }
        .cmp-badge { display:inline-block; padding:4px 12px; border-radius:999px; font-size:0.78rem; font-weight:600; }
        .cmp-badge.ok { background:rgba(22,163,74,0.1); color:#15803d; }
        .cmp-badge.warn { background:rgba(220,38,38,0.1); color:#b91c1c; }
        .cmp-grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; margin-top:8px; }
        @media (max-width: 1000px){ .cmp-grid{ grid-template-columns:1fr; } }
        .cmp-card { border:1px solid #e2e8f0; border-radius:14px; overflow:hidden; background:#fff; display:flex; flex-direction:column; }
        .cmp-card h3 { margin:0; padding:11px 14px; font-size:0.9rem; background:#f1f5f9; border-bottom:1px solid #e2e8f0; color:#0f172a; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .cmp-body { padding:0; min-height:480px; display:flex; flex-direction:column; }
        .cmp-spec-text { white-space:pre-wrap; font-family:ui-monospace,monospace; font-size:0.8rem; line-height:1.5; color:#334155; padding:14px 16px; height:480px; overflow:auto; }
        .cmp-empty { color:#94a3b8; font-style:italic; padding:40px 16px; text-align:center; }
        .cmp-pdf { width:100%; height:480px; border:0; }
        .cmp-actions { margin-top:22px; display:flex; gap:12px; align-items:center; justify-content:center; flex-wrap:wrap; }
        .cmp-btn { padding:12px 28px; border-radius:10px; border:0; font-size:0.95rem; font-weight:600; cursor:pointer; }
        .cmp-btn.primary { background:#2563eb; color:#fff; }
        .cmp-btn.primary:disabled { opacity:0.55; cursor:not-allowed; }
        .cmp-btn.ghost { background:transparent; color:#475569; border:1px solid #cbd5e1; }
        .cmp-progress { text-align:center; color:#475569; font-size:0.9rem; margin-top:10px; }
      `}</style>

      {error && <ErrorAlert message={error} onClose={() => setError(null)} />}

      <div className="cmp-head">
        <div>
          <h1 className="cmp-title">Yükleme Tamamlandı — Önizleme</h1>
          <div className="cmp-meta">
            <span>PO: <b>{preview?.po_number || '-'}</b></span>
            <span>Kalem: <b>{preview?.po_item || '-'}</b></span>
            <span>Malzeme: <b>{preview?.material || '-'}</b></span>
            <span>Spec: <b>{preview?.sap_spec_name || '-'}</b></span>
          </div>
        </div>
        <span className={`cmp-badge ${specMissing ? 'warn' : 'ok'}`}>
          {specDocStatus || (specTextFound ? 'Spec hazır' : 'Spec yok')}
        </span>
      </div>

      <div className="cmp-grid">
        {/* SOL: Vendor PDF */}
        <div className="cmp-card">
          <h3>Vendor Dokümanı{preview?.vendor_filename ? ` — ${preview.vendor_filename}` : ''}</h3>
          <div className="cmp-body">
            {preview?.vendor_doc_id ? (
              <iframe className="cmp-pdf" title="vendor" src={vendorUrl} />
            ) : (
              <div className="cmp-empty">Vendor dokümanı bulunamadı</div>
            )}
          </div>
        </div>

        {/* ORTA: SAP spec metni */}
        <div className="cmp-card">
          <h3>Spec Metni (SAP){preview?.sap_spec_name ? ` — ${preview.sap_spec_name}` : ''}</h3>
          <div className="cmp-body">
            {specTextFound ? (
              <div className="cmp-spec-text">{specText}</div>
            ) : (
              <div className="cmp-empty">
                {specMissing
                  ? 'Bu vendor dokümanına ait spec dosyası bulunamamıştır.'
                  : 'SAP spec metni alınamadı.'}
              </div>
            )}
          </div>
        </div>

        {/* SAĞ: Spec PDF (indekslenmişse) */}
        <div className="cmp-card">
          <h3>Spec Dokümanı (PDF)</h3>
          <div className="cmp-body">
            {specIndexed ? (
              <iframe className="cmp-pdf" title="spec" src={specPdfUrl} />
            ) : (
              <div className="cmp-empty">
                {specMissing
                  ? 'Spec PDF bulunamadı.'
                  : 'Spec dokümanı henüz indekslenmemiş.'}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="cmp-actions">
        <button className="cmp-btn ghost" onClick={() => navigate('/pdf-upload')} disabled={comparing}>
          Yeni Yükleme
        </button>
        <button
          className="cmp-btn primary"
          onClick={handleCompare}
          disabled={comparing || !canCompare}
          title={!canCompare ? 'Spec olmadan karşılaştırma yapılamaz' : ''}
        >
          {comparing ? 'Karşılaştırılıyor...' : 'Karşılaştır'}
        </button>
      </div>

      {comparing && (
        <div className="cmp-progress">
          <LoadingSpinner />
          <p>{compareStep}</p>
        </div>
      )}
    </div>
  )
}
