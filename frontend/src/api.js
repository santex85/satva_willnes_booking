import axios from 'axios'

export const SESSION_KEY = 'satva_wellness_session'

export const loadSession = () => {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export const saveSession = (data) => {
  localStorage.setItem(SESSION_KEY, JSON.stringify(data))
}

export const clearSession = () => {
  localStorage.removeItem(SESSION_KEY)
}

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const session = loadSession()
  if (session?.access) {
    config.headers.Authorization = `Bearer ${session.access}`
  }
  return config
})

let refreshPromise = null

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error)
    }

    const session = loadSession()
    if (!session?.refresh) {
      clearSession()
      return Promise.reject(error)
    }

    if (!refreshPromise) {
      refreshPromise = axios
        .post('/api/v1/token/refresh/', { refresh: session.refresh })
        .then(({ data }) => {
          saveSession({ ...session, access: data.access, refresh: data.refresh || session.refresh })
          return data.access
        })
        .catch((refreshError) => {
          clearSession()
          throw refreshError
        })
        .finally(() => {
          refreshPromise = null
        })
    }

    try {
      const access = await refreshPromise
      original._retry = true
      original.headers.Authorization = `Bearer ${access}`
      return api(original)
    } catch (refreshError) {
      return Promise.reject(refreshError)
    }
  },
)

export const login = async (username, password) => {
  const { data } = await axios.post('/api/v1/token/', { username, password })
  return data
}

export const logout = () => {
  clearSession()
}

export const getBookings = async () => {
  const { data } = await api.get('/bookings/')
  return data
}

export const updateBooking = async (id, payload) => {
  const { data } = await api.patch(`/bookings/${id}/`, payload)
  return data
}

export const getGuests = async () => {
  const { data } = await api.get('/guests/')
  return data
}

export const createGuest = async (payload) => {
  const { data } = await api.post('/guests/', payload)
  return data
}

export const getSpecialists = async () => {
  const { data } = await api.get('/specialists/')
  return data
}

export const getCabinets = async () => {
  const { data } = await api.get('/cabinets/')
  return data
}

export const getServiceVariants = async () => {
  const { data } = await api.get('/service-variants/')
  return data
}

export const getServicePopularity = async ({ startDate, endDate, specialistId }) => {
  const params = { start_date: startDate, end_date: endDate }
  if (specialistId) params.specialist_id = specialistId
  const { data } = await api.get('/bookings/service_popularity/', { params })
  return data
}

export const getSpecialistLoad = async ({ startDate, endDate, specialistId }) => {
  const params = { start_date: startDate, end_date: endDate }
  if (specialistId) params.specialist_id = specialistId
  const { data } = await api.get('/bookings/specialist_load/', { params })
  return data
}

export const getGuestStatistics = async ({ startDate, endDate, specialistId }) => {
  const params = { start_date: startDate, end_date: endDate }
  if (specialistId) params.specialist_id = specialistId
  const { data } = await api.get('/guests/statistics/', { params })
  return data
}

export const mergeGuests = async ({ primaryId, duplicateIds, primaryDisplayName }) => {
  const { data } = await api.post('/guests/merge/', {
    primary_id: primaryId,
    duplicate_ids: duplicateIds,
    primary_display_name: primaryDisplayName,
  })
  return data
}

export const downloadCsvReport = async ({ startDate, endDate, specialistId }) => {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
  })
  if (specialistId) params.set('specialist_id', specialistId)

  const session = loadSession()
  const response = await fetch(`/api/v1/bookings/export_csv/?${params.toString()}`, {
    headers: {
      Authorization: `Bearer ${session?.access || ''}`,
    },
  })

  if (!response.ok) {
    throw new Error('Не удалось скачать отчёт')
  }

  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="([^"]+)"/)
  const filename = match ? match[1] : `otchet_${startDate}_${endDate}.csv`

  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export default api
