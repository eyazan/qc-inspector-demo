import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getComparisonResults, apiClient } from '../services/api'
import { API_BASE_URL } from '../config'

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

  useEffect(() => {
    fetchResults()
  }, [])

  const handleDelete = async (reportId) => {
    if (!window.confirm('Bu karşılaştırma sonucunu silmek istediğinizden emin misiniz?')) {
      return
    }
    try {
      await apiClient.delete(`/api/comparison-results/${encodeURIComponent(reportId)}`)
      window.location.reload()
    } catch (err) {
      alert('Silme işlemi başarısız: ' + (err.detail || err.message || 'Bilinmeyen hata'))
    }
  }

  const handleRename = async (reportId, currentDisplayName) => {
    const newName = prompt('İşlem adını yeniden adlandırın (şu an: ' + currentDisplayName + '):', currentDisplayName)
    if (!newName || !newName.trim()) {
      return
    }
    try {
      await apiClient.post(`/api/comparison-results/${encodeURIComponent(reportId)}/rename`, { new_name: newName.trim() })
      fetchResults()
    } catch (err) {
      alert('Yeniden adlandırma başarısız: ' + (err.detail || err.message || 'Bilinmeyen hata'))
    }
  }

  return (
    <div className="form-container">
      <h1 className="page-title">Karşılaştırma Sonuçları</h1>

      {loading && <div className="loading">Yükleniyor...</div>}
      {error && <div className="error">{error}</div>}

      {results && results.length > 0 ? (
        <div className="table-responsive">
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Vendor Adı</th>
                <th>Spec Adı</th>
                <th>İşlem Adı</th>
                <th>Tarih / Saat</th>
                <th>İşlemler</th>
              </tr>
            </thead>
            <tbody>
              {results.filter(result => result.type === 'final_aggregation').map((result, index) => (
                 <tr key={result.id} style={{ backgroundColor: '#fff3cd' }}>
                   <td style={{ fontWeight: 'bold', textAlign: 'center' }}>{index + 1}</td>
                   <td title={result.vendor_file || 'Tüm Belgeler'} style={{ maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{(result.vendor_file || 'Tüm Belgeler').length > 30 ? (result.vendor_file || 'Tüm Belgeler').substring(0, 30) + '...' : (result.vendor_file || 'Tüm Belgeler')}</td>
                   <td title={result.spec_file || 'Final Master Report'} style={{ maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{(result.spec_file || 'Final Master Report').length > 30 ? (result.spec_file || 'Final Master Report').substring(0, 30) + '...' : (result.spec_file || 'Final Master Report')}</td>
                   <td style={{ fontWeight: 'bold' }}>{result.po_info || result.display_name || '-'}</td>
                   <td style={{ textAlign: 'center', fontSize: '0.9em' }}>{result.timestamp || '-'}</td>
                   <td>
                     <div style={{ display: 'flex', gap: '6px', alignItems: 'center', justifyContent: 'center' }}>
                       <Link to={`/report/${encodeURIComponent(result.id)}`}>
                         <button
                           className="button"
                           style={{
                             cursor: 'pointer',
                             fontSize: '13px',
                             padding: '7px 11px',
                             whiteSpace: 'nowrap',
                             backgroundColor: '#6366f1',
                             borderColor: '#6366f1',
                             color: '#fff',
                             borderRadius: '5px',
                             fontWeight: '500'
                           }}
                         >
                           Detayları Görüntüle
                         </button>
                       </Link>
                       {result.spec_pdf_path && (
                         <button
                           className="button"
                           onClick={() => window.open(`${API_BASE_URL}${result.spec_pdf_path}`, '_blank')}
                           style={{
                             cursor: 'pointer',
                             fontSize: '13px',
                             padding: '7px 11px',
                             whiteSpace: 'nowrap',
                             backgroundColor: '#3b82f6',
                             borderColor: '#3b82f6',
                             color: '#fff',
                             borderRadius: '5px',
                             fontWeight: '500'
                           }}
                         >
                           Spec Görüntüle
                         </button>
                       )}
                       {result.vendor_pdf_path && (
                         <button
                           className="button"
                           onClick={() => window.open(`${API_BASE_URL}${result.vendor_pdf_path}`, '_blank')}
                           style={{
                             cursor: 'pointer',
                             fontSize: '13px',
                             padding: '7px 11px',
                             whiteSpace: 'nowrap',
                             backgroundColor: '#10b981',
                             borderColor: '#10b981',
                             color: '#fff',
                             borderRadius: '5px',
                             fontWeight: '500'
                           }}
                         >
                           Vendor Görüntüle
                         </button>
                       )}
                       <button
                         className="button"
                         onClick={() => handleRename(result.id, result.po_info || result.display_name || '-')}
                         style={{
                           cursor: 'pointer',
                           fontSize: '13px',
                           padding: '7px 11px',
                           whiteSpace: 'nowrap',
                           backgroundColor: '#f59e0b',
                           borderColor: '#f59e0b',
                           color: '#fff',
                           borderRadius: '5px',
                           fontWeight: '500'
                         }}
                       >
                         Yeniden Adlandır
                       </button>
                       <button
                         className="button"
                         onClick={() => handleDelete(result.id)}
                         style={{
                           cursor: 'pointer',
                           fontSize: '13px',
                           padding: '7px 11px',
                           whiteSpace: 'nowrap',
                           backgroundColor: '#ef4444',
                           borderColor: '#ef4444',
                           color: '#fff',
                           borderRadius: '5px',
                           fontWeight: '500'
                         }}
                       >
                         Sil
                       </button>
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