import { useState, useEffect } from 'react'
import { Layout, Typography, Space, Card } from 'antd'

const { Header, Content } = Layout
const { Title, Text } = Typography

function App() {
  const [health, setHealth] = useState<any>(null)

  useEffect(() => {
    fetch('/api/health')
      .then(res => res.json())
      .then(data => setHealth(data))
      .catch(err => console.error('Health check failed:', err))
  }, [])

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ background: '#001529', padding: '0 50px' }}>
        <Title level={3} style={{ color: 'white', margin: '16px 0' }}>
          SciLEx - Literature Collection GUI
        </Title>
      </Header>
      <Content style={{ padding: '50px' }}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Card title="Welcome to SciLEx GUI">
            <Text>
              This is a web-based interface for systematic literature collection.
            </Text>
          </Card>

          <Card title="System Status">
            {health ? (
              <Text type="success">✓ Backend connected: {health.status}</Text>
            ) : (
              <Text type="secondary">Connecting to backend...</Text>
            )}
          </Card>
        </Space>
      </Content>
    </Layout>
  )
}

export default App
