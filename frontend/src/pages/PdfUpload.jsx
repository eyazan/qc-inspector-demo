import React, { useState, useCallback, useEffect, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorAlert from '../components/ErrorAlert'
import { API_BASE_URL } from '../config'

const POLLING_INTERVAL_MS = 3000
const RUN_ID_KEY = 'ocr_run_id'
const SESSION_STORAGE_KEYS = {
  VENDOR_FILES: 'ocr_vendor_files',
  PROCESSING_STATUS: 'ocr_processing_status',
  SUMMARY: 'ocr_summary'
}

// Vendor yukleme talimatlari (sonra duzenlenebilir)
const UPLOAD_RULES = [
  'Sadece vendor dokümanı yükleyin (Spec SAP\u2019tan otomatik gelir)',
  'PDF taranmış veya dijital olabilir',
  'İlk sayfada PO numarası ve kalem bilgisi okunabilir olmalı',
  '5\u201330 sayfa arası dokümanlar desteklenir',
  'Tek seferde 1 adet vendor dokümanı yüklenebilir.'
]

const safeParse = (str, defaultValue) => {
  if (!str || str === 'undefined' || str === 'null') {
    return defaultValue
  }
  try {
    return JSON.parse(str)
  } catch (e) {
    return defaultValue
  }
}

const PdfUpload = () => {
  const navigate = useNavigate()

  const [vendorFiles, setVendorFiles] = useState([])
  const [runId, setRunId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [summary, setSummary] = useState(null)
  const [elapsedTime, setElapsedTime] = useState(0)
  const [startTime, setStartTime] = useState(null)
  const [endTime, setEndTime] = useState(null)
  const timerIntervalRef = useRef(null)
  const checkIntervalRef = useRef(null)
  const [resumeRun, setResumeRun] = useState(null) // {runId, target} paused/finished run to return to
  const [processingStatus, setProcessingStatus] = useState({
    is_processing: false,
    current_step: '',
    progress: 0,
    logs: [],
    start_time: null,
    elapsed_seconds: 0
  })

  const saveVendorFilesMetadata = (files) => {
    const filesArray = Array.isArray(files) ? files : (files ? [files] : [])
    const metadata = filesArray.map(f => ({ name: f.name, size: f.size, type: f.type }))
    sessionStorage.setItem(SESSION_STORAGE_KEYS.VENDOR_FILES, JSON.stringify(metadata))
  }

  useEffect(() => {
    const restoredSummary = safeParse(sessionStorage.getItem(SESSION_STORAGE_KEYS.SUMMARY), null)
    const restoredProcessingStatus = safeParse(sessionStorage.getItem(SESSION_STORAGE_KEYS.PROCESSING_STATUS), {
      is_processing: false,
      current_step: '',
      progress: 0,
      logs: [],
      start_time: null,
      elapsed_seconds: 0
    })
    if (restoredSummary) setSummary(restoredSummary)
    setProcessingStatus(restoredProcessingStatus)
  }, [])

  // Resume on mount: if a run is still in progress on the server, re-attach the
  // poller and show live progress (continue where you left off). If it already
  // moved on (paused for preview / completed), surface a "return" banner instead
  // of hijacking navigation.
  useEffect(() => {
    const rid = sessionStorage.getItem(RUN_ID_KEY)
    if (!rid) return
    let cancelled = false
    ;(async () => {
      try {
        const { data: status } = await axios.get(
          `${API_BASE_URL}/api/processing-status/${encodeURIComponent(rid)}`
        )
        if (cancelled) return
        if (status.is_processing) {
          setRunId(rid)
          saveProcessingStatus(status)
          setStartTime(status.start_time ? new Date(status.start_time) : new Date())
          setElapsedTime(status.elapsed_seconds || 0)
          if (!timerIntervalRef.current) {
            timerIntervalRef.current = setInterval(() => setElapsedTime((p) => p + 1), 1000)
          }
          beginPolling(rid)
        } else if (status.status === 'awaiting_comparison') {
          setResumeRun({ runId: rid, target: `/comparison-preview/${encodeURIComponent(rid)}`, label: 'Önizlemeye dön' })
        } else if (status.status === 'completed') {
          setResumeRun({ runId: rid, target: `/report/${encodeURIComponent(rid)}`, label: 'Raporu gör' })
        } else {
          sessionStorage.removeItem(RUN_ID_KEY) // idle/failed/unknown -> stale
        }
      } catch (err) {
        /* server unreachable / unknown run -> ignore */
      }
    })()
    return () => { cancelled = true }
  }, [])

  const saveVendorFiles = (files) => {
    setVendorFiles(files)
    saveVendorFilesMetadata(Array.isArray(files) ? files : [])
  }

  const saveProcessingStatus = (status) => {
    setProcessingStatus(status)
    sessionStorage.setItem(SESSION_STORAGE_KEYS.PROCESSING_STATUS, JSON.stringify(status))
  }

  const saveSummary = (sum) => {
    setSummary(sum)
    sessionStorage.setItem(SESSION_STORAGE_KEYS.SUMMARY, JSON.stringify(sum))
  }

  const saveRunId = (id) => {
    setRunId(id)
    sessionStorage.setItem(RUN_ID_KEY, id)
  }

  // Resumable Stage-1 poller: re-attaches to a run by id (used on first start
  // AND when returning to the page mid-process). On completion it routes to the
  // preview screen, exactly like the original inline flow.
  const beginPolling = (rid) => {
    if (checkIntervalRef.current) clearInterval(checkIntervalRef.current)
    const pollStatus = async () => {
      try {
        const { data: status } = await axios.get(
          `${API_BASE_URL}/api/processing-status/${encodeURIComponent(rid)}`
        )
        saveProcessingStatus(status)
        if (!status.is_processing) {
          if (timerIntervalRef.current) { clearInterval(timerIntervalRef.current); timerIntervalRef.current = null }
          if (checkIntervalRef.current) { clearInterval(checkIntervalRef.current); checkIntervalRef.current = null }
          setEndTime(status.end_time ? new Date(status.end_time) : new Date())
          if (status.status === 'failed') {
            setError('Yükleme sırasında hata oluştu. Loglara bakın.')
          } else {
            sessionStorage.removeItem(RUN_ID_KEY) // preview screen owns the run now
            navigate(`/comparison-preview/${encodeURIComponent(rid)}`)
          }
        }
      } catch (err) {
        console.error('Status poll error:', err)
      }
    }
    pollStatus()
    checkIntervalRef.current = setInterval(pollStatus, POLLING_INTERVAL_MS)
  }

  const onDrop = useCallback((acceptedFiles) => {
    setVendorFiles(prev => {
      const next = [...prev, ...acceptedFiles]
      saveVendorFilesMetadata(next)
      return next
    })
    setError(null)
  }, [])

  const removeFile = (index) => {
    setVendorFiles(prev => {
      const next = prev.filter((_, i) => i !== index)
      saveVendorFilesMetadata(next)
      return next
    })
  }

  const handleClear = async () => {
    saveVendorFiles([])
    saveSummary(null)
    saveProcessingStatus({
      is_processing: false,
      current_step: '',
      progress: 0,
      logs: [],
      start_time: null,
      elapsed_seconds: 0
    })
    setElapsedTime(0)
    setError(null)

    if (processingStatus.is_processing) {
      try {
        await axios.post(`${API_BASE_URL}/api/cancel-processing`)
      } catch (err) {
        console.error('Failed to cancel processing:', err)
      }
    }

    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current)
      timerIntervalRef.current = null
    }
    if (checkIntervalRef.current) {
      clearInterval(checkIntervalRef.current)
      checkIntervalRef.current = null
    }
    setStartTime(null)
    setEndTime(null)
    sessionStorage.removeItem(SESSION_STORAGE_KEYS.VENDOR_FILES)
    sessionStorage.removeItem(SESSION_STORAGE_KEYS.SUMMARY)
    sessionStorage.removeItem(SESSION_STORAGE_KEYS.PROCESSING_STATUS)
    sessionStorage.removeItem(RUN_ID_KEY)
    setResumeRun(null)
  }

  const handleUpload = async () => {
    if (vendorFiles.length === 0) {
      setError('Lütfen en az bir vendor PDF dosyası yükleyin.')
      return
    }

    setLoading(true)
    setError(null)
    saveSummary(null)
    const now = new Date()
    setStartTime(now)
    setEndTime(null)
    setElapsedTime(0)

    saveProcessingStatus({
      is_processing: true,
      current_step: 'Yükleme başlatılıyor...',
      progress: 0,
      logs: [],
      start_time: now.toISOString(),
      elapsed_seconds: 0
    })

    const interval = setInterval(() => {
      setElapsedTime(prev => prev + 1)
    }, 1000)
    timerIntervalRef.current = interval

    try {
      for (const file of vendorFiles) {
        const formData = new FormData()
        formData.append('file', file)
        formData.append('is_spec', 'false')
        await axios.post(`${API_BASE_URL}/api/upload`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        })
      }

      saveVendorFiles([])
      let newRunId = null
      try {
        const startResp = await axios.post(`${API_BASE_URL}/api/start-full-pipeline`, {
          po_number: '',
          po_item: '',
          material: '',
          inspector_id: '',
        })
        newRunId = startResp.data?.run_id
        if (startResp.data?.status === 'rejected' || !newRunId) {
          setError(startResp.data?.message || 'İşlem başlatılamadı.')
          setLoading(false)
          return
        }
        saveRunId(newRunId)
      } catch (err) {
        console.error('Full pipeline start failed:', err)
        setError('İşlem başlatılamadı.')
        setLoading(false)
        return
      }

      // Asama 1'i takip et; bitince onizleme ekranina yonlendir. Baska sayfaya
      // gidip donulse bile mount'taki resume efekti bu polling'i tekrar baslatir.
      beginPolling(newRunId)

    } catch (err) {
      const errorMessage = err.response?.data?.detail || err.message || 'Dosya yükleme sırasında bir hata oluştu.'
      setError(typeof errorMessage === 'string' ? errorMessage : JSON.stringify(errorMessage))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    return () => {
      if (checkIntervalRef.current) clearInterval(checkIntervalRef.current)
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current)
    }
  }, [])

  const formatElapsedTime = (seconds) => {
    const hrs = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    const secs = seconds % 60
    if (hrs > 0) {
      return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
    }
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  const formatTime = (date) => {
    if (!date) return '--:--:--'
    return date.toLocaleTimeString('tr-TR', { hour12: false })
  }

  const vendorDropzone = useDropzone({
    onDrop: (acceptedFiles) => onDrop(acceptedFiles),
    accept: undefined,
    maxSize: undefined,
    multiple: true
  })

  return (
    <div className="form-container">
      <h1 className="page-title">Vendor PDF Yükle</h1>
      <p className="page-subtitle">Vendor dokümanını yükleyin; Spec SAP’tan otomatik alınır.</p>

      {error && <ErrorAlert message={error} onClose={() => setError(null)} />}

      {resumeRun && !processingStatus.is_processing && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
          background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 10,
          padding: '12px 16px', marginBottom: 16, flexWrap: 'wrap',
        }}>
          <span style={{ color: '#1e40af', fontWeight: 500 }}>
            Devam eden bir işleminiz var ({resumeRun.runId}). Kaldığınız yerden devam edebilirsiniz.
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="button button-primary" onClick={() => navigate(resumeRun.target)}>
              {resumeRun.label}
            </button>
            <button className="button button-secondary" onClick={() => { sessionStorage.removeItem(RUN_ID_KEY); setResumeRun(null) }}>
              Yoksay
            </button>
          </div>
        </div>
      )}

      <div className="dropzone-container">
        <div className="dropzone">
          <h3>Vendor PDF'i</h3>
          <div {...vendorDropzone.getRootProps()} className="dropzone-area">
            <input {...vendorDropzone.getInputProps()} />
            <p>PDF'i buraya sürükleyin veya tıklayın</p>
          </div>
          <ul className="file-list">
            {vendorFiles.map((file, index) => (
              <li key={index} className="file-item">
                <span className="file-name">{file.name} ({Math.round(file.size / 1024)} KB)</span>
                <button onClick={() => removeFile(index)} className="file-remove">×</button>
              </li>
            ))}
          </ul>
        </div>

        <div className="dropzone rules-panel">
          <h3>Kurallar</h3>
          <ul className="rules-list">
            {UPLOAD_RULES.map((rule, index) => (
              <li key={index} className="rules-item">{rule}</li>
            ))}
          </ul>
        </div>
      </div>

      <div className="button-container">
        <button
          onClick={handleUpload}
          className="button button-primary"
          disabled={loading || processingStatus.is_processing}
        >
          {loading ? 'Yükleniyor...' : processingStatus.is_processing ? 'İşleniyor...' : 'Yükle'}
        </button>
        <button
          onClick={handleClear}
          className="button button-secondary"
          disabled={loading}
        >
          Temizle
        </button>
        {(processingStatus.is_processing || startTime) && (
          <div className="timer-display">
            <div className="timer-info">
              <span className="timer-label">Başlangıç:</span>
              <span className="timer-value-small">{formatTime(startTime)}</span>
            </div>
            <div className="timer-info">
              <span className="timer-label">Bitiş:</span>
              <span className="timer-value-small">{formatTime(endTime)}</span>
            </div>
            <div className="timer-separator">→</div>
            <div className="timer-info">
              <span className="timer-label">Süre:</span>
              <span className="timer-value">{formatElapsedTime(elapsedTime)}</span>
            </div>
          </div>
        )}
      </div>

      {processingStatus.is_processing && (
        <div className="processing-container">
          <LoadingSpinner />
          <div className="processing-content">
            <p className="processing-step">
              {processingStatus.current_step || 'İşlem başlatılıyor...'}
            </p>
            <div className="progress-bar-container">
              <div className="progress-bar" style={{ width: `${processingStatus.progress}%` }} />
            </div>
            <div className="processing-logs">
              {processingStatus.logs && processingStatus.logs.map((log, index) => (
                <div key={index} className="log-item">{log}</div>
              ))}
              {(!processingStatus.logs || processingStatus.logs.length === 0) && (
                <div className="log-empty">Log yükleniyor...</div>
              )}
            </div>
          </div>
        </div>
      )}

      {summary && (
        <div className="report-container">
          <h2>Karşılaştırma Özeti</h2>
          <pre>
            {typeof summary === 'string' ? summary : JSON.stringify(summary, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

export default PdfUpload
