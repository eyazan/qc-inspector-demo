import React, { useState } from 'react'
import { querySpec } from '../services/api'

const SESSION_STORAGE_KEYS = {
  PO_NUMBER: 'spec_po_number',
  PO_ITEM: 'spec_po_item',
  MATERIAL: 'spec_material',
  RESULTS: 'spec_results'
}

export default function SpecQuery() {
  const [poNumber, setPoNumber] = useState(() => {
    const saved = sessionStorage.getItem(SESSION_STORAGE_KEYS.PO_NUMBER)
    return saved || ''
  })
  const [poItem, setPoItem] = useState(() => {
    const saved = sessionStorage.getItem(SESSION_STORAGE_KEYS.PO_ITEM)
    return saved || ''
  })
  const [material, setMaterial] = useState(() => {
    const saved = sessionStorage.getItem(SESSION_STORAGE_KEYS.MATERIAL)
    return saved || ''
  })
  const [results, setResults] = useState(() => {
    const saved = sessionStorage.getItem(SESSION_STORAGE_KEYS.RESULTS)
    return saved ? JSON.parse(saved) : null
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const savePoNumber = (value) => {
    setPoNumber(value)
    sessionStorage.setItem(SESSION_STORAGE_KEYS.PO_NUMBER, value)
  }

  const savePoItem = (value) => {
    setPoItem(value)
    sessionStorage.setItem(SESSION_STORAGE_KEYS.PO_ITEM, value)
  }

  const saveMaterial = (value) => {
    setMaterial(value)
    sessionStorage.setItem(SESSION_STORAGE_KEYS.MATERIAL, value)
  }

  const saveResults = (data) => {
    setResults(data)
    sessionStorage.setItem(SESSION_STORAGE_KEYS.RESULTS, JSON.stringify(data))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      const data = await querySpec(poNumber, poItem, material)
      saveResults(data)
    } catch (err) {
      setError(err.detail || err.message || 'Bir hata oluştu')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="form-container">
      <h1 className="page-title">Spec Sorgula</h1>
      <form onSubmit={handleSubmit} className="form">
        <div className="form-group">
          <label htmlFor="poNumber">PO Numarası</label>
          <input
            id="poNumber"
            type="text"
            value={poNumber}
            onChange={(e) => savePoNumber(e.target.value)}
            placeholder="PO numarası girin"
          />
        </div>
        <div className="form-group">
          <label htmlFor="poItem">PO Item</label>
          <input
            id="poItem"
            type="text"
            value={poItem}
            onChange={(e) => savePoItem(e.target.value)}
            placeholder="PO item girin"
          />
        </div>
        <div className="form-group">
          <label htmlFor="material">Malzeme</label>
          <input
            id="material"
            type="text"
            value={material}
            onChange={(e) => saveMaterial(e.target.value)}
            placeholder="Malzeme kodu girin"
          />
        </div>
        <button type="submit" className="button" disabled={loading}>
          {loading ? 'Sorgulanıyor...' : 'Sorgula'}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {results && (
        <div className="report-container">
          <h2>Spec Sorgulama Sonuçları</h2>
          <button
            onClick={() => saveResults(null)}
            className="button"
            style={{ marginBottom: '10px' }}
          >
            Temizle
          </button>
          <p><strong>Durum:</strong> {results.status}</p>
          {results.header_lines && <p><strong>Başlık Satırları:</strong> {results.header_lines}</p>}
          {results.lines && results.lines.length > 0 ? (
            <div className="spec-results">
              {results.lines.map((line, index) => (
                <div key={index} className="spec-line">
                  {line.tdline}
                </div>
              ))}
            </div>
          ) : (
            <p>Sonuç bulunamadı.</p>
          )}
        </div>
      )}
    </div>
  )
}