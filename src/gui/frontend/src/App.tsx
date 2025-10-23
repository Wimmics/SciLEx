import React from 'react'
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom'
import { Layout, Menu, Button } from 'antd'
import {
  HomeOutlined,
  SettingOutlined,
  KeyOutlined,
  PlayCircleOutlined,
  HistoryOutlined,
} from '@ant-design/icons'
import Home from './pages/Home'
import ConfigPage from './pages/ConfigPage'
import APIKeysPage from './pages/APIKeysPage'
import DashboardPage from './pages/DashboardPage'
import HistoryPage from './pages/HistoryPage'
import './App.css'

const { Header, Content, Footer, Sider } = Layout

function App() {
  const [collapsed, setCollapsed] = React.useState(false)

  return (
    <Router>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider
          collapsible
          collapsed={collapsed}
          onCollapse={setCollapsed}
          theme="dark"
        >
          <div className="logo" style={{ padding: '16px', color: 'white', fontWeight: 'bold', textAlign: 'center' }}>
            SciLEx
          </div>
          <Menu
            theme="dark"
            mode="inline"
            defaultSelectedKeys={['home']}
            items={[
              {
                key: 'home',
                icon: <HomeOutlined />,
                label: <Link to="/">Home</Link>,
              },
              {
                key: 'dashboard',
                icon: <PlayCircleOutlined />,
                label: <Link to="/dashboard">Monitor</Link>,
              },
              {
                type: 'divider',
              },
              {
                key: 'config-group',
                label: 'Configuration',
                type: 'group',
                children: [
                  {
                    key: 'config',
                    icon: <SettingOutlined />,
                    label: <Link to="/config">Collection</Link>,
                  },
                  {
                    key: 'api-keys',
                    icon: <KeyOutlined />,
                    label: <Link to="/api-keys">API Keys</Link>,
                  },
                ],
              },
              {
                key: 'history',
                icon: <HistoryOutlined />,
                label: <Link to="/history">History</Link>,
              },
            ]}
          />
        </Sider>

        <Layout>
          <Header style={{ background: '#fff', padding: '0 50px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h1 style={{ margin: 0, fontSize: 20 }}>SciLEx - Literature Collection GUI</h1>
              <Button type="text" href="https://github.com/anthropics/claude-code" target="_blank">
                Documentation
              </Button>
            </div>
          </Header>

          <Content style={{ margin: '24px 24px', minHeight: 'calc(100vh - 64px - 70px)' }}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/config" element={<ConfigPage />} />
              <Route path="/api-keys" element={<APIKeysPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/history" element={<HistoryPage />} />
            </Routes>
          </Content>

          <Footer style={{ textAlign: 'center' }}>
            SciLEx GUI © 2024 - A web-based interface for systematic literature reviews
          </Footer>
        </Layout>
      </Layout>
    </Router>
  )
}

export default App
