import { useCallback, useEffect, useRef, useState } from 'react'
import { getDashboardData } from '../api/dashboard.js'

const initialState = {
  status: 'loading',
  data: null,
  backend: null,
  error: null,
}

export function useDashboardData() {
  const [state, setState] = useState(initialState)
  const requestId = useRef(0)

  const refresh = useCallback(async () => {
    const activeRequest = ++requestId.current
    setState((previous) => ({ ...previous, status: 'loading', error: null }))

    try {
      const response = await getDashboardData()
      if (activeRequest === requestId.current) {
        setState({ status: 'ready', error: null, ...response })
      }
    } catch (error) {
      if (activeRequest === requestId.current) {
        setState((previous) => ({
          ...previous,
          status: 'error',
          error: error instanceof Error ? error : new Error('Could not load dashboard data.'),
        }))
      }
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { ...state, refresh }
}
