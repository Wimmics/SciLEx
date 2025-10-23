import React, { useState, useEffect } from 'react'
import {
  Form,
  Input,
  Select,
  Button,
  Card,
  Space,
  Checkbox,
  Divider,
  Row,
  Col,
  Tag,
  Empty,
  Spin,
  message,
} from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { useConfig, ScilexConfig } from '../../hooks/useConfig'

const AVAILABLE_APIS = [
  'SemanticScholar',
  'OpenAlex',
  'IEEE',
  'Elsevier',
  'Springer',
  'HAL',
  'DBLP',
  'Arxiv',
  'GoogleScholar',
  'Crossref',
]

const AVAILABLE_YEARS = Array.from({ length: 25 }, (_, i) => 2024 - i)

export const ScilexConfigEditor: React.FC = () => {
  const [form] = Form.useForm()
  const { scilex, loading, saveScilex, exists } = useConfig()
  const [hasChanges, setHasChanges] = useState(false)

  useEffect(() => {
    if (scilex) {
      form.setFieldsValue(scilex)
    }
  }, [scilex, form])

  if (loading) {
    return <Spin tip="Loading configuration..." />
  }

  if (!exists.scilex) {
    return (
      <Card>
        <Empty
          description="No configuration found"
          style={{ marginTop: 48, marginBottom: 48 }}
        >
          <Button type="primary">Create New Configuration</Button>
        </Empty>
      </Card>
    )
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const success = await saveScilex(values as ScilexConfig)
      if (success) {
        setHasChanges(false)
      }
    } catch (error) {
      console.error('Validation failed:', error)
    }
  }

  const handleReset = () => {
    if (scilex) {
      form.setFieldsValue(scilex)
      setHasChanges(false)
    }
  }

  return (
    <div>
      <Card title="Collection Configuration" style={{ marginBottom: 24 }}>
        <Form
          form={form}
          layout="vertical"
          onValuesChange={() => setHasChanges(true)}
        >
          {/* Keywords Section */}
          <Divider>Keywords</Divider>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                label="Group 1 Keywords (OR logic within group)"
                name={['keywords', 0]}
                rules={[
                  {
                    required: true,
                    message: 'At least one keyword required in Group 1',
                  },
                ]}
              >
                <Select
                  mode="tags"
                  placeholder="Enter keywords (e.g., machine learning, deep learning)"
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                label="Group 2 Keywords (optional, AND with Group 1)"
                name={['keywords', 1]}
              >
                <Select
                  mode="tags"
                  placeholder="Enter keywords (optional)"
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </Col>
          </Row>

          <p style={{ fontSize: 12, color: '#666' }}>
            💡 Single group: papers matching ANY keyword in Group 1 | Dual
            groups: papers matching (ANY from Group 1 AND ANY from Group 2)
          </p>

          {/* Years Section */}
          <Divider>Years</Divider>
          <Form.Item
            label="Select years to search"
            name="years"
            rules={[
              {
                required: true,
                message: 'At least one year required',
              },
            ]}
          >
            <Select
              mode="multiple"
              placeholder="Select years..."
              optionLabelProp="label"
            >
              {AVAILABLE_YEARS.map((year) => (
                <Select.Option key={year} value={year}>
                  {year}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          {/* APIs Section */}
          <Divider>APIs</Divider>
          <Form.Item label="Select APIs to use" name="apis">
            <Select
              mode="multiple"
              placeholder="Select APIs..."
              style={{ width: '100%' }}
            >
              {AVAILABLE_APIS.map((api) => (
                <Select.Option key={api} value={api}>
                  {api}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <div style={{ marginBottom: 16 }}>
            <Tag color="red">Required:</Tag>
            <Tag>IEEE</Tag>
            <Tag>Elsevier</Tag>
            <Tag>Springer</Tag>
            <Tag color="orange">Optional (recommended):</Tag>
            <Tag>SemanticScholar</Tag>
          </div>

          {/* Fields Section */}
          <Divider>Search Fields</Divider>
          <Form.Item label="Fields to search in" name="fields">
            <Checkbox.Group>
              <Row>
                <Col xs={24}>
                  <Checkbox value="title">Title</Checkbox>
                </Col>
                <Col xs={24}>
                  <Checkbox value="abstract">Abstract</Checkbox>
                </Col>
                <Col xs={24}>
                  <Checkbox value="keywords">Keywords</Checkbox>
                </Col>
              </Row>
            </Checkbox.Group>
          </Form.Item>

          {/* Advanced Options */}
          <Divider>Advanced Options</Divider>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                label="Collection Name"
                name="collect_name"
                rules={[
                  {
                    required: true,
                    message: 'Collection name required',
                  },
                ]}
              >
                <Input placeholder="e.g., ml_nlp_survey_2024" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                label="Email (optional, for some APIs)"
                name="email"
              >
                <Input type="email" placeholder="your.email@example.com" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item label="Output Directory" name="output_dir">
                <Input placeholder="output" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="Aggregated File Name" name="aggregate_file">
                <Input placeholder="aggregated_data.csv" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="aggregate_txt_filter"
                valuePropName="checked"
              >
                <Checkbox>Apply text filters during aggregation</Checkbox>
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="aggregate_get_citations"
                valuePropName="checked"
              >
                <Checkbox>Fetch citations automatically</Checkbox>
              </Form.Item>
            </Col>
          </Row>

          {/* Form Actions */}
          <Divider />
          <Space>
            <Button
              type="primary"
              onClick={handleSave}
              disabled={!hasChanges}
              size="large"
            >
              Save Configuration
            </Button>
            <Button onClick={handleReset} disabled={!hasChanges} size="large">
              Discard Changes
            </Button>
            <Button type="dashed" size="large">
              Reset to Defaults
            </Button>
          </Space>
        </Form>
      </Card>
    </div>
  )
}

export default ScilexConfigEditor
