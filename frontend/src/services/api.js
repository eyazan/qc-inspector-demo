import axios from 'axios'
import { API_BASE_URL } from '../config'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
})

const api = apiClient

// ----- Spec sorgu -----
export const querySpec = async (poNumber, poItem, material) => {
  try {
    const response = await api.post('/api/query', {
      po_number: poNumber,
      po_item: poItem,
      material: material,
    })
    return response.data
  } catch (error) {
    throw error.response?.data || error.message
  }
}

// ----- Upload -----
export const uploadPdf = async (file, isSpec = false) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('is_spec', isSpec)
  try {
    const response = await api.post('/api/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  } catch (error) {
    throw error.response?.data || error.message
  }
}

// ----- Pipeline -----
export const startFullPipeline = async (payload = {}) => {
  try {
    const response = await api.post('/api/start-full-pipeline', {
      po_number: payload.poNumber || '',
      po_item: payload.poItem || '',
      material: payload.material || '',
      inspector_id: payload.inspectorId || '',
    })
    return response.data
  } catch (error) {
    throw error.response?.data || error.message
  }
}

export const getProcessingStatus = async (runId) => {
  try {
    const response = await api.get(`/api/processing-status/${encodeURIComponent(runId)}`)
    return response.data
  } catch (error) {
    throw error.response?.data || error.message
  }
}

export const cancelProcessing = async (runId) => {
  try {
    const response = await api.post(`/api/cancel-processing/${encodeURIComponent(runId)}`)
    return response.data
  } catch (error) {
    throw error.response?.data || error.message
  }
}

// ----- Sonuçlar / Rapor -----
export const getComparisonResults = async () => {
  try {
    const response = await api.get('/api/comparison-results')
    return response.data
  } catch (error) {
    throw error.response?.data || error.message
  }
}

export const getAllReports = getComparisonResults

export const getReport = async (id) => {
  try {
    const response = await api.get(`/api/report/${encodeURIComponent(id)}`)
    return response.data
  } catch (error) {
    throw error.response?.data || error.message
  }
}

export const getReviewRegions = async (id) => {
  try {
    const response = await api.get(`/api/report/${encodeURIComponent(id)}/review-regions`)
    return response.data
  } catch (error) {
    throw error.response?.data || error.message
  }
}

export const reportPdfUrl = (id) =>
  `${API_BASE_URL}/api/report/${encodeURIComponent(id)}/pdf`

// ----- Override -----
export const overrideFinding = async (findingId, payload) => {
  try {
    const response = await api.post(
      `/api/findings/${findingId}/override`,
      {
        action: payload.action,
        new_status: payload.newStatus || null,
        new_value: payload.newValue || null,
        note: payload.note || null,
        inspector_id: payload.inspectorId || null,
      }
    )
    return response.data
  } catch (error) {
    throw error.response?.data || error.message
  }
}

// ----- Yönetim -----
export const renameResult = async (id, newName) => {
  try {
    const response = await api.post(
      `/api/comparison-results/${encodeURIComponent(id)}/rename`,
      { new_name: newName }
    )
    return response.data
  } catch (error) {
    throw error.response?.data || error.message
  }
}

export const deleteResult = async (id) => {
  try {
    const response = await api.delete(`/api/comparison-results/${encodeURIComponent(id)}`)
    return response.data
  } catch (error) {
    throw error.response?.data || error.message
  }
}

export const healthCheck = async () => {
  try {
    const response = await api.get('/health')
    return response.data
  } catch (error) {
    throw error.response?.data || error.message
  }
}

export default api
