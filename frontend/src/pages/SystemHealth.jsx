import React, { useState, useEffect } from 'react'
import { getSystemConfig, getReadiness, getMetrics } from '../services/api'

function Card({ title, children }) {
  return (
    <div style={{
      border: '1px solid #e2e8f0', borderRadius: '8px', padding: '16px',
      marginBottom: '16px', backgroundColor: '#fff',
    }}>
      <h3 style={{ marginTop: 0, marginBottom: '12px', fontSize: '16px' }}>{title}</h3>
      {children}
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid #f1f5f9', fontSize: '14px' }}>
      <span style={{ color: '#64748b' }}>{label}</span>
      <span style={{ fontWeight: 500, textAlign: 'right', wordBreak: 'break-all' }}>{value ?? '-'}</span>
    </div>
  )
}

function Dot({ ok }) {
  return <span style={{
    display: 'inline-block', width: 10, height: 10, borderRadius: '50%',
    backgroundColor: ok ? '#10b981' : '#ef4444', marginRight: 6,
  }} />
}

export default function SystemHealth() {
  const [config, setConfig] = useState(null)
  const [ready, setReady] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetchAll = async () => {
    setLoading(true)
    try {
      const [c, r, m] = await Promise.allSettled([getSystemConfig(), getReadiness(), getMetrics()])
      if (c.status === 'fulfilled') setConfig(c.value)
      if (r.status === 'fulfilled') setReady(r.value)
      if (m.status === 'fulfilled') setMetrics(m.value)
      if (c.status === 'rejected' && r.status === 'rejected') {
        setError('Backend\'e ulaşılamıyor')
      } else {
        setError(null)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchAll() }, [])

  return (
    <div className="form-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="page-title" style={{ marginBottom: 0 }}>Sistem Sağlığı</h1>
        <button className="button" onClick={fetchAll}
          style={{ backgroundColor: '#64748b', borderColor: '#64748b', color: '#fff', borderRadius: '5px' }}>
          Yenile
        </button>
      </div>

      {loading && <div className="loading">Yükleniyor...</div>}
      {error && <div className="error">{error}</div>}

      {ready && (
        <Card title={`Servis Erişilebilirliği — ${ready.status === 'ready' ? 'HAZIR' : 'KISITLI (degraded)'}`}>
          {Object.entries(ready.checks || {}).map(([name, c]) => (
            <div key={name} style={{ padding: '6px 0', borderBottom: '1px solid #f1f5f9', fontSize: '14px' }}>
              <Dot ok={name === 'layout' ? true : !!c.reachable} />
              <strong style={{ textTransform: 'uppercase' }}>{name}</strong>
              {' '}— {c.provider}
              {c.local && <span style={{ color: '#64748b' }}> (lokal)</span>}
              {c.url && <div style={{ color: '#64748b', fontSize: '12px', marginLeft: 16 }}>{c.url} {c.status ? `· HTTP ${c.status}` : c.error ? `· ${c.error}` : ''}</div>}
            </div>
          ))}
        </Card>
      )}

      {config && (
        <>
          <Card title="Ortam">
            <Row label="Uygulama" value={`${config.app?.name} v${config.app?.version}`} />
            <Row label="Environment" value={config.environment} />
          </Card>

          <Card title="Sağlayıcılar (Providers)">
            <Row label="Layout (lokal)" value={config.providers?.layout} />
            <Row label="OCR (remote)" value={config.providers?.ocr} />
            <Row label="LLM (remote)" value={config.providers?.llm} />
            <Row label="SAP" value={config.providers?.sap} />
            <Row label="Spec store" value={config.providers?.spec_store} />
          </Card>

          <Card title="Uç Noktalar (Endpoints)">
            <Row label="OCR base URL" value={config.endpoints?.ocr_base_url} />
            <Row label="LLM base URL" value={config.endpoints?.llm_base_url} />
            <Row label="SAP endpoint" value={config.endpoints?.sap_spec_endpoint} />
          </Card>

          <Card title="Spec İndeksleme">
            <Row label="Ağ yolu" value={config.spec_indexing?.network_root} />
            <Row label="Store DB" value={config.spec_indexing?.store_db} />
            <Row label="Zamanlama (cron)" value={config.spec_indexing?.schedule} />
            <Row label="Varsayılan mod" value={config.spec_indexing?.default_mode} />
          </Card>

          <Card title="Performans">
            <Row label="Sayfa paralelliği" value={String(config.performance?.page_parallelism)} />
            <Row label="OCR batch boyutu" value={config.performance?.ocr_batch_size} />
            <Row label="OCR max workers" value={config.performance?.ocr_max_workers} />
          </Card>
        </>
      )}

      {metrics && (
        <Card title="Metrikler">
          {Object.entries(metrics).map(([k, v]) => (
            <Row key={k} label={k} value={typeof v === 'object' ? JSON.stringify(v) : String(v)} />
          ))}
        </Card>
      )}
    </div>
  )
}
