import { useState, useEffect } from 'react'
import { message } from 'antd'
import { configApi } from '../services/api'

export interface ScilexConfig {
  keywords: string[][]
  years: number[]
  apis: string[]
  fields: string[]
  collect: boolean
  collect_name: string
  output_dir: string
  email?: string
  aggregate_txt_filter: boolean
  aggregate_get_citations: boolean
  aggregate_file: string
}

export interface APIConfig {
  zotero_api_key?: string
  zotero_user_id?: string
  zotero_collection_id?: string
  ieee_api_key?: string
  elsevier_api_key?: string
  elsevier_inst_token?: string
  springer_api_key?: string
  semantic_scholar_api_key?: string
  rate_limits?: Record<string, number>
}

export const useConfig = () => {
  const [scilex, setScilex] = useState<ScilexConfig | null>(null)
  const [api, setApi] = useState<APIConfig | null>(null)
  const [loading, setLoading] = useState(false)
  const [exists, setExists] = useState<{ scilex: boolean; api: boolean }>({
    scilex: false,
    api: false,
  })

  const loadConfigs = async () => {
    setLoading(true)
    try {
      const [existsRes, scilexRes] = await Promise.all([
        configApi.checkExists(),
        configApi.getScilex(),
      ])

      setExists(existsRes.data)
      setScilex(scilexRes.data)

      try {
        const apiRes = await configApi.getApi()
        setApi(apiRes.data)
      } catch {
        // API config might not exist yet
      }
    } catch (error) {
      console.error('Failed to load configuration:', error)
      message.error('Failed to load configuration')
    } finally {
      setLoading(false)
    }
  }

  const saveScilex = async (config: ScilexConfig) => {
    try {
      await configApi.updateScilex(config)
      setScilex(config)
      message.success('Collection configuration saved')
      return true
    } catch (error) {
      console.error('Failed to save configuration:', error)
      message.error('Failed to save configuration')
      return false
    }
  }

  const saveApi = async (config: APIConfig) => {
    try {
      await configApi.updateApi(config)
      setApi(config)
      message.success('API configuration saved')
      return true
    } catch (error) {
      console.error('Failed to save API configuration:', error)
      message.error('Failed to save API configuration')
      return false
    }
  }

  const testApi = async (apiName: string) => {
    try {
      const res = await configApi.testConnection(apiName)
      if (res.data.success) {
        message.success(`${apiName} is reachable`)
      } else {
        message.error(`${apiName} test failed: ${res.data.message}`)
      }
      return res.data.success
    } catch (error) {
      console.error(`Failed to test ${apiName}:`, error)
      message.error(`Failed to test ${apiName} connection`)
      return false
    }
  }

  useEffect(() => {
    loadConfigs()
  }, [])

  return {
    scilex,
    api,
    exists,
    loading,
    saveScilex,
    saveApi,
    testApi,
    reload: loadConfigs,
  }
}
