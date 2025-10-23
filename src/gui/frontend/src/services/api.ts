import axios, { AxiosInstance } from 'axios'

const API_BASE_URL = '/api'

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Config API
export const configApi = {
  getScilex: () => apiClient.get('/config/scilex'),
  updateScilex: (config: any) => apiClient.put('/config/scilex', config),

  getApi: () => apiClient.get('/config/api'),
  updateApi: (config: any) => apiClient.put('/config/api', config),

  checkExists: () => apiClient.get('/config/exists'),
  testConnection: (apiName: string) => apiClient.post(`/config/test/${apiName}`),
}

// Jobs API
export const jobsApi = {
  startJob: (jobData: any) => apiClient.post('/jobs/start', jobData),
  listJobs: (params?: any) => apiClient.get('/jobs', { params }),
  getJob: (jobId: string) => apiClient.get(`/jobs/${jobId}`),
  cancelJob: (jobId: string) => apiClient.post(`/jobs/${jobId}/cancel`),
  deleteJob: (jobId: string) => apiClient.delete(`/jobs/${jobId}`),
}

// Results API
export const resultsApi = {
  getPapers: (jobId: string, params?: any) =>
    apiClient.get(`/results/${jobId}/papers`, { params }),
  exportResults: (jobId: string, params?: any) =>
    apiClient.get(`/results/${jobId}/export`, { params }),
  getStatistics: (jobId: string) =>
    apiClient.get(`/results/${jobId}/statistics`),
}

// Health check
export const healthApi = {
  check: () => apiClient.get('/health'),
}

// WebSocket connection
export const connectWebSocket = (jobId: string, onMessage: (data: any) => void) => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/ws/${jobId}`

  const ws = new WebSocket(wsUrl)

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      onMessage(data)
    } catch (e) {
      console.error('Failed to parse WebSocket message:', e)
    }
  }

  return ws
}

export default apiClient
