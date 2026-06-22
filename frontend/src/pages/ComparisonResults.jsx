import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getComparisonResults, apiClient } from '../services/api'
import { API_BASE_URL } from '../config'

// Compliance vocabulary shared with the report screen (frontend status codes).
const STATUS_META = [
  { key: 'COMPLIANT', label: 'Uyumlu', color: '#10b981' },
  { key: 'PARTIAL', label: 'Sınırda', color: '#f59e0b' },
  { key: 'NON_COMPLIANT', label: 'Uyumsuz', color: '#ef4444' },
  { key: 'MISSING', label: 'Eksik', color: '#6b7280' },
  { key: 'NOT_COVERED', label: 'Kapsam dışı', color: '#94a3b8' },
]

function ComplianceChips({ summary, total }) {
  const entries = STATUS_META.filter((m) => (summary?.[m.key] || 0) > 0)
  if (!total) {
    return <span style={{ color: '#94a3b8', fontSize: 13 }}>Bulgu yok</span>
  }
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
      {entries.map((m) => (
        <span
          key={m.key}
          title={m.label}
          style={{
            backgroundColor: m.color, color: '#fff', borderRadius: 12,
            padding: '2px 9px', fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap',
          }}
        >
          {m.label}: {summary[m.key]}
        </span>
      ))}
      <span style={{ color: '#64748b', fontSize: 12 }}>(toplam {total})</span>
    </div>
  )
}

const btn = (bg) => ({
  cursor: 'pointer', fontSize: 13, padding: '6px 10px', whiteSpace: 'nowrap',
  backgroundColor: bg, borderColor: bg, color: '#fff', borderRadius: 5, fontWeight: 500,
})

export default function ComparisonResults() {
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchResults = async () => {
    try {
      const data = await getComparisonResults()
      setResults(data)
    } catch (err) {
      setError(err.detail || err.message || 'Sonuçlar yüklenemedi')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchResults() }, [])

  const handleDelete = async (reportId) => {
    if (!window.confirm('Bu karşılaştırma sonucunu silmek istediğinizden emin misiniz?')) return
    try {
      await apiClient.delete(`/api/comparison-results/${encodeURIComponent(reportId)}`)
      fetchResults()
    } catch (err) {
      alert('Silme başarısız: ' + (err.detail || err.message || 'Bilinmeyen hata'))
    }
  }

  const handleRename = async (reportId, current) => {
    const newName = prompt('İşlem adını yeniden adlandırın:', current || '')
    if (!newName || !newName.trim()) return
    try {
      await apiClient.post(`/api/comparison-results/${encodeURIComponent(reportId)}/rename`, { new_name: newName.trim() })
      fetchResults()
    } catch (err) {
      alert('Yeniden adlandırma başarısız: ' + (err.detail || err.message || 'Bilinmeyen hata'))
    }
  }

  const rows = (results || []).filter((r) => r.type === 'final_aggregation')

  return (
    <div className="form-container">
      <h1 className="page-title">Karşılaştırma Sonuçları</h1>

      {loading && <div className="loading">Yükleniyor...</div>}
      {error && <div className="error">{error}</div>}

      {rows.length > 0 ? (
        <div className="table-responsive">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 40 }}>#</th>
                <th>PO / Kalem</th>
                <th>Malzeme</th>
                <th>Spec</th>
                <th>Uyum Özeti</th>
                <th>Tarih</th>
                <th style={{ textAlign: 'center' }}>İşlemler</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, index) => (
                <tr key={r.id}>
                  <td style={{ fontWeight: 700, textAlign: 'center' }}>{index + 1}</td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{r.po_number || r.po_info || '—'}</div>
                    {r.po_item && <div style={{ fontSize: 12, color: '#64748b' }}>Kalem {r.po_item}</div>}
                  </td>
                  <td title={r.material || ''} style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {r.material || '—'}
                  </td>
                  <td title={r.spec_file || ''} style={{ fontWeight: 500 }}>
                    {r.spec_no || r.spec_file || '—'}
                  </td>
                  <td><ComplianceChips summary={r.summary} total={r.total_findings} /></td>
                  <td style={{ fontSize: 12, color: '#475569', whiteSpace: 'nowrap' }}>{r.timestamp || '—'}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center', justifyContent: 'center', flexWrap: 'wrap' }}>
                      <Link to={`/report/${encodeURIComponent(r.id)}`}>
                        <button className="button" style={btn('#6366f1')}>Detay</button>
                      </Link>
                      {r.spec_pdf_path && (
                        <button className="button" style={btn('#3b82f6')}
                          onClick={() => window.open(`${API_BASE_URL}${r.spec_pdf_path}`, '_blank')}>Spec</button>
                      )}
                      {r.vendor_pdf_path && (
                        <button className="button" style={btn('#10b981')}
                          onClick={() => window.open(`${API_BASE_URL}${r.vendor_pdf_path}`, '_blank')}>Vendor</button>
                      )}
                      <button className="button" style={btn('#f59e0b')}
                        onClick={() => handleRename(r.id, r.po_info || r.display_name)}>Ad</button>
                      <button className="button" style={btn('#ef4444')}
                        onClick={() => handleDelete(r.id)}>Sil</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        !loading && <div className="empty-state">Henüz karşılaştırma sonucu yok.</div>
      )}
    </div>
  )
}
