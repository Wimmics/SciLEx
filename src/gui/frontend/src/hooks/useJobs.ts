import { useState, useEffect } from 'react'
import { message } from 'antd'
import { jobsApi } from '../services/api'

export interface Job {
  id: string
  name: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  created_at: string
  started_at?: string
  completed_at?: string
  duration_seconds?: number
  papers_found: number
  duplicates_removed?: number
  citations_fetched?: number
  error_message?: string
  output_directory?: string
  config_snapshot?: string
  logs?: Array<{
    timestamp: string
    level: string
    api?: string
    message: string
  }>
}

export const useJobs = () => {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selectedJob, setSelectedJob] = useState<Job | null>(null)
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)

  const loadJobs = async (status?: string, limit = 20, offset = 0) => {
    setLoading(true)
    try {
      const res = await jobsApi.listJobs({ status, limit, offset })
      setJobs(res.data.jobs)
      setTotal(res.data.total)
    } catch (error) {
      console.error('Failed to load jobs:', error)
      message.error('Failed to load job history')
    } finally {
      setLoading(false)
    }
  }

  const loadJobDetail = async (jobId: string) => {
    try {
      const res = await jobsApi.getJob(jobId)
      setSelectedJob(res.data)
      return res.data
    } catch (error) {
      console.error('Failed to load job detail:', error)
      message.error('Failed to load job details')
      return null
    }
  }

  const startJob = async (jobName?: string) => {
    try {
      const res = await jobsApi.startJob(jobName ? { name: jobName } : {})
      message.success('Job started successfully')
      await loadJobs()
      return res.data.job_id
    } catch (error) {
      console.error('Failed to start job:', error)
      message.error('Failed to start job')
      return null
    }
  }

  const cancelJob = async (jobId: string) => {
    try {
      await jobsApi.cancelJob(jobId)
      message.success('Job cancelled')
      await loadJobs()
    } catch (error) {
      console.error('Failed to cancel job:', error)
      message.error('Failed to cancel job')
    }
  }

  const deleteJob = async (jobId: string) => {
    try {
      await jobsApi.deleteJob(jobId)
      message.success('Job deleted')
      await loadJobs()
    } catch (error) {
      console.error('Failed to delete job:', error)
      message.error('Failed to delete job')
    }
  }

  useEffect(() => {
    loadJobs()
  }, [])

  return {
    jobs,
    selectedJob,
    loading,
    total,
    loadJobs,
    loadJobDetail,
    startJob,
    cancelJob,
    deleteJob,
  }
}
