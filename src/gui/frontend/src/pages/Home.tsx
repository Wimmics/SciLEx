import React, { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Button, Space, Alert, Spin, Empty } from 'antd'
import { PlayCircleOutlined, SettingOutlined, KeyOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useJobs } from '../hooks/useJobs'
import { useConfig } from '../hooks/useConfig'

const Home: React.FC = () => {
  const navigate = useNavigate()
  const { jobs, total, loading } = useJobs()
  const { scilex, api, exists, loading: configLoading } = useConfig()
  const [readyToStart, setReadyToStart] = useState(false)

  useEffect(() => {
    // Check if we have minimum config to start
    const hasConfig = exists.scilex && scilex
    const hasApis = api && (api.ieee_api_key || api.elsevier_api_key || api.springer_api_key)
    setReadyToStart(hasConfig && hasApis)
  }, [scilex, api, exists])

  const activeJobs = jobs.filter((j) => j.status === 'running')
  const completedJobs = jobs.filter((j) => j.status === 'completed')
  const failedJobs = jobs.filter((j) => j.status === 'failed')

  return (
    <div>
      {/* Welcome Section */}
      <Card style={{ marginBottom: 24, textAlign: 'center' }}>
        <h1 style={{ fontSize: 32, marginBottom: 16 }}>Welcome to SciLEx GUI</h1>
        <p style={{ fontSize: 16, color: '#666', marginBottom: 24 }}>
          A web-based interface for systematic literature reviews and academic paper exploration
        </p>

        {!readyToStart && (
          <Alert
            message="Setup Required"
            description="Please configure your API credentials and collection parameters to get started"
            type="info"
            style={{ marginBottom: 24 }}
            showIcon
          />
        )}

        <Space>
          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            onClick={() => navigate('/dashboard')}
            disabled={!readyToStart || activeJobs.length > 0}
          >
            {activeJobs.length > 0 ? 'Job Running' : 'Start Collection'}
          </Button>
          <Button
            size="large"
            icon={<SettingOutlined />}
            onClick={() => navigate('/config')}
          >
            Configure
          </Button>
          <Button
            size="large"
            icon={<KeyOutlined />}
            onClick={() => navigate('/api-keys')}
          >
            API Keys
          </Button>
        </Space>
      </Card>

      {/* Statistics */}
      <Spin spinning={loading || configLoading}>
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col xs={24} md={6}>
            <Card>
              <Statistic
                title="Total Jobs"
                value={total}
                valueStyle={{ color: '#1890ff' }}
              />
            </Card>
          </Col>
          <Col xs={24} md={6}>
            <Card>
              <Statistic
                title="Active"
                value={activeJobs.length}
                valueStyle={{ color: '#faad14' }}
              />
            </Card>
          </Col>
          <Col xs={24} md={6}>
            <Card>
              <Statistic
                title="Completed"
                value={completedJobs.length}
                valueStyle={{ color: '#52c41a' }}
              />
            </Card>
          </Col>
          <Col xs={24} md={6}>
            <Card>
              <Statistic
                title="Failed"
                value={failedJobs.length}
                valueStyle={{ color: '#ff4d4f' }}
              />
            </Card>
          </Col>
        </Row>

        {/* Quick Start */}
        <Card title="Getting Started" style={{ marginBottom: 24 }}>
          <ol style={{ fontSize: 14, lineHeight: 2 }}>
            <li>
              <strong>Configure API Credentials:</strong>{' '}
              <Button type="link" onClick={() => navigate('/api-keys')}>
                Go to API Keys
              </Button>
              {' - Enter your IEEE, Elsevier, Springer, and other API keys'}
            </li>
            <li>
              <strong>Set Collection Parameters:</strong>{' '}
              <Button type="link" onClick={() => navigate('/config')}>
                Go to Configuration
              </Button>
              {' - Select keywords, years, and APIs to search'}
            </li>
            <li>
              <strong>Start Collection:</strong>{' '}
              <Button
                type="link"
                onClick={() => navigate('/dashboard')}
                disabled={!readyToStart}
              >
                Go to Monitor
              </Button>
              {' - Click Start Collection and watch real-time progress'}
            </li>
            <li>
              <strong>View Results:</strong>{' '}
              <Button type="link" onClick={() => navigate('/history')}>
                Go to History
              </Button>
              {' - Browse collected papers and export results'}
            </li>
          </ol>
        </Card>

        {/* Configuration Status */}
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Card title="Collection Configuration">
              {exists.scilex && scilex ? (
                <div>
                  <p>
                    <strong>Keywords:</strong> {scilex.keywords?.[0]?.join(', ') || 'None'}
                  </p>
                  <p>
                    <strong>Years:</strong> {scilex.years?.join(', ') || 'None'}
                  </p>
                  <p>
                    <strong>APIs:</strong> {scilex.apis?.join(', ') || 'None'}
                  </p>
                  <Button
                    type="primary"
                    onClick={() => navigate('/config')}
                    style={{ marginTop: 16 }}
                  >
                    Edit
                  </Button>
                </div>
              ) : (
                <Empty description="Not configured">
                  <Button
                    type="primary"
                    onClick={() => navigate('/config')}
                  >
                    Create Configuration
                  </Button>
                </Empty>
              )}
            </Card>
          </Col>

          <Col xs={24} md={12}>
            <Card title="API Credentials">
              {exists.api && api ? (
                <div>
                  <p>
                    <strong>IEEE:</strong>{' '}
                    {api.ieee_api_key ? '✓ Configured' : '✗ Not configured'}
                  </p>
                  <p>
                    <strong>Elsevier:</strong>{' '}
                    {api.elsevier_api_key ? '✓ Configured' : '✗ Not configured'}
                  </p>
                  <p>
                    <strong>Springer:</strong>{' '}
                    {api.springer_api_key ? '✓ Configured' : '✗ Not configured'}
                  </p>
                  <p>
                    <strong>SemanticScholar:</strong>{' '}
                    {api.semantic_scholar_api_key ? '✓ Configured' : '✗ Not configured'}
                  </p>
                  <Button
                    type="primary"
                    onClick={() => navigate('/api-keys')}
                    style={{ marginTop: 16 }}
                  >
                    Edit
                  </Button>
                </div>
              ) : (
                <Empty description="Not configured">
                  <Button
                    type="primary"
                    onClick={() => navigate('/api-keys')}
                  >
                    Configure Keys
                  </Button>
                </Empty>
              )}
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  )
}

export default Home
