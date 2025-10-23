import React, { useState, useEffect } from 'react'
import { Button, Empty, Spin, Card } from 'antd'
import { PlayCircleOutlined } from '@ant-design/icons'
import ProgressDashboard from '../components/Dashboard/ProgressDashboard'
import { useJobs } from '../hooks/useJobs'

const DashboardPage: React.FC = () => {
  const { jobs, loading } = useJobs()
  const [runningJobId, setRunningJobId] = useState<string | undefined>(undefined)

  useEffect(() => {
    // Find any running job
    const running = jobs.find((j) => j.status === 'running')
    if (running) {
      setRunningJobId(running.id)
    }
  }, [jobs])

  if (loading) {
    return <Spin tip="Loading..." />
  }

  return (
    <div>
      <ProgressDashboard
        jobId={runningJobId}
        onJobComplete={() => {
          setRunningJobId(undefined)
        }}
      />
    </div>
  )
}

export default DashboardPage
