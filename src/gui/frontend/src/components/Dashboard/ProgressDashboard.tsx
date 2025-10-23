import React, { useState, useEffect } from 'react'
import {
  Card,
  Progress,
  Statistic,
  Row,
  Col,
  Button,
  Space,
  Divider,
  List,
  Empty,
  Tag,
  Alert,
  Spin,
  message,
} from 'antd'
import {
  PlayCircleOutlined,
  StopOutlined,
  DeleteOutlined,
  DownloadOutlined,
} from '@ant-design/icons'
import { connectWebSocket } from '../../services/api'
import { useJobs, Job } from '../../hooks/useJobs'

interface ProgressEvent {
  job_id: string
  type: string
  data: any
  timestamp?: string
}

export interface ProgressDashboardProps {
  jobId?: string
  onJobComplete?: (jobId: string) => void
}

export const ProgressDashboard: React.FC<ProgressDashboardProps> = ({
  jobId,
  onJobComplete,
}) => {
  const { selectedJob, loadJobDetail, cancelJob, startJob } = useJobs()
  const [currentJob, setCurrentJob] = useState<Job | null>(null)
  const [logs, setLogs] = useState<Array<{ timestamp: string; level: string; message: string }>>([])
  const [ws, setWs] = useState<WebSocket | null>(null)
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [phase, setPhase] = useState('idle')

  // Load job detail when jobId changes
  useEffect(() => {
    if (jobId) {
      loadJobDetail(jobId)
    }
  }, [jobId])

  // Update local job when selectedJob changes
  useEffect(() => {
    if (selectedJob) {
      setCurrentJob(selectedJob)
      // Parse logs from job detail
      if (selectedJob.logs) {
        setLogs(selectedJob.logs)
      }
    }
  }, [selectedJob])

  // Connect to WebSocket when job starts running
  useEffect(() => {
    if (currentJob && currentJob.status === 'running' && !ws) {
      const newWs = connectWebSocket(currentJob.id, (event: ProgressEvent) => {
        handleWebSocketMessage(event)
      })

      newWs.onerror = (error) => {
        console.error('WebSocket error:', error)
        message.error('Connection to job updates lost')
      }

      newWs.onclose = () => {
        console.log('WebSocket closed')
      }

      setWs(newWs)

      return () => {
        if (newWs.readyState === WebSocket.OPEN) {
          newWs.close()
        }
      }
    }
  }, [currentJob?.status])

  const handleWebSocketMessage = (event: ProgressEvent) => {
    console.log('WebSocket message:', event)

    switch (event.type) {
      case 'progress_update':
        const { current = 0, total = 100 } = event.data
        const newProgress = total > 0 ? Math.round((current / total) * 100) : 0
        setProgress(newProgress)
        break

      case 'phase_complete':
        setPhase(event.data.phase || '')
        break

      case 'job_complete':
        setPhase('completed')
        message.success('Job completed successfully!')
        if (onJobComplete) {
          onJobComplete(event.job_id)
        }
        break

      case 'job_failed':
        message.error(`Job failed: ${event.data.error}`)
        setPhase('failed')
        break

      case 'log_message':
        const newLog = {
          timestamp: new Date().toISOString(),
          level: event.data.level || 'INFO',
          message: event.data.message || '',
        }
        setLogs((prev) => [...prev.slice(-49), newLog])
        break
    }
  }

  const handleStartJob = async () => {
    setLoading(true)
    try {
      const newJobId = await startJob()
      if (newJobId) {
        const job = await loadJobDetail(newJobId)
        if (job) {
          setCurrentJob(job)
          setProgress(0)
          setPhase('collection')
        }
      }
    } finally {
      setLoading(false)
    }
  }

  const handleCancelJob = async () => {
    if (currentJob) {
      await cancelJob(currentJob.id)
      setPhase('cancelled')
      setCurrentJob((prev) => prev ? { ...prev, status: 'cancelled' } : null)
    }
  }

  // Determine phase display
  const phases = ['collection', 'aggregation', 'citations', 'zotero']
  const currentPhaseIndex = phases.indexOf(phase)

  const getStatusColor = (status?: string): string => {
    switch (status) {
      case 'completed':
        return 'green'
      case 'running':
        return 'blue'
      case 'failed':
        return 'red'
      case 'cancelled':
        return 'orange'
      default:
        return 'default'
    }
  }

  const getPhaseStatus = (phaseName: string): 'process' | 'finish' | 'error' | 'wait' => {
    const phaseIdx = phases.indexOf(phaseName)
    if (phase === 'failed' && phaseIdx <= currentPhaseIndex) return 'error'
    if (phaseIdx < currentPhaseIndex) return 'finish'
    if (phaseIdx === currentPhaseIndex) return 'process'
    return 'wait'
  }

  if (!currentJob) {
    return (
      <Card title="Job Progress" style={{ marginBottom: 24 }}>
        <Empty description="No job running" style={{ marginTop: 48 }}>
          <Button
            type="primary"
            size="large"
            onClick={handleStartJob}
            loading={loading}
          >
            Start Collection
          </Button>
        </Empty>
      </Card>
    )
  }

  return (
    <div>
      {/* Job Header */}
      <Card
        title={`Job: ${currentJob.name}`}
        extra={<Tag color={getStatusColor(currentJob.status)}>{currentJob.status.toUpperCase()}</Tag>}
        style={{ marginBottom: 24 }}
      >
        <Row gutter={16}>
          <Col xs={12} md={6}>
            <Statistic
              title="Status"
              value={currentJob.status}
              valueStyle={{ fontSize: 14 }}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title="Papers Found"
              value={currentJob.papers_found}
              precision={0}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title="Duplicates Removed"
              value={currentJob.duplicates_removed || 0}
              precision={0}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title="Citations"
              value={currentJob.citations_fetched || 0}
              precision={0}
            />
          </Col>
        </Row>
      </Card>

      {/* Overall Progress */}
      <Card title="Overall Progress" style={{ marginBottom: 24 }}>
        <Progress percent={progress} status={currentJob.status === 'running' ? 'active' : 'normal'} />

        <Divider />

        <div style={{ marginBottom: 24 }}>
          <p style={{ marginBottom: 12, fontWeight: 'bold' }}>Phases:</p>
          <Row gutter={16}>
            {phases.map((p) => (
              <Col key={p} xs={12} md={6}>
                <div
                  style={{
                    padding: '12px',
                    border: '1px solid #d9d9d9',
                    borderRadius: '4px',
                    textAlign: 'center',
                    backgroundColor:
                      getPhaseStatus(p) === 'process'
                        ? '#e6f7ff'
                        : getPhaseStatus(p) === 'finish'
                        ? '#f6ffed'
                        : getPhaseStatus(p) === 'error'
                        ? '#fff1f0'
                        : 'transparent',
                  }}
                >
                  <div style={{ fontWeight: 'bold', textTransform: 'capitalize' }}>
                    {p}
                  </div>
                  <Tag
                    color={
                      getPhaseStatus(p) === 'process'
                        ? 'blue'
                        : getPhaseStatus(p) === 'finish'
                        ? 'green'
                        : getPhaseStatus(p) === 'error'
                        ? 'red'
                        : 'default'
                    }
                  >
                    {getPhaseStatus(p) === 'wait' ? '⏳ Waiting' : getPhaseStatus(p).toUpperCase()}
                  </Tag>
                </div>
              </Col>
            ))}
          </Row>
        </div>
      </Card>

      {/* Live Log */}
      <Card title="Live Log" style={{ marginBottom: 24 }}>
        {logs.length === 0 ? (
          <Empty description="No logs yet" />
        ) : (
          <div
            style={{
              maxHeight: 300,
              overflowY: 'auto',
              fontFamily: 'monospace',
              fontSize: 12,
              backgroundColor: '#f5f5f5',
              padding: '12px',
              borderRadius: '4px',
            }}
          >
            <List
              dataSource={logs.slice(-50)}
              renderItem={(log) => (
                <div
                  style={{
                    marginBottom: '4px',
                    color:
                      log.level === 'ERROR'
                        ? '#ff4d4f'
                        : log.level === 'WARNING'
                        ? '#faad14'
                        : '#000',
                  }}
                >
                  <span style={{ color: '#999' }}>
                    [{new Date(log.timestamp).toLocaleTimeString()}]
                  </span>{' '}
                  <span style={{ fontWeight: 'bold' }}>[{log.level}]</span> {log.message}
                </div>
              )}
            />
          </div>
        )}
      </Card>

      {/* Action Buttons */}
      <Card>
        <Space>
          {currentJob.status === 'running' ? (
            <>
              <Button
                type="primary"
                danger
                icon={<StopOutlined />}
                onClick={handleCancelJob}
              >
                Cancel Job
              </Button>
            </>
          ) : currentJob.status === 'completed' ? (
            <>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
              >
                Download Results
              </Button>
              <Button
                icon={<PlayCircleOutlined />}
                onClick={handleStartJob}
              >
                Start New Collection
              </Button>
            </>
          ) : null}
        </Space>
      </Card>
    </div>
  )
}

export default ProgressDashboard
