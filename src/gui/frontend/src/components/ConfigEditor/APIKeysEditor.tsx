import React, { useState, useEffect } from 'react'
import {
  Form,
  Input,
  Button,
  Card,
  Space,
  Divider,
  Row,
  Col,
  Slider,
  Tag,
  Spin,
  message,
  Tooltip,
} from 'antd'
import { EyeInvisibleOutlined, EyeOutlined, CheckCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons'
import { useConfig, APIConfig } from '../../hooks/useConfig'

const API_RATE_LIMITS = {
  SemanticScholar: { default: 1.0, min: 0.1, max: 10 },
  OpenAlex: { default: 10.0, min: 1, max: 100 },
  Arxiv: { default: 3.0, min: 0.5, max: 10 },
  IEEE: { default: 10.0, min: 1, max: 100 },
  Elsevier: { default: 6.0, min: 1, max: 50 },
  Springer: { default: 1.5, min: 0.5, max: 10 },
  HAL: { default: 10.0, min: 1, max: 100 },
  DBLP: { default: 10.0, min: 1, max: 100 },
  GoogleScholar: { default: 2.0, min: 0.5, max: 10 },
  Crossref: { default: 3.0, min: 1, max: 50 },
}

interface PasswordFieldProps {
  value?: string
  onChange?: (value: string) => void
}

const PasswordField: React.FC<PasswordFieldProps> = ({ value, onChange }) => {
  const [visible, setVisible] = useState(false)
  const displayValue = visible ? value : value ? '***' + value.slice(-4) : ''

  return (
    <Input
      type={visible ? 'text' : 'password'}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
      suffix={
        <span
          style={{ cursor: 'pointer' }}
          onClick={() => setVisible(!visible)}
        >
          {visible ? <EyeOutlined /> : <EyeInvisibleOutlined />}
        </span>
      }
      placeholder="Enter API key (or leave blank to skip)"
    />
  )
}

export const APIKeysEditor: React.FC = () => {
  const [form] = Form.useForm()
  const { api, loading, saveApi, testApi, exists } = useConfig()
  const [hasChanges, setHasChanges] = useState(false)
  const [testing, setTesting] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (api) {
      const formData: any = { ...api }
      // Ensure rate_limits exists
      if (!formData.rate_limits) {
        formData.rate_limits = {}
      }
      form.setFieldsValue(formData)
    }
  }, [api, form])

  if (loading) {
    return <Spin tip="Loading API configuration..." />
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const success = await saveApi(values as APIConfig)
      if (success) {
        setHasChanges(false)
      }
    } catch (error) {
      console.error('Validation failed:', error)
    }
  }

  const handleReset = () => {
    if (api) {
      form.setFieldsValue(api)
      setHasChanges(false)
    }
  }

  const handleTestApi = async (apiName: string) => {
    setTesting({ ...testing, [apiName]: true })
    await testApi(apiName)
    setTesting({ ...testing, [apiName]: false })
  }

  return (
    <div>
      <Card title="API Credentials & Configuration" style={{ marginBottom: 24 }}>
        <Form
          form={form}
          layout="vertical"
          onValuesChange={() => setHasChanges(true)}
        >
          {/* Zotero Section */}
          <Divider>Zotero Configuration</Divider>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item label="Zotero API Key" name="zotero_api_key">
                <PasswordField />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Space>
                <Button
                  loading={testing.Zotero}
                  onClick={() => handleTestApi('Zotero')}
                >
                  Test Connection
                </Button>
              </Space>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                label="Zotero User ID"
                name="zotero_user_id"
                tooltip="Auto-fetched from API key"
              >
                <Input placeholder="User ID" disabled />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="Zotero Collection ID" name="zotero_collection_id">
                <Input placeholder="Collection ID (optional)" />
              </Form.Item>
            </Col>
          </Row>

          {/* Required APIs Section */}
          <Divider>Required APIs (Must Configure)</Divider>
          <p style={{ color: '#ff4d4f', marginBottom: 16 }}>
            ⚠️ You must configure at least one of these APIs to collect papers
          </p>

          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item label="IEEE API Key" name="ieee_api_key">
                <PasswordField />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Space>
                <Button
                  loading={testing.IEEE}
                  onClick={() => handleTestApi('IEEE')}
                >
                  Test
                </Button>
              </Space>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item label="Elsevier API Key" name="elsevier_api_key">
                <PasswordField />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Space>
                <Button
                  loading={testing.Elsevier}
                  onClick={() => handleTestApi('Elsevier')}
                >
                  Test
                </Button>
              </Space>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                label="Elsevier Institutional Token"
                name="elsevier_inst_token"
              >
                <PasswordField />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item label="Springer API Key" name="springer_api_key">
                <PasswordField />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Space>
                <Button
                  loading={testing.Springer}
                  onClick={() => handleTestApi('Springer')}
                >
                  Test
                </Button>
              </Space>
            </Col>
          </Row>

          {/* Optional APIs Section */}
          <Divider>Optional APIs (Recommended)</Divider>
          <p style={{ color: '#faad14', marginBottom: 16 }}>
            ℹ️ These improve rate limits and search coverage
          </p>

          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                label="Semantic Scholar API Key"
                name="semantic_scholar_api_key"
              >
                <PasswordField />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Space>
                <Button
                  loading={testing.SemanticScholar}
                  onClick={() => handleTestApi('SemanticScholar')}
                >
                  Test
                </Button>
              </Space>
            </Col>
          </Row>

          {/* Rate Limits Section */}
          <Divider>Rate Limits (requests per second)</Divider>
          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) => true}
          >
            {() => (
              <div>
                {Object.entries(API_RATE_LIMITS).map(([apiName, config]) => (
                  <Row gutter={16} key={apiName} style={{ marginBottom: 20 }}>
                    <Col xs={24} md={6}>
                      <label>{apiName}</label>
                    </Col>
                    <Col xs={24} md={12}>
                      <Form.Item
                        name={['rate_limits', apiName]}
                        initialValue={config.default}
                        noStyle
                      >
                        <Slider
                          min={config.min}
                          max={config.max}
                          step={0.1}
                          marks={{
                            [config.min]: String(config.min),
                            [config.default]: 'default',
                            [config.max]: String(config.max),
                          }}
                        />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={6}>
                      <Form.Item
                        name={['rate_limits', apiName]}
                        noStyle
                      >
                        {({ value }) => (
                          <span style={{ fontWeight: 'bold' }}>
                            {Number(value || config.default).toFixed(1)} req/s
                          </span>
                        )}
                      </Form.Item>
                    </Col>
                  </Row>
                ))}
              </div>
            )}
          </Form.Item>

          <p style={{ fontSize: 12, color: '#666', marginTop: 16 }}>
            💡 These are conservative defaults. Check your API dashboard for actual limits.
          </p>

          {/* Form Actions */}
          <Divider />
          <Space>
            <Button
              type="primary"
              onClick={handleSave}
              disabled={!hasChanges}
              size="large"
            >
              Save API Configuration
            </Button>
            <Button onClick={handleReset} disabled={!hasChanges} size="large">
              Discard Changes
            </Button>
          </Space>
        </Form>
      </Card>
    </div>
  )
}

export default APIKeysEditor
