import React, { useState, useEffect } from 'react'
import {
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Input,
  DatePicker,
  Select,
  Row,
  Col,
  Statistic,
  Card,
  Empty,
  Spin,
  message,
} from 'antd'
import {
  EyeOutlined,
  DeleteOutlined,
  DownloadOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { useJobs, Job } from '../../hooks/useJobs'

interface JobHistoryBrowserProps {
  onJobSelect?: (job: Job) => void
}

export const JobHistoryBrowser: React.FC<JobHistoryBrowserProps> = ({
  onJobSelect,
}) => {
  const {
    jobs,
    loading,
    total,
    loadJobs,
    loadJobDetail,
    deleteJob,
    startJob,
  } = useJobs()

  const [filterStatus, setFilterStatus] = useState<string | undefined>(undefined)
  const [searchText, setSearchText] = useState('')
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [selectedJobDetail, setSelectedJobDetail] = useState<Job | null>(null)
  const [detailModalVisible, setDetailModalVisible] = useState(false)

  const handleLoadJobs = (status?: string) => {
    const offset = (currentPage - 1) * pageSize
    loadJobs(status, pageSize, offset)
  }

  useEffect(() => {
    handleLoadJobs(filterStatus)
  }, [currentPage, pageSize, filterStatus])

  const handleStatusFilter = (value: string | undefined) => {
    setFilterStatus(value)
    setCurrentPage(1)
  }

  const handleViewDetails = async (jobId: string) => {
    const detail = await loadJobDetail(jobId)
    if (detail) {
      setSelectedJobDetail(detail)
      setDetailModalVisible(true)
    }
  }

  const handleDeleteJob = (jobId: string) => {
    Modal.confirm({
      title: 'Delete Job',
      content: 'Are you sure you want to delete this job and all associated data?',
      okText: 'Delete',
      okType: 'danger',
      onOk: async () => {
        await deleteJob(jobId)
        handleLoadJobs(filterStatus)
      },
    })
  }

  const handleRerunJob = async (job: Job) => {
    Modal.confirm({
      title: 'Rerun Job',
      content: `Rerun collection "${job.name}"?`,
      okText: 'Rerun',
      onOk: async () => {
        await startJob(job.name)
        handleLoadJobs(filterStatus)
      },
    })
  }

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'completed':
        return 'green'
      case 'running':
        return 'blue'
      case 'failed':
        return 'red'
      case 'cancelled':
        return 'orange'
      case 'queued':
        return 'default'
      default:
        return 'default'
    }
  }

  const columns = [
    {
      title: 'Collection Name',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (text: string) => <span>{text}</span>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={getStatusColor(status)}>{status.toUpperCase()}</Tag>
      ),
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (date: string) => new Date(date).toLocaleString(),
    },
    {
      title: 'Papers',
      dataIndex: 'papers_found',
      key: 'papers_found',
      width: 80,
      align: 'right' as const,
    },
    {
      title: 'Duration',
      dataIndex: 'duration_seconds',
      key: 'duration_seconds',
      width: 100,
      render: (seconds?: number) => {
        if (!seconds) return '-'
        const hours = Math.floor(seconds / 3600)
        const mins = Math.floor((seconds % 3600) / 60)
        const secs = seconds % 60
        if (hours > 0) {
          return `${hours}h ${mins}m`
        } else if (mins > 0) {
          return `${mins}m ${secs}s`
        } else {
          return `${secs}s`
        }
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (_: any, record: Job) => (
        <Space>
          <Button
            type="text"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewDetails(record.id)}
          >
            View
          </Button>
          {record.status === 'completed' && (
            <Button
              type="text"
              size="small"
              icon={<DownloadOutlined />}
            >
              Export
            </Button>
          )}
          {record.status !== 'running' && (
            <Button
              type="text"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => handleRerunJob(record)}
            >
              Rerun
            </Button>
          )}
          <Button
            type="text"
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => handleDeleteJob(record.id)}
          >
            Delete
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      {/* Statistics */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col xs={24} md={6}>
          <Card>
            <Statistic
              title="Total Jobs"
              value={total}
              precision={0}
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic
              title="Completed"
              value={jobs.filter((j) => j.status === 'completed').length}
              precision={0}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic
              title="Failed"
              value={jobs.filter((j) => j.status === 'failed').length}
              precision={0}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic
              title="Running"
              value={jobs.filter((j) => j.status === 'running').length}
              precision={0}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Filters */}
      <Card style={{ marginBottom: 24 }}>
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Input.Search
              placeholder="Search by name..."
              allowClear
              onSearch={(value) => setSearchText(value)}
            />
          </Col>
          <Col xs={24} md={8}>
            <Select
              placeholder="Filter by status"
              allowClear
              onChange={handleStatusFilter}
              style={{ width: '100%' }}
              options={[
                { label: 'Completed', value: 'completed' },
                { label: 'Failed', value: 'failed' },
                { label: 'Running', value: 'running' },
                { label: 'Cancelled', value: 'cancelled' },
                { label: 'Queued', value: 'queued' },
              ]}
            />
          </Col>
          <Col xs={24} md={8}>
            <Button block onClick={() => handleLoadJobs(filterStatus)}>
              Refresh
            </Button>
          </Col>
        </Row>
      </Card>

      {/* Jobs Table */}
      <Card title="Job History">
        <Spin spinning={loading}>
          {jobs.length === 0 ? (
            <Empty description="No jobs found" />
          ) : (
            <Table
              columns={columns}
              dataSource={jobs.map((job) => ({
                ...job,
                key: job.id,
              }))}
              pagination={{
                current: currentPage,
                pageSize: pageSize,
                total: total,
                onChange: (page, size) => {
                  setCurrentPage(page)
                  setPageSize(size)
                },
              }}
              size="small"
            />
          )}
        </Spin>
      </Card>

      {/* Job Detail Modal */}
      <Modal
        title={selectedJobDetail ? `Job: ${selectedJobDetail.name}` : 'Job Details'}
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        width={800}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>
            Close
          </Button>,
        ]}
      >
        {selectedJobDetail && (
          <div>
            <Row gutter={16} style={{ marginBottom: 24 }}>
              <Col xs={12}>
                <Statistic title="Status" value={selectedJobDetail.status} />
              </Col>
              <Col xs={12}>
                <Statistic title="Papers Found" value={selectedJobDetail.papers_found} />
              </Col>
            </Row>

            <Row gutter={16} style={{ marginBottom: 24 }}>
              <Col xs={12}>
                <Statistic title="Duplicates" value={selectedJobDetail.duplicates_removed || 0} />
              </Col>
              <Col xs={12}>
                <Statistic title="Citations" value={selectedJobDetail.citations_fetched || 0} />
              </Col>
            </Row>

            {selectedJobDetail.error_message && (
              <div style={{ marginBottom: 24, padding: '12px', backgroundColor: '#fff1f0', border: '1px solid #ffccc7', borderRadius: '4px' }}>
                <strong>Error:</strong> {selectedJobDetail.error_message}
              </div>
            )}

            {selectedJobDetail.logs && selectedJobDetail.logs.length > 0 && (
              <div>
                <h4>Recent Logs:</h4>
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
                  {selectedJobDetail.logs.slice(-20).map((log, idx) => (
                    <div key={idx} style={{ marginBottom: '4px' }}>
                      <span style={{ color: '#999' }}>
                        [{new Date(log.timestamp).toLocaleTimeString()}]
                      </span>{' '}
                      <span style={{ fontWeight: 'bold', color: log.level === 'ERROR' ? '#ff4d4f' : log.level === 'WARNING' ? '#faad14' : '#000' }}>
                        [{log.level}]
                      </span>{' '}
                      {log.message}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}

export default JobHistoryBrowser
