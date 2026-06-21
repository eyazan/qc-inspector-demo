import React, { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import Home from './pages/Home'
// import SpecQuery from './pages/SpecQuery'
import PdfUpload from './pages/PdfUpload'
import ComparisonResults from './pages/ComparisonResults'
import InspectorReport from './pages/InspectorReport'
import Navbar from './components/Navbar'
import ComparisonPreview from './pages/ComparisonPreview'
import SpecIndex from './pages/SpecIndex'
import SystemHealth from './pages/SystemHealth'

const SESSION_STORAGE_KEYS = {
  VENDOR_FILES: 'ocr_vendor_files',
  SPEC_FILES: 'ocr_spec_files',
  PROCESSING_STATUS: 'ocr_processing_status',
  SUMMARY: 'ocr_summary'
}

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

function GlobalNavigation() {
  const navigate = useNavigate()
  const location = useLocation()
  const [showDetailsModal, setShowDetailsModal] = useState(false)

  const handleBack = () => {
    navigate('/')
  }

  const handleForward = () => {
    navigate('/pdf-upload')
  }

  const handleDetailsClick = () => {
    setShowDetailsModal(true)
  }

  const isUploadPage = location.pathname === '/pdf-upload'
  const hasSavedState = safeParse(sessionStorage.getItem(SESSION_STORAGE_KEYS.VENDOR_FILES), []).length > 0 ||
                        safeParse(sessionStorage.getItem(SESSION_STORAGE_KEYS.SPEC_FILES), []).length > 0

  const getDetailsContent = () => {
    const vendorFiles = safeParse(sessionStorage.getItem(SESSION_STORAGE_KEYS.VENDOR_FILES), [])
    const specFiles = safeParse(sessionStorage.getItem(SESSION_STORAGE_KEYS.SPEC_FILES), [])
    const summary = safeParse(sessionStorage.getItem(SESSION_STORAGE_KEYS.SUMMARY), null)
    const processingStatus = safeParse(sessionStorage.getItem(SESSION_STORAGE_KEYS.PROCESSING_STATUS), {
      is_processing: false,
      current_step: '',
      progress: 0,
      logs: []
    })

    return (
      <div className="details-content">
        <h3>Yükleme Detayları</h3>
        <div className="details-grid">
          <div className="detail-item">
            <span className="detail-label">Vendor PDF Sayısı:</span>
            <span className="detail-value">{vendorFiles.length}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Spec PDF Sayısı:</span>
            <span className="detail-value">{specFiles.length}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">İşlem Durumu:</span>
            <span className={`detail-value ${processingStatus.is_processing ? 'processing' : 'completed'}`}>
              {processingStatus.is_processing ? 'İşleniyor' : 'Tamamlandı'}
            </span>
          </div>
          {processingStatus.is_processing && (
            <>
              <div className="detail-item">
                <span className="detail-label">Mevcut Adım:</span>
                <span className="detail-value">{processingStatus.current_step || 'Başlatılıyor...'}</span>
              </div>
              <div className="detail-item full-width">
                <span className="detail-label">İlerleme:</span>
                <div className="progress-bar-container">
                  <div className="progress-bar" style={{ width: `${processingStatus.progress}%` }} />
                </div>
              </div>
            </>
          )}
          <div className="detail-item">
            <span className="detail-label">Rapor Oluşturuldu:</span>
            <span className={`detail-value ${summary ? 'success' : 'pending'}`}>
              {summary ? 'Evet' : 'Hayır'}
            </span>
          </div>
        </div>
        {processingStatus.logs && processingStatus.logs.length > 0 && (
          <div className="details-logs">
            <h4>İşlem Logları</h4>
            <div className="log-list">
              {processingStatus.logs.map((log, index) => (
                <div key={index} className="log-item">{log}</div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <>
      <div className="global-navigation">
        <div className="nav-buttons">
          <button onClick={handleBack} className="nav-button back-button" title="Geri">
            ← Geri
          </button>
          <button
            onClick={handleForward}
            className="nav-button forward-button"
          >
            İleri →
          </button>
        </div>
      </div>

      {showDetailsModal && (
        <div className="modal-overlay" onClick={() => setShowDetailsModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setShowDetailsModal(false)}>×</button>
            {getDetailsContent()}
          </div>
        </div>
      )}
    </>
  )
}

function App() {
  return (
    <Router>
      <Navbar />
      <GlobalNavigation />
      <div className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/pdf-upload" element={<PdfUpload />} />
          <Route path="/comparison-preview/:runId" element={<ComparisonPreview />} />
          <Route path="/comparison-results" element={<ComparisonResults />} />
          <Route path="/report/:id" element={<InspectorReport />} />
          <Route path="/report/:id/segments" element={<InspectorReport />} />
          <Route path="/spec-index" element={<SpecIndex />} />
          <Route path="/system-health" element={<SystemHealth />} />
        </Routes>
      </div>
    </Router>
  )
}

export default App