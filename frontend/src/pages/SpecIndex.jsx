import React, { useState, useEffect, useRef } from 'react'
import {
  listIndexedSpecs,
  searchIndexedSpecs,
  runSpecIndex,
  getSpecIndexStatus,
} from '../services/api'

export default function SpecIndex() {
  const [specs, setSpecs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState(null)

  const [mode, setMode] = useState('incremental')
  const [job, setJob] = useState(null)
  const [running, setRunning] = useState(false)
  const pollRef = useRef(null)

  const fetchSpecs = async () => {
    setLoading(true)
    try {
      const data = await listIndexedSpecs()
      setSpecs(data.results || [])
      setError(null)
    } catch (err) {
      setError(err.detail || err.message || 'Spec listesi yüklenemedi')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSpecs()
    return () => pollRef.current && clearInterval(pollRef.current)
  }, [])

  const handleSearch = async (e) => {
    e.preventDefault()
    if (!query.trim()) {
      setSearchResults(null)
      return
    }
    try {
      const data = await searchIndexedSpecs(query.trim())
      setSearchResults(data.results || [])
    } catch (err) {
      setError(err.detail || err.message || 'Arama başarısız')
    }
  }

  const pollJob = (runId) => {
    pollRef.current && clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const j = await getSpecIndexStatus(runId)
        setJob(j)
        if (['completed', 'failed', 'dead_letter'].includes(j.status)) {
          clearInterval(pollRef.current)
          setRunning(false)
          fetchSpecs()
        }
      } catch (err) {
        clearInterval(pollRef.current)
        setRunning(false)
      }
    }, 2000)
  }

  const handleRun = async () => {
    setRunning(true)
    setJob(null)
    setError(null)
    try {
      const res = await runSpecIndex(mode)
      setJob(res.job || { id: res.run_id, status: 'queued' })
      pollJob(res.run_id)
    } catch (err) {
      setRunning(false)
      setError(err.detail || err.message || 'İndeksleme başlatılamadı')
    }
  }

  const statusBadge = (status) => {
    const color = status === 'indexed' || status === 'completed' ? '#10b981'
      : status === 'failed' || status === 'dead_letter' ? '#ef4444'
      : '#f59e0b'
    return (
      <span style={{
        backgroundColor: color, color: '#fff', padding: '2px 8px',
        borderRadius: '4px', fontSize: '12px', fontWeight: 500,
      }}>{status}</span>
    )
  }

  const rows = searchResults !== null ? searchResults : specs

  return (
    <div className="form-container">
      <h1 className="page-title">Spec İndeksleme</h1>

      {/* Run indexing */}
      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '18px', flexWrap: 'wrap' }}>
        <label style={{ fontWeight: 500 }}>Mod:</label>
        <select value={mode} onChange={(e) => setMode(e.target.value)} disabled={running}
          style={{ padding: '7px 10px', borderRadius: '5px' }}>
          <option value="incremental">incremental (değişenleri indeksle)</option>
          <option value="full">full (tümünü yeniden indeksle)</option>
        </select>
        <button className="button" onClick={handleRun} disabled={running}
          style={{ backgroundColor: '#6366f1', borderColor: '#6366f1', color: '#fff', borderRadius: '5px' }}>
          {running ? 'İndeksleniyor…' : 'İndekslemeyi Başlat'}
        </button>
        <button className="button" onClick={fetchSpecs}
          style={{ backgroundColor: '#64748b', borderColor: '#64748b', color: '#fff', borderRadius: '5px' }}>
          Yenile
        </button>
      </div>

      {job && (
        <div style={{
          marginBottom: '18px', padding: '12px 14px', borderRadius: '6px',
          backgroundColor: '#f1f5f9', border: '1px solid #e2e8f0',
        }}>
          <strong>İş:</strong> {job.id} &nbsp; {statusBadge(job.status)}
          {job.result && (
            <div style={{ marginTop: '6px', fontSize: '13px' }}>
              İndekslenen: {job.result.indexed ?? '-'} · Atlanan: {job.result.skipped ?? '-'} · Hata: {job.result.failed ?? '-'}
            </div>
          )}
          {job.error && <div style={{ marginTop: '6px', color: '#ef4444', fontSize: '13px' }}>{job.error}</div>}
        </div>
      )}

      {/* Search */}
      <form onSubmit={handleSearch} style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        <input
          type="text" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Spec ara (örn. AMS4911)…"
          style={{ flex: 1, padding: '8px 10px', borderRadius: '5px', border: '1px solid #cbd5e1' }}
        />
        <button className="button" type="submit"
          style={{ backgroundColor: '#3b82f6', borderColor: '#3b82f6', color: '#fff', borderRadius: '5px' }}>
          Ara
        </button>
        {searchResults !== null && (
          <button className="button" type="button" onClick={() => { setSearchResults(null); setQuery('') }}
            style={{ backgroundColor: '#64748b', borderColor: '#64748b', color: '#fff', borderRadius: '5px' }}>
            Temizle
          </button>
        )}
      </form>

      {loading && <div className="loading">Yükleniyor...</div>}
      {error && <div className="error">{error}</div>}

      {rows && rows.length > 0 ? (
        <div className="table-responsive">
          <table className="table">
            <thead>
              <tr>
                <th>Spec No</th>
                <th>Revizyon</th>
                <th>Durum</th>
                <th>Dosya</th>
                <th>Hash</th>
                <th>İndekslenme</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id ?? s.spec_no}>
                  <td style={{ fontWeight: 'bold' }}>{s.spec_no}</td>
                  <td>{s.revision || '-'}</td>
                  <td>{statusBadge(s.status || 'indexed')}</td>
                  <td title={s.file_path} style={{ maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.file_path || '-'}
                  </td>
                  <td style={{ fontFamily: 'monospace', fontSize: '12px' }}>{s.content_hash || '-'}</td>
                  <td style={{ fontSize: '12px' }}>{s.indexed_at ? new Date(s.indexed_at).toLocaleString('tr-TR') : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        !loading && <div className="empty-state">
          {searchResults !== null ? 'Arama sonucu yok.' : 'Henüz indekslenmiş spec yok. İndekslemeyi başlatın.'}
        </div>
      )}
    </div>
  )
}
