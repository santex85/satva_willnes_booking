import React, { useState, useEffect, useCallback } from 'react'
import { 
  Calendar as CalendarIcon, 
  Users, 
  FileText, 
  Settings as SettingsIcon, 
  TrendingUp, 
  DollarSign, 
  Clock, 
  CheckCircle, 
  Lock, 
  LogOut, 
  Menu, 
  ChevronRight, 
  Activity, 
  User, 
  MapPin, 
  ShieldAlert, 
  Phone,
  Plus,
  BarChart3,
  Download,
  GitMerge,
  Star,
  Quote
} from 'lucide-react'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import {
  loadSession,
  saveSession,
  clearSession,
  login as apiLogin,
  logout as apiLogout,
  getBookings,
  createBooking,
  updateBooking,
  deleteBooking,
  getGuests,
  createGuest,
  getSpecialists,
  getCabinets,
  getServiceVariants,
  getServicePopularity,
  getSpecialistLoad,
  getGuestStatistics,
  mergeGuests,
  downloadCsvReport,
  getSoapNotes,
  createSoapNote,
  updateSoapNote,
  registerSalon,
} from './api'

import './App.css'

const BOOKING_STATUS_COLORS = {
  paid: { backgroundColor: '#0d9488', borderColor: '#0f766e', label: 'ОПЛАЧЕНО' },
  confirmed: { backgroundColor: '#f59e0b', borderColor: '#d97706', label: 'ПОДТВЕРЖДЕНО' },
  unconfirmed: { backgroundColor: '#64748b', borderColor: '#475569', label: 'НЕ ПОДТВЕРЖДЕНО' },
  completed: { backgroundColor: '#2563eb', borderColor: '#1d4ed8', label: 'ВЫПОЛНЕНО' },
}

const CHART_COLORS = ['#0d9488', '#f59e0b', '#8b5cf6', '#ef4444', '#3b82f6', '#10b981', '#f97316']

const buildBookingTitle = (guestName, specialist, service, duration) => {
  const nameParts = (guestName || 'Гость').trim().split(/\s+/)
  const shortGuest = nameParts.length > 1
    ? `${nameParts[0]} ${nameParts[1][0]}.`
    : nameParts[0]
  const shortSpecialist = (specialist || 'Мастер').split(' ')[0]
  const shortService = (service || 'Услуга').split(' ')[0]
  return `${shortGuest} - ${shortSpecialist} (${shortService} ${duration})`
}

const mapBookingToFcEvent = (booking) => {
  const statusMeta = BOOKING_STATUS_COLORS[booking.status] || BOOKING_STATUS_COLORS.confirmed
  const guestName = booking.guest_display_name || booking.guest_name || 'Гость'
  const specialistName = booking.specialist_name || ''
  const serviceName = booking.service_name || ''
  const duration = booking.service_duration || 60

  return {
    id: String(booking.id),
    title: buildBookingTitle(guestName, specialistName, serviceName, duration),
    start: booking.start_time,
    end: booking.end_time,
    backgroundColor: statusMeta.backgroundColor,
    borderColor: statusMeta.borderColor,
    extendedProps: {
      guestId: booking.guest,
      guestName,
      room: booking.guest_room_number || '',
      specialistId: booking.specialist,
      specialist: specialistName,
      cabinetId: booking.cabinet,
      cabinet: booking.cabinet_name || '',
      serviceVariantId: booking.service_variant,
      service: serviceName,
      duration,
      status: booking.status,
      comment: booking.comment || '',
    },
  }
}

const formatDateTimeLocal = (value) => {
  const date = value instanceof Date ? value : new Date(value)
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const normalizeCalendarEvent = (fcEvent) => ({
  id: String(fcEvent.id),
  title: fcEvent.title,
  start: fcEvent.start instanceof Date ? fcEvent.start.toISOString() : fcEvent.startStr || fcEvent.start,
  end: fcEvent.end instanceof Date ? fcEvent.end.toISOString() : fcEvent.endStr || fcEvent.end,
  backgroundColor: fcEvent.backgroundColor,
  borderColor: fcEvent.borderColor,
  extendedProps: { ...(fcEvent.extendedProps || {}) },
})

const defaultReportStart = () => {
  const d = new Date()
  d.setDate(d.getDate() - 30)
  return d.toISOString().slice(0, 10)
}

const defaultReportEnd = () => new Date().toISOString().slice(0, 10)

export default function App() {
  const savedSession = loadSession()

  const [view, setView] = useState(savedSession?.access ? 'app' : (savedSession?.view || 'landing'))
  const [activeTab, setActiveTab] = useState(savedSession?.activeTab || 'calendar')

  const [tenantName, setTenantName] = useState(savedSession?.tenantName || 'Satva Samui Retreat & Spa')
  const [isLogged, setIsLogged] = useState(Boolean(savedSession?.access))
  const [username, setUsername] = useState(savedSession?.username || 'admin')
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState('')
  const [appLoading, setAppLoading] = useState(false)
  const [appError, setAppError] = useState('')

  const [avgPrice, setAvgPrice] = useState(3500)
  const [monthlyBookings, setMonthlyBookings] = useState(150)

  const [isModalOpen, setIsModalOpen] = useState(false)
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [modalMode, setModalMode] = useState('view')
  const [editForm, setEditForm] = useState(null)
  const [savingBooking, setSavingBooking] = useState(false)
  const [featuresTab, setFeaturesTab] = useState('f-calendar')

  const [selectedSoapGuestId, setSelectedSoapGuestId] = useState('')
  const [currentSoapNoteId, setCurrentSoapNoteId] = useState(null)

  const [selectedBodyParts, setSelectedBodyParts] = useState({
    head: false,
    neck: false,
    shoulders: false,
    thoracic: false,
    lumbar: false,
    legs: false
  })
  const [soapData, setSoapData] = useState({
    subjective: '',
    objective: '',
    assessment: '',
    plan: ''
  })

  const [cabinets, setCabinets] = useState([])
  const [specialists, setSpecialists] = useState([])
  const [serviceVariants, setServiceVariants] = useState([])
  const [clients, setClients] = useState([])
  const [newClientName, setNewClientName] = useState('')
  const [newClientRoom, setNewClientRoom] = useState('')
  const [newClientPhone, setNewClientPhone] = useState('')

  const [calendarEvents, setCalendarEvents] = useState([])

  const [reportStart, setReportStart] = useState(defaultReportStart())
  const [reportEnd, setReportEnd] = useState(defaultReportEnd())
  const [reportSpecialistId, setReportSpecialistId] = useState('')
  const [servicePopularity, setServicePopularity] = useState([])
  const [specialistLoad, setSpecialistLoad] = useState([])
  const [guestStats, setGuestStats] = useState([])
  const [reportsLoading, setReportsLoading] = useState(false)
  const [reportsError, setReportsError] = useState('')
  const [csvDownloading, setCsvDownloading] = useState(false)
  const [mergeModalOpen, setMergeModalOpen] = useState(false)
  const [mergePrimary, setMergePrimary] = useState(null)
  const [mergeSelectedIds, setMergeSelectedIds] = useState([])
  const [mergeDisplayName, setMergeDisplayName] = useState('')
  const [mergeLoading, setMergeLoading] = useState(false)
  const [mergeError, setMergeError] = useState('')

  // Onboarding Wizard States & Handlers
  const [wizardStep, setWizardStep] = useState(0) // 0 - landing/no wizard, 1..4 - onboarding steps
  const [onboardingData, setOnboardingData] = useState({
    name: '',
    subdomain: '',
    email: '',
    password: '',
    cabinets: ['Массажный кабинет Бали', 'VIP Спа-зона с джакузи'],
    services: ['massage', 'facial', 'aromatherapy'],
  })
  const [onboardingLoading, setOnboardingLoading] = useState(false)
  const [onboardingError, setOnboardingError] = useState('')
  const [onboardingResult, setOnboardingResult] = useState(null)

  const handleRegisterSalon = async (e) => {
    if (e) e.preventDefault()
    setOnboardingLoading(true)
    setOnboardingError('')
    try {
      const res = await registerSalon(onboardingData)
      setOnboardingResult(res)
      setWizardStep(4) // Успех
    } catch (err) {
      setOnboardingError(err.response?.data?.error || err.message || 'Ошибка регистрации салона')
      setWizardStep(1) // Вернуть на Шаг 1 для исправления ошибок
    } finally {
      setOnboardingLoading(false)
    }
  }

  // ROI Calculations
  const standardNoShowRate = 0.15 // 15%
  const satvaNoShowRate = 0.08    // 8% (46% reduction with WhatsApp/SMS)
  const currentLostRevenue = Math.round(monthlyBookings * standardNoShowRate * avgPrice)
  const satvaLostRevenue = Math.round(monthlyBookings * satvaNoShowRate * avgPrice)
  const savedRevenue = currentLostRevenue - satvaLostRevenue
  const monthlySubscription = 5000 // 5,000 rubles
  const netROI = savedRevenue - monthlySubscription

  const loadBookings = useCallback(async () => {
    const bookings = await getBookings()
    setCalendarEvents(bookings.map(mapBookingToFcEvent))
  }, [])

  const loadGuests = useCallback(async () => {
    const guests = await getGuests()
    setClients(guests.map((g) => ({
      id: g.id,
      name: g.display_name,
      room: '—',
      phone: '—',
      visits: g.booking_count ?? g.total_visits ?? 0,
      status: (g.booking_count ?? g.total_visits ?? 0) >= 10 ? 'VIP' : 'Гость',
      totalAmount: g.total_amount,
      lastVisit: g.last_visit,
    })))
  }, [])

  const loadReferenceData = useCallback(async () => {
    const [specs, cabs, variants] = await Promise.all([
      getSpecialists(),
      getCabinets(),
      getServiceVariants(),
    ])
    setSpecialists(specs.map((s) => ({
      id: s.id,
      name: s.full_name,
      services: (s.services_can_perform || []).join(', '),
    })))
    setCabinets(cabs.map((c) => ({
      id: c.id,
      name: c.name,
      type: c.cabinet_type_name || '',
    })))
    setServiceVariants(variants)
  }, [])

  const loadAppData = useCallback(async () => {
    setAppLoading(true)
    setAppError('')
    try {
      await Promise.all([loadBookings(), loadGuests(), loadReferenceData()])
    } catch (err) {
      setAppError(err.response?.data?.detail || err.message || 'Ошибка загрузки данных')
      if (err.response?.status === 401) {
        apiLogout()
        setIsLogged(false)
        setView('login')
      }
    } finally {
      setAppLoading(false)
    }
  }, [loadBookings, loadGuests, loadReferenceData])

  const loadReports = useCallback(async () => {
    setReportsLoading(true)
    setReportsError('')
    try {
      const params = {
        startDate: reportStart,
        endDate: reportEnd,
        specialistId: reportSpecialistId || undefined,
      }
      const [popularity, load, stats] = await Promise.all([
        getServicePopularity(params),
        getSpecialistLoad(params),
        getGuestStatistics(params),
      ])
      setServicePopularity(popularity)
      setSpecialistLoad(load)
      setGuestStats(stats)
    } catch (err) {
      setReportsError(err.response?.data?.detail || err.message || 'Ошибка загрузки отчётов')
    } finally {
      setReportsLoading(false)
    }
  }, [reportStart, reportEnd, reportSpecialistId])

  useEffect(() => {
    if (isLogged) {
      saveSession({
        ...loadSession(),
        access: loadSession()?.access,
        refresh: loadSession()?.refresh,
        view: 'app',
        username,
        tenantName,
        activeTab,
      })
    }
  }, [isLogged, username, tenantName, activeTab])

  useEffect(() => {
    if (isLogged && view === 'app') {
      loadAppData()
    }
  }, [isLogged, view, loadAppData])

  useEffect(() => {
    if (isLogged && activeTab === 'reports') {
      loadReports()
    }
  }, [isLogged, activeTab, loadReports])

  const handleLogout = () => {
    apiLogout()
    setIsLogged(false)
    setView('landing')
    setActiveTab('calendar')
    setCalendarEvents([])
    setClients([])
  }

  const handleLogin = async (e) => {
    e.preventDefault()
    setLoginError('')
    try {
      const tokens = await apiLogin(username, password)
      saveSession({
        access: tokens.access,
        refresh: tokens.refresh,
        username,
        tenantName,
        activeTab: 'calendar',
        view: 'app',
      })
      setIsLogged(true)
      setView('app')
      setPassword('')
    } catch (err) {
      setLoginError(
        err.response?.data?.detail
        || 'Неверный логин или пароль. Используйте учётную запись Django (admin / admin12345).'
      )
    }
  }

  const buildEditFormFromEvent = (event) => {
    const props = event?.extendedProps || {}
    return {
      guestId: props.guestId || '',
      guestName: props.guestName || '',
      room: props.room || '',
      specialistId: props.specialistId || specialists[0]?.id || '',
      specialist: props.specialist || specialists[0]?.name || '',
      cabinetId: props.cabinetId || cabinets[0]?.id || '',
      cabinet: props.cabinet || cabinets[0]?.name || '',
      serviceVariantId: props.serviceVariantId || serviceVariants[0]?.id || '',
      service: props.service || '',
      duration: props.duration || 60,
      status: props.status || 'confirmed',
      comment: props.comment || '',
      startLocal: formatDateTimeLocal(event.start),
    }
  }

  const handleEventClick = (info) => {
    if (isModalOpen) return
    info.jsEvent?.preventDefault()
    info.jsEvent?.stopPropagation()
    const normalized = normalizeCalendarEvent(info.event)
    setSelectedEvent(normalized)
    setEditForm(buildEditFormFromEvent(normalized))
    setModalMode('view')
    setIsModalOpen(true)
  }

  const handleDateSelect = (selectInfo) => {
    const calendarApi = selectInfo.view.calendar
    calendarApi.unselect()

    const newForm = {
      guestId: clients[0]?.id || '',
      guestName: clients[0]?.name || '',
      room: '',
      specialistId: specialists[0]?.id || '',
      specialist: specialists[0]?.name || '',
      cabinetId: cabinets[0]?.id || '',
      cabinet: cabinets[0]?.name || '',
      serviceVariantId: serviceVariants[0]?.id || '',
      service: serviceVariants[0]?.service_name || '',
      duration: serviceVariants[0]?.duration_minutes || 60,
      status: 'confirmed',
      comment: '',
      startLocal: formatDateTimeLocal(selectInfo.start),
    }

    setSelectedEvent({
      id: 'new',
      start: selectInfo.start,
      extendedProps: {
        guestId: '',
        guestName: '',
        room: '',
        specialistId: specialists[0]?.id || '',
        specialist: specialists[0]?.name || '',
        cabinetId: cabinets[0]?.id || '',
        cabinet: cabinets[0]?.name || '',
        serviceVariantId: serviceVariants[0]?.id || '',
        service: '',
        duration: 60,
        status: 'confirmed',
        comment: '',
      }
    })
    setEditForm(newForm)
    setModalMode('edit')
    setIsModalOpen(true)
  }

  const closeBookingModal = () => {
    setIsModalOpen(false)
    setModalMode('view')
    setEditForm(null)
    setSelectedEvent(null)
  }

  const startEditBooking = () => {
    if (!selectedEvent || !editForm) return
    setModalMode('edit')
  }

  const handleSaveBooking = async (e) => {
    e.preventDefault()
    if (!editForm) return
    setSavingBooking(true)
    try {
      const payload = {
        guest: editForm.guestId ? Number(editForm.guestId) : null,
        guest_name: editForm.guestName,
        guest_room_number: editForm.room,
        specialist: Number(editForm.specialistId),
        cabinet: Number(editForm.cabinetId),
        service_variant: Number(editForm.serviceVariantId),
        start_time: new Date(editForm.startLocal).toISOString(),
        status: editForm.status,
        comment: editForm.comment,
      }

      if (selectedEvent && selectedEvent.id !== 'new') {
        await updateBooking(selectedEvent.id, payload)
      } else {
        await createBooking(payload)
      }
      await loadBookings()
      closeBookingModal()
    } catch (err) {
      setAppError(err.response?.data ? JSON.stringify(err.response.data) : err.message)
    } finally {
      setSavingBooking(false)
    }
  }

  const handleDeleteBooking = async () => {
    if (!selectedEvent || selectedEvent.id === 'new') return
    if (!window.confirm('Вы уверены, что хотите отменить это бронирование?')) return
    
    setSavingBooking(true)
    try {
      await deleteBooking(selectedEvent.id)
      await loadBookings()
      closeBookingModal()
    } catch (err) {
      setAppError(err.response?.data ? JSON.stringify(err.response.data) : err.message)
    } finally {
      setSavingBooking(false)
    }
  }

  const handleLoadSoapNotes = useCallback(async (guestId) => {
    if (!guestId) {
      setCurrentSoapNoteId(null)
      setSoapData({ subjective: '', objective: '', assessment: '', plan: '' })
      setSelectedBodyParts({ head: false, neck: false, shoulders: false, thoracic: false, lumbar: false, legs: false })
      return
    }
    try {
      const notes = await getSoapNotes(guestId)
      if (notes && notes.length > 0) {
        const latest = notes[0]
        setCurrentSoapNoteId(latest.id)
        setSoapData({
          subjective: latest.subjective || '',
          objective: latest.objective || '',
          assessment: latest.assessment || '',
          plan: latest.plan || '',
        })
        setSelectedBodyParts(latest.body_map_data || {
          head: false, neck: false, shoulders: false, thoracic: false, lumbar: false, legs: false
        })
      } else {
        setCurrentSoapNoteId(null)
        setSoapData({ subjective: '', objective: '', assessment: '', plan: '' })
        setSelectedBodyParts({ head: false, neck: false, shoulders: false, thoracic: false, lumbar: false, legs: false })
      }
    } catch (err) {
      console.error('Error loading SOAP notes:', err)
    }
  }, [specialists])

  const handleSaveSoapNote = async () => {
    if (!selectedSoapGuestId) {
      alert('Пожалуйста, выберите гостя для сохранения SOAP-карты')
      return
    }
    
    const specialistId = specialists[0]?.id
    if (!specialistId) {
      alert('Не найдены специалисты для создания SOAP-карты. Пожалуйста, создайте специалиста в админ-панели.')
      return
    }

    const payload = {
      guest: Number(selectedSoapGuestId),
      specialist: Number(specialistId),
      subjective: soapData.subjective,
      objective: soapData.objective,
      assessment: soapData.assessment,
      plan: soapData.plan,
      body_map_data: selectedBodyParts,
    }

    try {
      if (currentSoapNoteId) {
        await updateSoapNote(currentSoapNoteId, payload)
        alert('SOAP-карта гостя успешно обновлена на сервере!')
      } else {
        const newNote = await createSoapNote(payload)
        setCurrentSoapNoteId(newNote.id)
        alert('Новая SOAP-карта гостя успешно создана на сервере!')
      }
    } catch (err) {
      alert('Ошибка сохранения SOAP-карты: ' + (err.response?.data ? JSON.stringify(err.response.data) : err.message))
    }
  }

  const handleAddClient = async (e) => {
    e.preventDefault()
    if (!newClientName) return
    try {
      await createGuest({ display_name: newClientName.trim() })
      setNewClientName('')
      setNewClientRoom('')
      setNewClientPhone('')
      await loadGuests()
    } catch (err) {
      setAppError(err.response?.data?.display_name?.[0] || err.message || 'Ошибка создания гостя')
    }
  }

  const handleDownloadCsv = async () => {
    setCsvDownloading(true)
    try {
      await downloadCsvReport({
        startDate: reportStart,
        endDate: reportEnd,
        specialistId: reportSpecialistId || undefined,
      })
    } catch (err) {
      setReportsError(err.message || 'Ошибка скачивания CSV')
    } finally {
      setCsvDownloading(false)
    }
  }

  const openMergeModal = (guestStat) => {
    if (!guestStat.guest_id) return
    setMergePrimary(guestStat)
    setMergeDisplayName(guestStat.guest_name)
    setMergeSelectedIds([])
    setMergeError('')
    setMergeModalOpen(true)
  }

  const toggleMergeDuplicate = (guestId) => {
    setMergeSelectedIds((prev) =>
      prev.includes(guestId)
        ? prev.filter((id) => id !== guestId)
        : [...prev, guestId]
    )
  }

  const handleMergeGuests = async () => {
    if (!mergePrimary?.guest_id || mergeSelectedIds.length === 0) return
    setMergeLoading(true)
    setMergeError('')
    try {
      await mergeGuests({
        primaryId: mergePrimary.guest_id,
        duplicateIds: mergeSelectedIds,
        primaryDisplayName: mergeDisplayName,
      })
      setMergeModalOpen(false)
      await Promise.all([loadGuests(), loadReports()])
    } catch (err) {
      setMergeError(err.response?.data?.error || err.message || 'Ошибка объединения')
    } finally {
      setMergeLoading(false)
    }
  }

  const mergeCandidates = clients.filter(
    (c) => c.id !== mergePrimary?.guest_id && c.name.toLowerCase().includes((mergePrimary?.guest_name || '').split(' ')[0]?.toLowerCase() || '')
  )

  const toggleBodyPart = (part) => {
    setSelectedBodyParts({
      ...selectedBodyParts,
      [part]: !selectedBodyParts[part]
    })
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      
      {/* WIZARD ONBOARDING VIEW */}
      {wizardStep > 0 && (
        <div style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'radial-gradient(circle at center, rgba(13, 148, 136, 0.08) 0%, transparent 70%)',
          padding: '40px 20px',
        }} className="fade-in">
          
          <div className="glass-card" style={{ padding: '40px', width: '100%', maxWidth: '640px', position: 'relative' }}>
            
            {/* Header progress bar */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Activity size={20} color="hsl(var(--primary))" />
                <span style={{ fontSize: '1rem', fontWeight: 800, fontFamily: 'var(--font-title)' }}>
                  SATVA<span style={{ color: 'hsl(var(--primary))' }}>ONBOARDING</span>
                </span>
              </div>
              <button 
                onClick={() => setWizardStep(0)}
                style={{ background: 'transparent', border: 'none', color: 'hsl(var(--text-secondary))', cursor: 'pointer', fontSize: '0.9rem' }}
              >
                Отмена
              </button>
            </div>

            {/* Stepper indicators */}
            {wizardStep < 4 && (
              <div style={{ display: 'flex', gap: '10px', marginBottom: '40px' }}>
                {[1, 2, 3].map((step) => (
                  <div key={step} style={{
                    flex: 1,
                    height: '4px',
                    borderRadius: '2px',
                    background: step <= wizardStep ? 'hsl(var(--primary))' : 'hsl(var(--border))',
                    transition: 'all 0.3s ease'
                  }}></div>
                ))}
              </div>
            )}

            {/* STEP 1: ACCOUNT DETAILS */}
            {wizardStep === 1 && (
              <div className="fade-in">
                <h2 style={{ fontSize: '1.75rem', color: 'white', marginBottom: '10px' }}>Создайте ваш велнес-объект</h2>
                <p style={{ fontSize: '0.9rem', color: 'hsl(var(--text-secondary))', marginBottom: '30px' }}>Заполните основные данные о вашем спа-салоне или отеле для автоматического развертывания системы.</p>
                
                <form onSubmit={(e) => { e.preventDefault(); setWizardStep(2); }}>
                  <div className="form-group">
                    <label className="form-label">Название спа-салона или отеля</label>
                    <input 
                      type="text" 
                      className="form-input" 
                      placeholder="Напр. Lotus Wellness & Spa" 
                      value={onboardingData.name}
                      onChange={(e) => setOnboardingData({
                        ...onboardingData,
                        name: e.target.value,
                        subdomain: onboardingData.subdomain || e.target.value.toLowerCase().replace(/[^a-z0-9]/g, '-')
                      })}
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Адрес субдомена (латиница)</label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <input 
                        type="text" 
                        className="form-input" 
                        style={{ flex: 1 }}
                        placeholder="lotus-spa" 
                        value={onboardingData.subdomain}
                        onChange={(e) => setOnboardingData({ ...onboardingData, subdomain: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') })}
                        required
                      />
                      <span style={{ color: 'hsl(var(--text-secondary))', fontSize: '0.9rem', fontFamily: 'monospace' }}>.localhost:8002</span>
                    </div>
                    <span style={{ fontSize: '0.75rem', color: 'hsl(var(--text-secondary))' }}>По этому адресу будет доступен ваш изолированный личный кабинет.</span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                    <div className="form-group">
                      <label className="form-label">Email администратора</label>
                      <input 
                        type="email" 
                        className="form-input" 
                        placeholder="admin@hotel.com" 
                        value={onboardingData.email}
                        onChange={(e) => setOnboardingData({ ...onboardingData, email: e.target.value })}
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Пароль администратора</label>
                      <input 
                        type="password" 
                        className="form-input" 
                        placeholder="Минимум 6 символов" 
                        value={onboardingData.password}
                        onChange={(e) => setOnboardingData({ ...onboardingData, password: e.target.value })}
                        required
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '20px' }}>
                    <button type="submit" className="btn-primary">
                      Продолжить <ChevronRight size={16} />
                    </button>
                  </div>
                </form>
              </div>
            )}

            {/* STEP 2: CABINETS SETUP */}
            {wizardStep === 2 && (
              <div className="fade-in">
                <h2 style={{ fontSize: '1.75rem', color: 'white', marginBottom: '10px' }}>Настройка кабинетов и спа-зон</h2>
                <p style={{ fontSize: '0.9rem', color: 'hsl(var(--text-secondary))', marginBottom: '30px' }}>Укажите спа-кабинеты вашего отеля для интеллектуального распределения броней и предотвращения овербукинга.</p>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '30px' }}>
                  {onboardingData.cabinets.map((cab, idx) => (
                    <div key={idx} style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
                      <input 
                        type="text" 
                        className="form-input" 
                        style={{ flex: 1 }}
                        value={cab}
                        onChange={(e) => {
                          const newCabs = [...onboardingData.cabinets]
                          newCabs[idx] = e.target.value
                          setOnboardingData({ ...onboardingData, cabinets: newCabs })
                        }}
                        placeholder="Название кабинета"
                        required
                      />
                      <button 
                        type="button" 
                        className="btn-secondary" 
                        style={{ padding: '12px', color: '#ef4444', borderColor: 'rgba(239, 68, 68, 0.2)' }}
                        onClick={() => setOnboardingData({ ...onboardingData, cabinets: onboardingData.cabinets.filter((_, i) => i !== idx) })}
                        disabled={onboardingData.cabinets.length <= 1}
                      >
                        Удалить
                      </button>
                    </div>
                  ))}
                  
                  <button 
                    type="button" 
                    className="btn-secondary" 
                    style={{ borderStyle: 'dashed', justifyContent: 'center' }}
                    onClick={() => setOnboardingData({ ...onboardingData, cabinets: [...onboardingData.cabinets, `Кабинет ${onboardingData.cabinets.length + 1}`] })}
                  >
                    + Добавить кабинет
                  </button>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '20px' }}>
                  <button type="button" className="btn-secondary" onClick={() => setWizardStep(1)}>
                    Назад
                  </button>
                  <button type="button" className="btn-primary" onClick={() => setWizardStep(3)}>
                    Продолжить <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            )}

            {/* STEP 3: PRE-LOADED SERVICES */}
            {wizardStep === 3 && (
              <div className="fade-in">
                <h2 style={{ fontSize: '1.75rem', color: 'white', marginBottom: '10px' }}>Каталог предустановленных услуг</h2>
                <p style={{ fontSize: '0.9rem', color: 'hsl(var(--text-secondary))', marginBottom: '20px' }}>Выберите спа-услуги, которыми вы хотите наполнить систему. Мы автоматически настроим для них варианты длительности и цен.</p>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '15px', marginBottom: '30px' }}>
                  {[
                    { id: 'massage', title: 'Тайский велнес-массаж', desc: 'Процедуры 60 и 90 минут для оздоровления тела и снятия гипертонуса.' },
                    { id: 'facial', title: 'Премиальный косметологический уход', desc: 'Уходовые спа-процедуры для лица, очищение и лифтинг.' },
                    { id: 'aromatherapy', title: 'Ароматерапия & СПА-ритуал', desc: 'Расслабляющий массаж с ароматическими маслами в VIP кабинетах.' }
                  ].map((srv) => (
                    <label key={srv.id} className="glass-card" style={{ padding: '20px', display: 'flex', gap: '15px', cursor: 'pointer', border: onboardingData.services.includes(srv.id) ? '1px solid hsl(var(--primary))' : '1px solid var(--glass-border)' }}>
                      <input 
                        type="checkbox" 
                        checked={onboardingData.services.includes(srv.id)}
                        style={{ accentColor: 'hsl(var(--primary))', width: '18px', height: '18px', marginTop: '3px' }}
                        onChange={() => {
                          const active = onboardingData.services.includes(srv.id)
                          setOnboardingData({
                            ...onboardingData,
                            services: active 
                              ? onboardingData.services.filter(id => id !== srv.id)
                              : [...onboardingData.services, srv.id]
                          })
                        }}
                      />
                      <div>
                        <h4 style={{ color: 'white', fontSize: '1rem', marginBottom: '4px' }}>{srv.title}</h4>
                        <p style={{ color: 'hsl(var(--text-secondary))', fontSize: '0.8rem' }}>{srv.desc}</p>
                      </div>
                    </label>
                  ))}
                </div>

                {onboardingError && (
                  <div style={{ marginBottom: '20px', padding: '12px 16px', borderRadius: '8px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#fca5a5', fontSize: '0.9rem' }}>
                    {onboardingError}
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '20px' }}>
                  <button type="button" className="btn-secondary" onClick={() => setWizardStep(2)} disabled={onboardingLoading}>
                    Назад
                  </button>
                  <button 
                    type="button" 
                    className="btn-primary" 
                    onClick={handleRegisterSalon}
                    disabled={onboardingLoading || onboardingData.services.length === 0}
                  >
                    {onboardingLoading ? 'Развертывание системы...' : 'Запустить мой СПА-центр 🚀'}
                  </button>
                </div>
              </div>
            )}

            {/* STEP 4: SUCCESS ONBOARDING */}
            {wizardStep === 4 && onboardingResult && (
              <div className="fade-in" style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', gap: '20px', alignItems: 'center', padding: '20px 0' }}>
                <div style={{
                  background: 'rgba(16, 185, 129, 0.1)',
                  width: '60px',
                  height: '60px',
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: '2px solid #10b981',
                  marginBottom: '10px'
                }}>
                  <CheckCircle size={32} color="#10b981" />
                </div>
                
                <h2 style={{ fontSize: '1.75rem', color: 'white' }}>База данных успешно развернута!</h2>
                <p style={{ fontSize: '1rem', color: 'hsl(var(--text-secondary))', maxWidth: '480px' }}>
                  Для вашего спа-отеля создана изолированная схема базы данных и настроен выделенный рабочий домен:
                </p>

                <div style={{
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '12px',
                  padding: '20px',
                  width: '100%',
                  textAlign: 'left',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '10px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Название салона:</span>
                    <strong style={{ color: 'white' }}>{onboardingData.name}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Ваш домен:</span>
                    <a 
                      href={`http://${onboardingResult.domain}:8002`} 
                      style={{ color: 'hsl(var(--primary))', textDecoration: 'underline', fontWeight: 600 }}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {onboardingResult.domain}
                    </a>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Email администратора:</span>
                    <strong style={{ color: 'white' }}>{onboardingData.email}</strong>
                  </div>
                </div>

                <div style={{
                  background: 'rgba(245, 158, 11, 0.1)',
                  border: '1px solid rgba(245, 158, 11, 0.2)',
                  color: '#fbbf24',
                  fontSize: '0.85rem',
                  padding: '12px',
                  borderRadius: '8px',
                  marginTop: '10px',
                  maxWidth: '480px'
                }}>
                  ⚠️ <strong>Важно:</strong> для корректной работы изолированной базы данных по субдоменам на вашем локальном компьютере, перейдите по ссылке выше.
                </div>

                <a 
                  href={`http://${onboardingResult.domain}:8002/`} 
                  className="btn-primary" 
                  style={{ marginTop: '20px', width: '100%', justifyContent: 'center' }}
                >
                  Перейти в личный кабинет <ChevronRight size={16} />
                </a>
              </div>
            )}

          </div>
        </div>
      )}

      {/* LANDING PAGE VIEW */}
      {view === 'landing' && wizardStep === 0 && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }} className="fade-in">
          
          {/* Landing Header */}
          <header style={{
            padding: '20px 40px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            borderBottom: '1px solid hsl(var(--border))',
            background: 'var(--glass-bg)',
            backdropFilter: 'var(--glass-blur)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                background: 'hsl(var(--primary))',
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <Activity size={18} color="white" />
              </div>
              <span style={{ fontSize: '1.25rem', fontFamily: 'var(--font-title)', fontWeight: 800, letterSpacing: '0.05em' }}>
                SATVA<span style={{ color: 'hsl(var(--primary))' }}>WELLNESS</span>
              </span>
            </div>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button className="btn-secondary" onClick={() => setView('login')}>
                <Lock size={16} /> Войти
              </button>
              <button className="btn-primary" onClick={() => setWizardStep(1)}>
                Регистрация салона
              </button>
            </div>
          </header>

          {/* Hero section */}
          <main style={{ flex: 1, maxWidth: '1200px', margin: '0 auto', padding: '60px 20px', width: '100%' }}>
            
            <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '60px', alignItems: 'center', marginBottom: '80px' }}>
              <div>
                <span style={{
                  background: 'hsl(var(--primary) / 10%)',
                  color: 'hsl(var(--primary))',
                  padding: '6px 12px',
                  borderRadius: '20px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  display: 'inline-block',
                  marginBottom: '15px'
                }}>
                  Премиум спа-автоматизация
                </span>
                <h1 style={{ fontSize: '3.5rem', lineHeight: '1.15', marginBottom: '20px', fontWeight: 800 }}>
                  Управляйте вашим спа-отелем на <span style={{
                    background: 'linear-gradient(135deg, hsl(var(--primary)) 0%, #10b981 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent'
                  }}>максимальной</span> скорости
                </h1>
                <p style={{ color: 'hsl(var(--text-secondary))', fontSize: '1.1rem', marginBottom: '30px' }}>
                  Satva Wellness — это первая специализированная B2B SaaS-система для спа-салонов, велнес-клубов и отелей. Уникальный двойной контроль ресурсов: автоматический учет загрузки мастеров, доступности массажных кабинетов и буферного времени уборки.
                </p>
                <div style={{ display: 'flex', gap: '15px' }}>
                  <button className="btn-primary" onClick={() => setWizardStep(1)}>
                    Попробовать бесплатно <ChevronRight size={16} />
                  </button>
                  <a href="#roi-calculator" className="btn-secondary">
                    Рассчитать окупаемость
                  </a>
                </div>
              </div>
              
              {/* Glassmorphic Mockup Container */}
              <div className="glass-card glow-effect" style={{ padding: '30px', position: 'relative' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '1px solid hsl(var(--border))', paddingBottom: '15px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#ef4444' }}></div>
                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#f59e0b' }}></div>
                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#10b981' }}></div>
                  </div>
                  <span style={{ fontSize: '0.8rem', color: 'hsl(var(--text-secondary))' }}>Панель управления Satva SaaS</span>
                </div>
                
                {/* Visual Widget Preview */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ background: 'rgba(255,255,255,0.02)', padding: '15px', borderRadius: '8px', border: '1px solid hsl(var(--border))', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <h4 style={{ fontSize: '0.9rem', color: 'white' }}>Тайский массаж (90 мин)</h4>
                      <p style={{ fontSize: '0.8rem', color: 'hsl(var(--text-secondary))' }}>Гость: Александр Ч. (Номер 302)</p>
                    </div>
                    <span style={{ fontSize: '0.75rem', padding: '4px 8px', borderRadius: '4px', background: 'hsl(var(--status-paid) / 15%)', color: 'hsl(var(--status-paid))', fontWeight: 600 }}>ОПЛАЧЕНО</span>
                  </div>
                  
                  <div style={{ background: 'rgba(255,255,255,0.02)', padding: '15px', borderRadius: '8px', border: '1px solid hsl(var(--border))', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <h4 style={{ fontSize: '0.9rem', color: 'white' }}>Антистресс уход (60 мин)</h4>
                      <p style={{ fontSize: '0.8rem', color: 'hsl(var(--text-secondary))' }}>Гость: Елена С. (Номер 104)</p>
                    </div>
                    <span style={{ fontSize: '0.75rem', padding: '4px 8px', borderRadius: '4px', background: 'hsl(var(--status-confirmed) / 15%)', color: 'hsl(var(--status-confirmed))', fontWeight: 600 }}>ПОДТВЕРЖДЕНО</span>
                  </div>
                  
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginTop: '10px' }}>
                    <div style={{ background: 'rgba(255,255,255,0.02)', padding: '15px', borderRadius: '8px', border: '1px solid hsl(var(--border))', textAlign: 'center' }}>
                      <span style={{ fontSize: '0.75rem', color: 'hsl(var(--text-secondary))' }}>Занятость Кабинетов</span>
                      <h3 style={{ fontSize: '1.5rem', color: 'white', marginTop: '5px' }}>82%</h3>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.02)', padding: '15px', borderRadius: '8px', border: '1px solid hsl(var(--border))', textAlign: 'center' }}>
                      <span style={{ fontSize: '0.75rem', color: 'hsl(var(--text-secondary))' }}>Экономия на неявках</span>
                      <h3 style={{ fontSize: '1.5rem', color: '#10b981', marginTop: '5px' }}>+46,200 ₽</h3>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* INLINE PREMIUM FEATURES WALKTHROUGH */}
            <section className="glass-card" style={{ padding: '40px', marginBottom: '80px' }}>
              <div style={{ textAlign: 'center', marginBottom: '40px' }}>
                <span style={{ color: 'hsl(var(--primary))', fontSize: '0.85rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: '10px' }}>
                  Функционал платформы
                </span>
                <h2 style={{ fontSize: '2rem' }}>Все инструменты управления в одном окне</h2>
              </div>

              {/* Tab headers */}
              <div style={{ display: 'flex', justifyContent: 'center', gap: '15px', marginBottom: '40px' }}>
                {[
                  { id: 'f-calendar', label: 'Интеллектуальный календарь' },
                  { id: 'f-soap', label: 'Анатомические SOAP-карты' },
                  { id: 'f-analytics', label: 'Сквозная аналитика' }
                ].map(tab => (
                  <button 
                    key={tab.id}
                    className="btn-secondary" 
                    style={{ 
                      background: featuresTab === tab.id ? 'hsl(var(--primary) / 10%)' : 'transparent',
                      borderColor: featuresTab === tab.id ? 'hsl(var(--primary))' : 'hsl(var(--border))',
                      color: featuresTab === tab.id ? 'white' : 'hsl(var(--text-secondary))'
                    }}
                    onClick={() => setFeaturesTab(tab.id)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Tab contents */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '40px', alignItems: 'center' }}>
                {featuresTab === 'f-calendar' && (
                  <div className="fade-in">
                    <h3 style={{ fontSize: '1.5rem', color: 'white', marginBottom: '15px' }}>Двухфакторный учет ресурсов</h3>
                    <p style={{ color: 'hsl(var(--text-secondary))', marginBottom: '20px', fontSize: '0.95rem' }}>
                      В отличие от стандартных систем, Satva одновременно проверяет занятость специалиста и доступность нужного кабинета с учетом буферного времени на уборку (15–30 минут).
                    </p>
                    <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '0.9rem', color: 'hsl(var(--text-secondary))' }}>
                      <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Интеллектуальный поиск свободных окон</li>
                      <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Управление сменами и графиками работы</li>
                      <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Функция Drag & Drop для быстрого переноса</li>
                    </ul>
                  </div>
                )}
                {featuresTab === 'f-soap' && (
                  <div className="fade-in">
                    <h3 style={{ fontSize: '1.5rem', color: 'white', marginBottom: '15px' }}>Электронные клинические SOAP-карты</h3>
                    <p style={{ color: 'hsl(var(--text-secondary))', marginBottom: '20px', fontSize: '0.95rem' }}>
                      Уникальный модуль ведения спа-ухода. Специалисты размечают проблемные зоны (гипертонус, спазмы, триггеры) на интерактивном SVG-силуэте тела в реальном времени.
                    </p>
                    <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '0.9rem', color: 'hsl(var(--text-secondary))' }}>
                      <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Запись жалоб (Subjective) и объективных показателей (Objective)</li>
                      <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Хранение истории сеансов в изолированной базе данных</li>
                      <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Анатомическая визуализация для контроля динамики ухода</li>
                    </ul>
                  </div>
                )}
                {featuresTab === 'f-analytics' && (
                  <div className="fade-in">
                    <h3 style={{ fontSize: '1.5rem', color: 'white', marginBottom: '15px' }}>Сквозная B2B-аналитика и экспорт</h3>
                    <p style={{ color: 'hsl(var(--text-secondary))', marginBottom: '20px', fontSize: '0.95rem' }}>
                      Контролируйте загрузку специалистов, популярность услуг по времени суток и выручку. Экспортируйте отчеты в CSV для интеграции с 1С или отельными PMS.
                    </p>
                    <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '0.9rem', color: 'hsl(var(--text-secondary))' }}>
                      <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Расчет эффективности каждого мастера</li>
                      <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Фильтрация по периодам и специалистам</li>
                      <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Готовые графики занятости и посещаемости гостей</li>
                    </ul>
                  </div>
                )}

                <div className="glass-card" style={{ padding: '20px', minHeight: '220px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(255,255,255,0.01)' }}>
                  {featuresTab === 'f-calendar' && (
                    <div style={{ textAlign: 'center', width: '100%' }} className="fade-in">
                      <div style={{ fontSize: '0.75rem', color: 'hsl(var(--primary))', marginBottom: '10px', textTransform: 'uppercase', fontWeight: 600 }}>Двойной контроль конфликтов</div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <div style={{ padding: '10px 15px', borderRadius: '6px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', color: '#fca5a5', fontSize: '0.8rem' }}>
                          ⚠️ Конфликт: Кабинет 1 занят на это время тайским массажем!
                        </div>
                        <div style={{ padding: '10px 15px', borderRadius: '6px', background: 'rgba(16, 185, 129, 0.05)', border: '1px solid #10b981', color: '#a7f3d0', fontSize: '0.8rem' }}>
                          ✓ Рекомендованное время: 12:30 (Специалист Сомбат свободен)
                        </div>
                      </div>
                    </div>
                  )}
                  {featuresTab === 'f-soap' && (
                    <div style={{ textAlign: 'center' }} className="fade-in">
                      <div style={{ display: 'inline-block', width: '12px', height: '12px', borderRadius: '50%', background: '#ef4444', marginRight: '8px' }}></div>
                      <span style={{ fontSize: '0.85rem', color: 'white' }}>Активный триггер: Лопаточная область (Мышечный спазм)</span>
                      <div style={{ display: 'flex', gap: '5px', justifyContent: 'center', marginTop: '10px' }}>
                        <span style={{ fontSize: '0.7rem', padding: '3px 8px', borderRadius: '4px', background: '#ef4444', color: 'white' }}>S: Боли 8/10</span>
                        <span style={{ fontSize: '0.7rem', padding: '3px 8px', borderRadius: '4px', background: '#3b82f6', color: 'white' }}>O: Гипертонус</span>
                      </div>
                    </div>
                  )}
                  {featuresTab === 'f-analytics' && (
                    <div style={{ width: '100%' }} className="fade-in">
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'hsl(var(--text-secondary))', marginBottom: '5px' }}>
                        <span>Эффективность мастеров (KPI)</span>
                        <span>Выручка</span>
                      </div>
                      <div style={{ height: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', overflow: 'hidden' }}>
                        <div style={{ width: '82%', height: '100%', background: 'hsl(var(--primary))' }}></div>
                      </div>
                      <div style={{ marginTop: '10px', fontSize: '1.25rem', color: 'white', fontWeight: 700 }}>+238,500 ₽ <span style={{ fontSize: '0.8rem', color: '#10b981', fontWeight: 500 }}>▲ 18%</span></div>
                    </div>
                  )}
                </div>
              </div>
            </section>

            {/* Interactive ROI Calculator Section */}
            <section id="roi-calculator" className="glass-card" style={{ padding: '40px', marginBottom: '80px' }}>
              <div style={{ textAlign: 'center', marginBottom: '40px' }}>
                <h2 style={{ fontSize: '2rem', marginBottom: '10px' }}>Калькулятор окупаемости Satva SaaS</h2>
                <p style={{ color: 'hsl(var(--text-secondary))' }}>Узнайте, сколько ваш салон теряет из-за пропущенных записей (no-shows) и сколько сбережет наша СМС/WhatsApp автоматизация.</p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '50px' }}>
                
                {/* Left Side: Sliders */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '25px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                      <span>Средняя стоимость сеанса (массаж/спа):</span>
                      <span style={{ color: 'hsl(var(--primary))' }}>{avgPrice.toLocaleString()} ₽</span>
                    </div>
                    <input 
                      type="range" 
                      min="1000" 
                      max="15000" 
                      step="500" 
                      value={avgPrice} 
                      onChange={(e) => setAvgPrice(Number(e.target.value))}
                      style={{ accentColor: 'hsl(var(--primary))', width: '100%', cursor: 'pointer' }}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                      <span>Количество бронирований в месяц:</span>
                      <span style={{ color: 'hsl(var(--primary))' }}>{monthlyBookings}</span>
                    </div>
                    <input 
                      type="range" 
                      min="20" 
                      max="600" 
                      step="10" 
                      value={monthlyBookings} 
                      onChange={(e) => setMonthlyBookings(Number(e.target.value))}
                      style={{ accentColor: 'hsl(var(--primary))', width: '100%', cursor: 'pointer' }}
                    />
                  </div>
                </div>

                {/* Right Side: Financial Output */}
                <div style={{
                  background: 'rgba(255,255,255,0.02)',
                  borderRadius: '12px',
                  border: '1px solid hsl(var(--border))',
                  padding: '25px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '15px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dashed hsl(var(--border))', paddingBottom: '10px' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Текущие убытки без автонапоминаний (15%):</span>
                    <span style={{ color: '#ef4444', fontWeight: 600 }}>-{currentLostRevenue.toLocaleString()} ₽ / мес</span>
                  </div>
                  
                  <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dashed hsl(var(--border))', paddingBottom: '10px' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Убытки с Satva автонапоминаниями (8%):</span>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>-{satvaLostRevenue.toLocaleString()} ₽ / мес</span>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dashed hsl(var(--border))', paddingBottom: '10px' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Спасенная выручка:</span>
                    <span style={{ color: '#10b981', fontWeight: 600 }}>+{savedRevenue.toLocaleString()} ₽ / мес</span>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'hsl(var(--primary) / 5%)', padding: '15px', borderRadius: '8px', border: '1px solid hsl(var(--primary) / 10%)' }}>
                    <div>
                      <span style={{ display: 'block', fontSize: '0.8rem', color: 'hsl(var(--text-secondary))' }}>Чистый профит (после подписки 5,000 ₽)</span>
                      <span style={{ fontSize: '1.5rem', fontWeight: 800, color: 'hsl(var(--primary))' }}>+{netROI.toLocaleString()} ₽ / мес</span>
                    </div>
                    <div style={{
                      background: '#10b981',
                      color: 'white',
                      padding: '4px 10px',
                      borderRadius: '12px',
                      fontSize: '0.75rem',
                      fontWeight: 600
                    }}>
                      ROI &gt; {Math.round((savedRevenue / monthlySubscription) * 100)}%
                    </div>
                  </div>
                </div>

              </div>
            </section>

            {/* Pricing Section */}
            <section style={{ marginBottom: '40px' }}>
              <div style={{ textAlign: 'center', marginBottom: '40px' }}>
                <h2 style={{ fontSize: '2rem', marginBottom: '10px' }}>Прозрачные тарифы без скрытых переплат</h2>
                <p style={{ color: 'hsl(var(--text-secondary))' }}>Выберите оптимальный тариф для вашего велнес-бизнеса.</p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '30px' }}>
                
                {/* Plan 1 */}
                <div className="glass-card" style={{ padding: '30px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  <div>
                    <h3 style={{ fontSize: '1.25rem', color: 'white', marginBottom: '5px' }}>Тариф «Студия»</h3>
                    <p style={{ fontSize: '0.8rem', color: 'hsl(var(--text-secondary))' }}>Для небольших массажных студий</p>
                  </div>
                  <div style={{ fontSize: '2rem', fontWeight: 800, color: 'white' }}>
                    2 500 ₽ <span style={{ fontSize: '1rem', fontWeight: 400, color: 'hsl(var(--text-secondary))' }}>/ мес</span>
                  </div>
                  <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.85rem', color: 'hsl(var(--text-secondary))' }}>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> До 3 мастеров</li>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Учет 2 кабинетов</li>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Интерактивный календарь</li>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> СМС-уведомления</li>
                  </ul>
                  <button className="btn-secondary" style={{ marginTop: 'auto', width: '100%', justifyContent: 'center' }} onClick={() => setWizardStep(1)}>
                    Выбрать тариф
                  </button>
                </div>

                {/* Plan 2: Best Value */}
                <div className="glass-card glow-effect" style={{ padding: '30px', display: 'flex', flexDirection: 'column', gap: '20px', border: '1px solid hsl(var(--primary))' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <h3 style={{ fontSize: '1.25rem', color: 'white', marginBottom: '5px' }}>Тариф «Премиум Спа»</h3>
                      <p style={{ fontSize: '0.8rem', color: 'hsl(var(--text-secondary))' }}>Идеально для крупных спа-центров</p>
                    </div>
                    <span style={{ fontSize: '0.7rem', padding: '3px 8px', borderRadius: '12px', background: 'hsl(var(--primary) / 20%)', color: 'hsl(var(--primary))', fontWeight: 600 }}>ХИТ ПРОДАЖ</span>
                  </div>
                  <div style={{ fontSize: '2rem', fontWeight: 800, color: 'white' }}>
                    5 000 ₽ <span style={{ fontSize: '1rem', fontWeight: 400, color: 'hsl(var(--text-secondary))' }}>/ мес</span>
                  </div>
                  <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.85rem', color: 'hsl(var(--text-secondary))' }}>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Безлимит специалистов</li>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Безлимит кабинетов</li>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> SOAP-карты клиентов</li>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Учет расходников и склад</li>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Интеграция YooKassa / Stripe</li>
                  </ul>
                  <button className="btn-primary" style={{ marginTop: 'auto', width: '100%', justifyContent: 'center' }} onClick={() => setWizardStep(1)}>
                    Начать 14 дней бесплатно
                  </button>
                </div>

                {/* Plan 3 */}
                <div className="glass-card" style={{ padding: '30px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  <div>
                    <h3 style={{ fontSize: '1.25rem', color: 'white', marginBottom: '5px' }}>Тариф «Отель & Курорт»</h3>
                    <p style={{ fontSize: '0.8rem', color: 'hsl(var(--text-secondary))' }}>Для гостиничных сетей и санаториев</p>
                  </div>
                  <div style={{ fontSize: '2rem', fontWeight: 800, color: 'white' }}>
                    15 000 ₽ <span style={{ fontSize: '1rem', fontWeight: 400, color: 'hsl(var(--text-secondary))' }}>/ мес</span>
                  </div>
                  <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.85rem', color: 'hsl(var(--text-secondary))' }}>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Развертывание в Private Cloud</li>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Интеграция с отельными PMS</li>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Кастомный брендинг (White-Label)</li>
                    <li><CheckCircle size={14} color="#10b981" style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Выделенный сервер & SLA 99.9%</li>
                  </ul>
                  <button className="btn-secondary" style={{ marginTop: 'auto', width: '100%', justifyContent: 'center' }} onClick={() => setWizardStep(1)}>
                    Выбрать тариф
                  </button>
                </div>

              </div>
            </section>

            {/* Reviews Section */}
            <section style={{ marginBottom: '60px', marginTop: '60px' }}>
              <div style={{ textAlign: 'center', marginBottom: '40px' }}>
                <span style={{ color: 'hsl(var(--primary))', fontSize: '0.85rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: '10px' }}>
                  Отзывы лидеров индустрии
                </span>
                <h2 style={{ fontSize: '2rem', marginBottom: '10px' }}>Доверие лучших велнес-пространств</h2>
                <p style={{ color: 'hsl(var(--text-secondary))', maxWidth: '600px', margin: '0 auto' }}>
                  Посмотрите, как Satva Wellness помогает автоматизировать рабочие процессы и повышать прибыль премиальным отелям и спа-курортам.
                </p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '30px' }}>
                {/* Review 1 */}
                <div className="glass-card" style={{ padding: '35px', display: 'flex', flexDirection: 'column', gap: '20px', position: 'relative', overflow: 'hidden' }}>
                  <div style={{ position: 'absolute', top: '15px', right: '20px', opacity: 0.05, color: 'hsl(var(--primary))' }}>
                    <Quote size={80} />
                  </div>
                  <div style={{ display: 'flex', gap: '4px', marginBottom: '5px' }}>
                    {[...Array(5)].map((_, i) => (
                      <Star key={i} size={16} fill="hsl(var(--primary))" color="hsl(var(--primary))" />
                    ))}
                  </div>
                  <p style={{ fontSize: '1.05rem', lineHeight: '1.6', color: 'white', fontStyle: 'italic', zIndex: 1 }}>
                    «Переход на Satva Wellness позволил нам полностью исключить накладки в бронировании VIP-кабин. Система двойного учета ресурсов работает безупречно. Загрузка спа выросла на 24% за первые три месяца!»
                  </p>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginTop: '10px', zIndex: 1 }}>
                    <div style={{
                      width: '48px',
                      height: '48px',
                      borderRadius: '50%',
                      background: 'linear-gradient(135deg, hsl(var(--primary)) 0%, hsl(var(--accent)) 100%)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '1.1rem',
                      fontWeight: 700,
                      color: 'white',
                      boxShadow: '0 4px 10px rgba(0,0,0,0.3)'
                    }}>
                      КС
                    </div>
                    <div>
                      <h4 style={{ fontSize: '0.95rem', color: 'white', fontWeight: 600 }}>Ксения Смирнова</h4>
                      <p style={{ fontSize: '0.8rem', color: 'hsl(var(--text-secondary))' }}>Управляющая спа-комплексом, Panviman Chiang Mai Resort</p>
                    </div>
                  </div>
                </div>

                {/* Review 2 */}
                <div className="glass-card" style={{ padding: '35px', display: 'flex', flexDirection: 'column', gap: '20px', position: 'relative', overflow: 'hidden' }}>
                  <div style={{ position: 'absolute', top: '15px', right: '20px', opacity: 0.05, color: 'hsl(var(--primary))' }}>
                    <Quote size={80} />
                  </div>
                  <div style={{ display: 'flex', gap: '4px', marginBottom: '5px' }}>
                    {[...Array(5)].map((_, i) => (
                      <Star key={i} size={16} fill="hsl(var(--primary))" color="hsl(var(--primary))" />
                    ))}
                  </div>
                  <p style={{ fontSize: '1.05rem', lineHeight: '1.6', color: 'white', fontStyle: 'italic', zIndex: 1 }}>
                    «SOAP-карты на планшетах специалистов — это просто космос! Мастера в реальном времени размечают мышечные спазмы гостей, а история ухода автоматически синхронизируется между всеми нашими студиями. Клиенты в восторге от премиального сервиса.»
                  </p>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginTop: '10px', zIndex: 1 }}>
                    <div style={{
                      width: '48px',
                      height: '48px',
                      borderRadius: '50%',
                      background: 'linear-gradient(135deg, #10b981 0%, hsl(var(--primary)) 100%)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '1.1rem',
                      fontWeight: 700,
                      color: 'white',
                      boxShadow: '0 4px 10px rgba(0,0,0,0.3)'
                    }}>
                      АВ
                    </div>
                    <div>
                      <h4 style={{ fontSize: '0.95rem', color: 'white', fontWeight: 600 }}>Артур Вершинин</h4>
                      <p style={{ fontSize: '0.8rem', color: 'hsl(var(--text-secondary))' }}>Основатель сети велнес-пространств Wellness Oasis Sochi</p>
                    </div>
                  </div>
                </div>
              </div>
            </section>

          </main>

          {/* Premium Footer */}
          <footer style={{
            background: 'linear-gradient(to top, rgba(13, 148, 136, 0.04) 0%, rgba(10, 14, 23, 0.95) 100%)',
            borderTop: '1px solid hsl(var(--border))',
            padding: '60px 40px 30px',
            marginTop: 'auto',
            width: '100%'
          }}>
            <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1.5fr', gap: '40px', marginBottom: '40px' }}>
              {/* Brand Col */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div style={{
                    background: 'hsl(var(--primary))',
                    width: '32px',
                    height: '32px',
                    borderRadius: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}>
                    <Activity size={18} color="white" />
                  </div>
                  <span style={{ fontSize: '1.25rem', fontFamily: 'var(--font-title)', fontWeight: 800, letterSpacing: '0.05em' }}>
                    SATVA<span style={{ color: 'hsl(var(--primary))' }}>WELLNESS</span>
                  </span>
                </div>
                <p style={{ color: 'hsl(var(--text-secondary))', fontSize: '0.9rem', lineHeight: '1.6' }}>
                  Интеллектуальная B2B SaaS экосистема для автоматизации спа-салонов, велнес-клубов и санаторно-курортных зон с двойным контролем доступности ресурсов.
                </p>
                <div style={{ display: 'flex', gap: '15px', marginTop: '10px' }}>
                  {['TG', 'IN', 'LN'].map((net) => (
                    <a key={net} href="#" style={{
                      width: '36px',
                      height: '36px',
                      borderRadius: '50%',
                      border: '1px solid hsl(var(--border))',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'hsl(var(--text-secondary))',
                      textDecoration: 'none',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      transition: 'all 0.2s ease'
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'hsl(var(--primary))'; e.currentTarget.style.color = 'white'; e.currentTarget.style.boxShadow = '0 0 10px hsl(var(--primary) / 30%)'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'hsl(var(--border))'; e.currentTarget.style.color = 'hsl(var(--text-secondary))'; e.currentTarget.style.boxShadow = 'none'; }}
                    >
                      {net}
                    </a>
                  ))}
                </div>
              </div>

              {/* Product Col */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
                <h4 style={{ color: 'white', fontSize: '0.95rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Продукт</h4>
                <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.85rem' }}>
                  <li><a href="#" style={{ color: 'hsl(var(--text-secondary))', textDecoration: 'none', transition: 'color 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.color = 'white'} onMouseLeave={(e) => e.currentTarget.style.color = 'hsl(var(--text-secondary))'}>Возможности</a></li>
                  <li><a href="#" style={{ color: 'hsl(var(--text-secondary))', textDecoration: 'none', transition: 'color 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.color = 'white'} onMouseLeave={(e) => e.currentTarget.style.color = 'hsl(var(--text-secondary))'}>SOAP-карты</a></li>
                  <li><a href="#roi-calculator" style={{ color: 'hsl(var(--text-secondary))', textDecoration: 'none', transition: 'color 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.color = 'white'} onMouseLeave={(e) => e.currentTarget.style.color = 'hsl(var(--text-secondary))'}>Калькулятор ROI</a></li>
                  <li><a href="#" style={{ color: 'hsl(var(--text-secondary))', textDecoration: 'none', transition: 'color 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.color = 'white'} onMouseLeave={(e) => e.currentTarget.style.color = 'hsl(var(--text-secondary))'}>Тарифные планы</a></li>
                </ul>
              </div>

              {/* Company Col */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
                <h4 style={{ color: 'white', fontSize: '0.95rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Компания</h4>
                <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.85rem' }}>
                  <li><a href="#" style={{ color: 'hsl(var(--text-secondary))', textDecoration: 'none', transition: 'color 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.color = 'white'} onMouseLeave={(e) => e.currentTarget.style.color = 'hsl(var(--text-secondary))'}>О нас</a></li>
                  <li><a href="#" style={{ color: 'hsl(var(--text-secondary))', textDecoration: 'none', transition: 'color 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.color = 'white'} onMouseLeave={(e) => e.currentTarget.style.color = 'hsl(var(--text-secondary))'}>Блог</a></li>
                  <li><a href="#" style={{ color: 'hsl(var(--text-secondary))', textDecoration: 'none', transition: 'color 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.color = 'white'} onMouseLeave={(e) => e.currentTarget.style.color = 'hsl(var(--text-secondary))'}>Вакансии</a></li>
                  <li><a href="#" style={{ color: 'hsl(var(--text-secondary))', textDecoration: 'none', transition: 'color 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.color = 'white'} onMouseLeave={(e) => e.currentTarget.style.color = 'hsl(var(--text-secondary))'}>Контакты</a></li>
                </ul>
              </div>

              {/* Contacts Col */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
                <h4 style={{ color: 'white', fontSize: '0.95rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Поддержка & Связь</h4>
                <p style={{ color: 'hsl(var(--text-secondary))', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Phone size={14} color="hsl(var(--primary))" /> 8 (800) 555-35-35
                </p>
                <p style={{ color: 'hsl(var(--text-secondary))', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '0.9rem', color: 'hsl(var(--primary))' }}>✉</span> support@satva.wellness
                </p>
                <p style={{ color: 'hsl(var(--text-secondary))', fontSize: '0.8rem', lineHeight: '1.4', marginTop: '5px' }}>
                  Адрес: 119019, г. Москва, ул. Новый Арбат, д. 21, оф. 1040
                </p>
              </div>
            </div>

            <div style={{ maxWidth: '1200px', margin: '0 auto', paddingTop: '25px', borderTop: '1px solid hsl(var(--border))', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8rem', color: 'hsl(var(--text-secondary))' }}>
              <span>© {new Date().getFullYear()} Satva Wellness. Все права защищены.</span>
              <div style={{ display: 'flex', gap: '20px' }}>
                <a href="#" style={{ color: 'hsl(var(--text-secondary))', textDecoration: 'none' }}>Политика конфиденциальности</a>
                <a href="#" style={{ color: 'hsl(var(--text-secondary))', textDecoration: 'none' }}>Условия использования</a>
              </div>
            </div>
          </footer>
        </div>
      )}

      {/* LOGIN PAGE VIEW */}
      {view === 'login' && (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'radial-gradient(circle at center, rgba(13, 148, 136, 0.05) 0%, transparent 60%)' }} className="fade-in">
          <div className="glass-card" style={{ padding: '40px', width: '100%', maxWidth: '400px' }}>
            <div style={{ textAlign: 'center', marginBottom: '30px' }}>
              <div style={{
                background: 'hsl(var(--primary))',
                width: '40px',
                height: '40px',
                borderRadius: '10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 15px'
              }}>
                <Activity size={24} color="white" />
              </div>
              <h2 style={{ fontSize: '1.75rem', color: 'white', marginBottom: '5px' }}>Вход в личный кабинет</h2>
              <p style={{ fontSize: '0.85rem', color: 'hsl(var(--text-secondary))' }}>Satva Wellness B2B SaaS Platform</p>
            </div>

            <form onSubmit={handleLogin}>
              <div className="form-group">
                <label className="form-label">Имя пользователя (Логин)</label>
                <input 
                  type="text" 
                  className="form-input" 
                  value={username} 
                  onChange={(e) => setUsername(e.target.value)} 
                  required 
                />
              </div>

              <div className="form-group">
                <label className="form-label">Пароль</label>
                <input 
                  type="password" 
                  className="form-input" 
                  value={password}
                  placeholder="••••••••"
                  onChange={(e) => setPassword(e.target.value)} 
                  required 
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.85rem', marginBottom: '25px' }}>
                <span style={{ color: 'hsl(var(--text-secondary))', display: 'flex', alignItems: 'center', gap: '5px' }}>
                  <input type="checkbox" style={{ accentColor: 'hsl(var(--primary))' }} /> Запомнить меня
                </span>
                <span style={{ color: 'hsl(var(--primary))', cursor: 'pointer' }}>Забыли пароль?</span>
              </div>

              <button type="submit" className="btn-primary" style={{ width: '100%', justifyContent: 'center' }}>
                Войти в систему
              </button>
              {loginError && (
                <p style={{ color: '#ef4444', fontSize: '0.85rem', marginTop: '12px', textAlign: 'center' }}>
                  {loginError}
                </p>
              )}
            </form>
            
            <button className="btn-secondary" style={{ width: '100%', justifyContent: 'center', marginTop: '10px' }} onClick={() => setView('landing')}>
              Вернуться на главную
            </button>

            <div style={{ textAlign: 'center', marginTop: '20px', fontSize: '0.875rem', color: 'hsl(var(--text-secondary))' }}>
              Хотите подключить свой спа-салон?{' '}
              <span 
                style={{ color: 'hsl(var(--primary))', cursor: 'pointer', fontWeight: 600, textDecoration: 'underline' }} 
                onClick={() => {
                  setView('landing');
                  setWizardStep(1);
                }}
              >
                Зарегистрироваться
              </span>
            </div>
          </div>
        </div>
      )}

      {/* DASHBOARD / MAIN APP VIEW */}
      {view === 'app' && (
        <div style={{ flex: 1, display: 'flex' }} className="fade-in">
          
          {/* Sidebar */}
          <aside style={{
            width: '260px',
            borderRight: '1px solid hsl(var(--border))',
            background: 'rgba(10, 14, 23, 0.8)',
            padding: '25px 20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '30px'
          }}>
            {/* Logo */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                background: 'hsl(var(--primary))',
                width: '28px',
                height: '28px',
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <Activity size={16} color="white" />
              </div>
              <span style={{ fontSize: '1.1rem', fontFamily: 'var(--font-title)', fontWeight: 800, letterSpacing: '0.05em' }}>
                SATVA<span style={{ color: 'hsl(var(--primary))' }}>WELLNESS</span>
              </span>
            </div>

            {/* Navigation links */}
            <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button 
                onClick={() => setActiveTab('calendar')} 
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '12px 16px',
                  borderRadius: '10px',
                  background: activeTab === 'calendar' ? 'hsl(var(--primary) / 10%)' : 'transparent',
                  color: activeTab === 'calendar' ? 'hsl(var(--primary))' : 'hsl(var(--text-secondary))',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontWeight: 500,
                  fontSize: '0.95rem',
                  transition: 'all 0.2s ease'
                }}
              >
                <CalendarIcon size={18} /> Календарь записей
              </button>

              <button 
                onClick={() => setActiveTab('clients')} 
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '12px 16px',
                  borderRadius: '10px',
                  background: activeTab === 'clients' ? 'hsl(var(--primary) / 10%)' : 'transparent',
                  color: activeTab === 'clients' ? 'hsl(var(--primary))' : 'hsl(var(--text-secondary))',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontWeight: 500,
                  fontSize: '0.95rem',
                  transition: 'all 0.2s ease'
                }}
              >
                <Users size={18} /> Клиенты (CRM)
              </button>

              <button 
                onClick={() => setActiveTab('clinical')} 
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '12px 16px',
                  borderRadius: '10px',
                  background: activeTab === 'clinical' ? 'hsl(var(--primary) / 10%)' : 'transparent',
                  color: activeTab === 'clinical' ? 'hsl(var(--primary))' : 'hsl(var(--text-secondary))',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontWeight: 500,
                  fontSize: '0.95rem',
                  transition: 'all 0.2s ease'
                }}
              >
                <FileText size={18} /> Клинические SOAP-карты
              </button>

              <button 
                onClick={() => setActiveTab('reports')} 
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '12px 16px',
                  borderRadius: '10px',
                  background: activeTab === 'reports' ? 'hsl(var(--primary) / 10%)' : 'transparent',
                  color: activeTab === 'reports' ? 'hsl(var(--primary))' : 'hsl(var(--text-secondary))',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontWeight: 500,
                  fontSize: '0.95rem',
                  transition: 'all 0.2s ease'
                }}
              >
                <BarChart3 size={18} /> Отчёты и аналитика
              </button>

              <button 
                onClick={() => setActiveTab('settings')} 
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '12px 16px',
                  borderRadius: '10px',
                  background: activeTab === 'settings' ? 'hsl(var(--primary) / 10%)' : 'transparent',
                  color: activeTab === 'settings' ? 'hsl(var(--primary))' : 'hsl(var(--text-secondary))',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontWeight: 500,
                  fontSize: '0.95rem',
                  transition: 'all 0.2s ease'
                }}
              >
                <SettingsIcon size={18} /> Настройки спа
              </button>
            </nav>

            {/* Profile / Logout Section */}
            <div style={{ marginTop: 'auto', borderTop: '1px solid hsl(var(--border))', paddingTop: '20px', display: 'flex', flexDirection: 'column', gap: '15px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{ width: '36px', height: '36px', borderRadius: '50%', background: 'hsl(var(--border))', display: 'flex', alignItems: 'center', justifycontent: 'center', border: '1px solid rgba(255,255,255,0.1)' }}>
                  <User size={18} style={{ margin: '0 auto' }} />
                </div>
                <div>
                  <h4 style={{ fontSize: '0.85rem', color: 'white', fontWeight: 600 }}>Администратор</h4>
                  <span style={{ fontSize: '0.75rem', color: 'hsl(var(--text-secondary))' }}>Тариф: Премиум спа</span>
                </div>
              </div>
              <button className="btn-secondary" style={{ width: '100%', justifyContent: 'center' }} onClick={handleLogout}>
                <LogOut size={16} /> Выйти
              </button>
            </div>
          </aside>

          {/* Main workspace */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            
            {/* Header */}
            <header style={{
              padding: '20px 40px',
              borderBottom: '1px solid hsl(var(--border))',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              background: 'var(--glass-bg)'
            }}>
              <div>
                <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'hsl(var(--primary))', fontWeight: 600, letterSpacing: '0.05em' }}>Арендатор: {tenantName}</span>
                <h2 style={{ fontSize: '1.25rem', color: 'white', marginTop: '2px' }}>
                  {activeTab === 'calendar' && 'Календарь записей'}
                  {activeTab === 'clients' && 'База гостей и CRM'}
                  {activeTab === 'clinical' && 'SOAP заметки & Разметка тела'}
                  {activeTab === 'reports' && 'Отчёты и аналитика'}
                  {activeTab === 'settings' && 'Настройки спа-салона'}
                </h2>
              </div>
              <div style={{ display: 'flex', gap: '15px' }}>
                <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid hsl(var(--border))', padding: '8px 16px', borderRadius: '8px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Clock size={14} color="hsl(var(--primary))" />
                  <span>Сегодня: 26 мая 2026</span>
                </div>
              </div>
            </header>

            {/* Tab contents */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '40px' }}>

              {appError && (
                <div style={{ marginBottom: '20px', padding: '12px 16px', borderRadius: '8px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#fca5a5', fontSize: '0.9rem' }}>
                  {appError}
                </div>
              )}

              {appLoading && (
                <p style={{ color: 'hsl(var(--text-secondary))', marginBottom: '20px' }}>Загрузка данных...</p>
              )}
              
              {/* TAB 1: CALENDAR VIEW */}
              {activeTab === 'calendar' && (
                <div className="glass-card" style={{ padding: '30px', pointerEvents: isModalOpen ? 'none' : 'auto' }}>
                  <FullCalendar
                    plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
                    initialView="timeGridDay"
                    headerToolbar={{
                      left: 'prev,next today',
                      center: 'title',
                      right: 'timeGridDay,timeGridWeek,dayGridMonth'
                    }}
                    locale="ru"
                    events={calendarEvents}
                    slotMinTime="09:00:00"
                    slotMaxTime="21:00:00"
                    editable={true}
                    selectable={true}
                    selectMirror={true}
                    dayMaxEvents={true}
                    allDaySlot={false}
                    eventClick={handleEventClick}
                    select={handleDateSelect}
                  />
                </div>
              )}

              {/* TAB 2: CLIENTS VIEW */}
              {activeTab === 'clients' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '30px' }}>
                  
                  {/* Add guest form */}
                  <div className="glass-card" style={{ padding: '25px' }}>
                    <h3 style={{ fontSize: '1.1rem', marginBottom: '20px', color: 'white' }}>Добавить нового гостя</h3>
                    <form onSubmit={handleAddClient} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '20px', alignItems: 'end' }}>
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label">ФИО гостя</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          placeholder="Иванов Иван Иванович" 
                          value={newClientName} 
                          onChange={(e) => setNewClientName(e.target.value)} 
                          required 
                        />
                      </div>
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label">Номер комнаты</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          placeholder="Напр. 302" 
                          value={newClientRoom} 
                          onChange={(e) => setNewClientRoom(e.target.value)} 
                        />
                      </div>
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label">Номер телефона</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          placeholder="+7 (___) ___-__-__" 
                          value={newClientPhone} 
                          onChange={(e) => setNewClientPhone(e.target.value)} 
                          required 
                        />
                      </div>
                      <button type="submit" className="btn-primary" style={{ padding: '12px 24px' }}>
                        <Plus size={16} /> Создать
                      </button>
                    </form>
                  </div>

                  {/* Guests list */}
                  <div className="glass-card" style={{ padding: '30px' }}>
                    <h3 style={{ fontSize: '1.1rem', marginBottom: '20px', color: 'white' }}>База зарегистрированных гостей</h3>
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid hsl(var(--border))', color: 'hsl(var(--text-secondary))', fontSize: '0.85rem' }}>
                          <th style={{ padding: '12px 15px' }}>ФИО</th>
                          <th style={{ padding: '12px 15px' }}>Номер комнаты</th>
                          <th style={{ padding: '12px 15px' }}>Телефон</th>
                          <th style={{ padding: '12px 15px' }}>Визитов</th>
                          <th style={{ padding: '12px 15px' }}>Статус</th>
                          <th style={{ padding: '12px 15px' }}>Действия</th>
                        </tr>
                      </thead>
                      <tbody>
                        {clients.map(client => (
                          <tr key={client.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)', fontSize: '0.9rem' }}>
                            <td style={{ padding: '12px 15px', color: 'white', fontWeight: 500 }}>{client.name}</td>
                            <td style={{ padding: '12px 15px' }}>{client.room}</td>
                            <td style={{ padding: '12px 15px', fontFamily: 'monospace' }}>{client.phone}</td>
                            <td style={{ padding: '12px 15px' }}>{client.visits}</td>
                            <td style={{ padding: '12px 15px' }}>
                              <span style={{
                                fontSize: '0.75rem',
                                padding: '3px 8px',
                                borderRadius: '4px',
                                background: client.status === 'VIP' ? 'rgba(139, 92, 246, 0.15)' : 'rgba(255,255,255,0.05)',
                                color: client.status === 'VIP' ? '#8b5cf6' : 'hsl(var(--text-secondary))',
                                fontWeight: 600
                              }}>{client.status}</span>
                            </td>
                            <td style={{ padding: '12px 15px' }}>
                              <button
                                className="btn-secondary"
                                style={{ padding: '6px 12px', fontSize: '0.75rem' }}
                                onClick={() => {
                                  setSelectedSoapGuestId(client.id)
                                  handleLoadSoapNotes(client.id)
                                  setActiveTab('clinical')
                                }}
                              >
                                Открыть SOAP-карту
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                </div>
              )}

              {/* TAB 3: SOAP CLINICAL NOTES VIEW */}
              {activeTab === 'clinical' && (
                <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: '30px' }}>
                  
                  {/* Left Column: Interactive Silhouette */}
                  <div className="glass-card" style={{ padding: '30px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px' }}>
                    <h3 style={{ fontSize: '1.1rem', color: 'white', alignSelf: 'flex-start' }}>Разметка проблемных зон</h3>
                    <p style={{ fontSize: '0.75rem', color: 'hsl(var(--text-secondary))', alignSelf: 'flex-start' }}>Нажмите на зоны для выделения очагов боли/спазма на силуэте:</p>
                    
                    {/* Inline Interactive Anatomical SVG Lineart */}
                    <svg width="240" height="420" viewBox="0 0 200 400" style={{ background: 'rgba(255,255,255,0.01)', borderRadius: '12px', border: '1px solid hsl(var(--border))', padding: '15px' }}>
                      {/* Grid background */}
                      <defs>
                        <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
                          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(255,255,255,0.02)" strokeWidth="1"/>
                        </pattern>
                      </defs>
                      <rect width="100%" height="100%" fill="url(#grid)" />
                      
                      {/* Body silhouette line art */}
                      {/* Head */}
                      <circle 
                        cx="100" cy="45" r="18" 
                        fill={selectedBodyParts.head ? 'rgba(239, 68, 68, 0.4)' : 'rgba(13, 148, 136, 0.1)'} 
                        stroke={selectedBodyParts.head ? '#ef4444' : '#0d9488'} 
                        strokeWidth="1.5"
                        style={{ cursor: 'pointer', transition: 'all 0.2s ease' }}
                        onClick={() => toggleBodyPart('head')}
                      />
                      {/* Neck */}
                      <rect 
                        x="93" y="63" width="14" height="12" 
                        fill={selectedBodyParts.neck ? 'rgba(239, 68, 68, 0.4)' : 'rgba(13, 148, 136, 0.1)'} 
                        stroke={selectedBodyParts.neck ? '#ef4444' : '#0d9488'} 
                        strokeWidth="1.5"
                        style={{ cursor: 'pointer', transition: 'all 0.2s ease' }}
                        onClick={() => toggleBodyPart('neck')}
                      />
                      {/* Shoulders */}
                      <path 
                        d="M 50,75 C 80,75 120,75 150,75 L 140,95 L 60,95 Z" 
                        fill={selectedBodyParts.shoulders ? 'rgba(239, 68, 68, 0.4)' : 'rgba(13, 148, 136, 0.1)'} 
                        stroke={selectedBodyParts.shoulders ? '#ef4444' : '#0d9488'} 
                        strokeWidth="1.5"
                        style={{ cursor: 'pointer', transition: 'all 0.2s ease' }}
                        onClick={() => toggleBodyPart('shoulders')}
                      />
                      {/* Thoracic Back */}
                      <rect 
                        x="62" y="95" width="76" height="50" rx="4"
                        fill={selectedBodyParts.thoracic ? 'rgba(239, 68, 68, 0.4)' : 'rgba(13, 148, 136, 0.1)'} 
                        stroke={selectedBodyParts.thoracic ? '#ef4444' : '#0d9488'} 
                        strokeWidth="1.5"
                        style={{ cursor: 'pointer', transition: 'all 0.2s ease' }}
                        onClick={() => toggleBodyPart('thoracic')}
                      />
                      {/* Lumbar Back (Lower Back) */}
                      <rect 
                        x="68" y="145" width="64" height="40" rx="4"
                        fill={selectedBodyParts.lumbar ? 'rgba(239, 68, 68, 0.4)' : 'rgba(13, 148, 136, 0.1)'} 
                        stroke={selectedBodyParts.lumbar ? '#ef4444' : '#0d9488'} 
                        strokeWidth="1.5"
                        style={{ cursor: 'pointer', transition: 'all 0.2s ease' }}
                        onClick={() => toggleBodyPart('lumbar')}
                      />
                      {/* Legs */}
                      <path 
                        d="M 68,185 L 96,185 L 86,330 L 60,330 Z" 
                        fill={selectedBodyParts.legs ? 'rgba(239, 68, 68, 0.4)' : 'rgba(13, 148, 136, 0.1)'} 
                        stroke={selectedBodyParts.legs ? '#ef4444' : '#0d9488'} 
                        strokeWidth="1.5"
                        style={{ cursor: 'pointer', transition: 'all 0.2s ease' }}
                        onClick={() => toggleBodyPart('legs')}
                      />
                      <path 
                        d="M 104,185 L 132,185 L 140,330 L 114,330 Z" 
                        fill={selectedBodyParts.legs ? 'rgba(239, 68, 68, 0.4)' : 'rgba(13, 148, 136, 0.1)'} 
                        stroke={selectedBodyParts.legs ? '#ef4444' : '#0d9488'} 
                        strokeWidth="1.5"
                        style={{ cursor: 'pointer', transition: 'all 0.2s ease' }}
                        onClick={() => toggleBodyPart('legs')}
                      />
                      
                      <text x="100" y="380" fill="hsl(var(--text-secondary))" fontSize="10" textAnchor="middle">Вид сзади (Шея/Спина/Ноги)</text>
                    </svg>

                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'center' }}>
                      <span style={{ fontSize: '0.75rem', padding: '4px 8px', borderRadius: '4px', background: selectedBodyParts.neck ? '#ef4444' : 'transparent', color: selectedBodyParts.neck ? 'white' : 'hsl(var(--text-secondary))', border: '1px solid' + (selectedBodyParts.neck ? '#ef4444' : 'hsl(var(--border))') }}>Шея</span>
                      <span style={{ fontSize: '0.75rem', padding: '4px 8px', borderRadius: '4px', background: selectedBodyParts.shoulders ? '#ef4444' : 'transparent', color: selectedBodyParts.shoulders ? 'white' : 'hsl(var(--text-secondary))', border: '1px solid' + (selectedBodyParts.shoulders ? '#ef4444' : 'hsl(var(--border))') }}>Плечи</span>
                      <span style={{ fontSize: '0.75rem', padding: '4px 8px', borderRadius: '4px', background: selectedBodyParts.lumbar ? '#ef4444' : 'transparent', color: selectedBodyParts.lumbar ? 'white' : 'hsl(var(--text-secondary))', border: '1px solid' + (selectedBodyParts.lumbar ? '#ef4444' : 'hsl(var(--border))') }}>Поясница</span>
                    </div>
                  </div>

                  {/* Right Column: SOAP Text Forms */}
                  <div className="glass-card" style={{ padding: '30px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <div style={{ borderBottom: '1px solid hsl(var(--border))', paddingBottom: '15px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
                        <h3 style={{ fontSize: '1.25rem', color: 'white' }}>Электронная SOAP карта</h3>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span style={{ fontSize: '0.85rem', color: 'hsl(var(--text-secondary))' }}>Пациент:</span>
                          <select
                            className="form-input"
                            style={{ padding: '6px 12px', background: 'rgba(255,255,255,0.03)', border: '1px solid hsl(var(--border))', borderRadius: '6px', color: 'white', outline: 'none', fontSize: '0.85rem' }}
                            value={selectedSoapGuestId}
                            onChange={(e) => {
                              setSelectedSoapGuestId(e.target.value)
                              handleLoadSoapNotes(e.target.value)
                            }}
                          >
                            <option value="">-- Выберите гостя из базы --</option>
                            {clients.map((c) => (
                              <option key={c.id} value={c.id}>{c.name}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                      <span style={{ fontSize: '0.75rem', color: 'hsl(var(--primary))', fontWeight: 600 }}>
                        {currentSoapNoteId ? 'Карта загружена из БД' : 'Новая запись'}
                      </span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                      <div className="form-group">
                        <label className="form-label" style={{ color: '#f59e0b' }}>S (Subjective) - Жалобы клиента</label>
                        <textarea 
                          rows="4" 
                          className="form-input" 
                          style={{ resize: 'none', background: 'rgba(255,255,255,0.01)', fontSize: '0.85rem' }} 
                          value={soapData.subjective}
                          onChange={(e) => setSoapData({...soapData, subjective: e.target.value})}
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label" style={{ color: '#3b82f6' }}>O (Objective) - Данные осмотра</label>
                        <textarea 
                          rows="4" 
                          className="form-input" 
                          style={{ resize: 'none', background: 'rgba(255,255,255,0.01)', fontSize: '0.85rem' }} 
                          value={soapData.objective}
                          onChange={(e) => setSoapData({...soapData, objective: e.target.value})}
                        />
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                      <div className="form-group">
                        <label className="form-label" style={{ color: '#10b981' }}>A (Assessment) - Оценка специалиста</label>
                        <textarea 
                          rows="4" 
                          className="form-input" 
                          style={{ resize: 'none', background: 'rgba(255,255,255,0.01)', fontSize: '0.85rem' }} 
                          value={soapData.assessment}
                          onChange={(e) => setSoapData({...soapData, assessment: e.target.value})}
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label" style={{ color: '#8b5cf6' }}>P (Plan) - План дальнейшего ухода</label>
                        <textarea 
                          rows="4" 
                          className="form-input" 
                          style={{ resize: 'none', background: 'rgba(255,255,255,0.01)', fontSize: '0.85rem' }} 
                          value={soapData.plan}
                          onChange={(e) => setSoapData({...soapData, plan: e.target.value})}
                        />
                      </div>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '15px' }}>
                      <button className="btn-secondary" onClick={() => window.print()}>Печать карты</button>
                      <button className="btn-primary" onClick={handleSaveSoapNote}>Сохранить изменения</button>
                    </div>
                  </div>

                </div>
              )}

              {/* TAB 4: REPORTS VIEW */}
              {activeTab === 'reports' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '30px' }}>
                  <div className="glass-card" style={{ padding: '25px' }}>
                    <h3 style={{ fontSize: '1.1rem', marginBottom: '20px', color: 'white' }}>Параметры отчёта</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto auto', gap: '16px', alignItems: 'end' }}>
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label">Дата начала</label>
                        <input type="date" className="form-input" value={reportStart} onChange={(e) => setReportStart(e.target.value)} />
                      </div>
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label">Дата окончания</label>
                        <input type="date" className="form-input" value={reportEnd} onChange={(e) => setReportEnd(e.target.value)} />
                      </div>
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label">Специалист (опционально)</label>
                        <select className="form-input" value={reportSpecialistId} onChange={(e) => setReportSpecialistId(e.target.value)}>
                          <option value="">Все специалисты</option>
                          {specialists.map((s) => (
                            <option key={s.id} value={s.id}>{s.name}</option>
                          ))}
                        </select>
                      </div>
                      <button className="btn-primary" onClick={loadReports} disabled={reportsLoading}>
                        {reportsLoading ? 'Загрузка...' : 'Обновить'}
                      </button>
                      <button className="btn-secondary" onClick={handleDownloadCsv} disabled={csvDownloading}>
                        <Download size={16} /> {csvDownloading ? 'Скачивание...' : 'CSV'}
                      </button>
                    </div>
                    {reportsError && (
                      <p style={{ color: '#ef4444', fontSize: '0.85rem', marginTop: '12px' }}>{reportsError}</p>
                    )}
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '30px' }}>
                    <div className="glass-card" style={{ padding: '25px', minHeight: '360px' }}>
                      <h3 style={{ fontSize: '1.1rem', marginBottom: '20px', color: 'white' }}>Популярность услуг</h3>
                      {servicePopularity.length === 0 ? (
                        <p style={{ color: 'hsl(var(--text-secondary))' }}>Нет данных за выбранный период</p>
                      ) : (
                        <ResponsiveContainer width="100%" height={280}>
                          <PieChart>
                            <Pie
                              data={servicePopularity.map((item) => ({ name: item.service_name, value: item.count }))}
                              dataKey="value"
                              nameKey="name"
                              cx="50%"
                              cy="50%"
                              outerRadius={90}
                              label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                            >
                              {servicePopularity.map((_, index) => (
                                <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                              ))}
                            </Pie>
                            <Tooltip />
                            <Legend />
                          </PieChart>
                        </ResponsiveContainer>
                      )}
                    </div>

                    <div className="glass-card" style={{ padding: '25px', minHeight: '360px' }}>
                      <h3 style={{ fontSize: '1.1rem', marginBottom: '20px', color: 'white' }}>Нагрузка специалистов</h3>
                      {specialistLoad.length === 0 ? (
                        <p style={{ color: 'hsl(var(--text-secondary))' }}>Нет данных за выбранный период</p>
                      ) : (
                        <ResponsiveContainer width="100%" height={280}>
                          <BarChart data={specialistLoad.map((item) => ({
                            name: item.specialist_name.split(' ')[0],
                            minutes: item.total_minutes,
                            display: item.total_display,
                          }))}>
                            <XAxis dataKey="name" stroke="hsl(var(--text-secondary))" fontSize={12} />
                            <YAxis stroke="hsl(var(--text-secondary))" fontSize={12} />
                            <Tooltip formatter={(value, _name, props) => [props.payload.display, 'Время']} />
                            <Bar dataKey="minutes" fill="#0d9488" radius={[4, 4, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      )}
                    </div>
                  </div>

                  <div className="glass-card" style={{ padding: '30px' }}>
                    <h3 style={{ fontSize: '1.1rem', marginBottom: '20px', color: 'white' }}>CRM-аналитика гостей</h3>
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid hsl(var(--border))', color: 'hsl(var(--text-secondary))', fontSize: '0.85rem' }}>
                          <th style={{ padding: '12px 15px' }}>Гость</th>
                          <th style={{ padding: '12px 15px' }}>Визиты</th>
                          <th style={{ padding: '12px 15px' }}>Сумма</th>
                          <th style={{ padding: '12px 15px' }}>Средний чек</th>
                          <th style={{ padding: '12px 15px' }}>Время в спа</th>
                          <th style={{ padding: '12px 15px' }}>Первый визит</th>
                          <th style={{ padding: '12px 15px' }}>Последний визит</th>
                          <th style={{ padding: '12px 15px' }}>Действия</th>
                        </tr>
                      </thead>
                      <tbody>
                        {guestStats.map((guest, idx) => (
                          <tr key={guest.guest_id || `${guest.guest_name}-${idx}`} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)', fontSize: '0.9rem' }}>
                            <td style={{ padding: '12px 15px', color: 'white', fontWeight: 500 }}>
                              {guest.guest_name}
                              {guest.is_merged && (
                                <span style={{ marginLeft: '8px', fontSize: '0.7rem', padding: '2px 6px', borderRadius: '4px', background: 'rgba(245,158,11,0.15)', color: '#f59e0b' }}>
                                  склеен
                                </span>
                              )}
                            </td>
                            <td style={{ padding: '12px 15px' }}>{guest.visit_count}</td>
                            <td style={{ padding: '12px 15px' }}>{guest.total_amount} ₽</td>
                            <td style={{ padding: '12px 15px' }}>{guest.avg_check} ₽</td>
                            <td style={{ padding: '12px 15px' }}>{guest.total_duration_display}</td>
                            <td style={{ padding: '12px 15px' }}>{guest.first_visit ? new Date(guest.first_visit).toLocaleDateString('ru-RU') : '—'}</td>
                            <td style={{ padding: '12px 15px' }}>{guest.last_visit ? new Date(guest.last_visit).toLocaleDateString('ru-RU') : '—'}</td>
                            <td style={{ padding: '12px 15px' }}>
                              {guest.guest_id && (
                                <button
                                  className="btn-secondary"
                                  style={{ padding: '6px 12px', fontSize: '0.75rem' }}
                                  onClick={() => openMergeModal(guest)}
                                >
                                  <GitMerge size={12} style={{ marginRight: '4px' }} /> Объединить
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 5: SETTINGS VIEW */}
              {activeTab === 'settings' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '30px' }}>
                  
                  {/* System Settings card */}
                  <div className="glass-card" style={{ padding: '30px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <h3 style={{ fontSize: '1.1rem', color: 'white', borderBottom: '1px solid hsl(var(--border))', paddingBottom: '10px' }}>Глобальные параметры спа</h3>
                    
                    <div className="form-group">
                      <label className="form-label">Название спа-центра</label>
                      <input type="text" className="form-input" value={tenantName} onChange={(e) => setTenantName(e.target.value)} />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                      <div className="form-group">
                        <label className="form-label">Время открытия</label>
                        <input type="time" className="form-input" defaultValue="09:00" />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Время закрытия</label>
                        <input type="time" className="form-input" defaultValue="21:00" />
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                      <div className="form-group">
                        <label className="form-label">Буферное время уборки (мин)</label>
                        <input type="number" className="form-input" defaultValue="15" />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Шаг сетки календаря (мин)</label>
                        <input type="number" className="form-input" defaultValue="15" />
                      </div>
                    </div>

                    <div className="form-group">
                      <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', color: 'white', textTransform: 'none' }}>
                        <input type="checkbox" defaultChecked={true} style={{ accentColor: 'hsl(var(--primary))' }} /> Автоматически отправлять СМС с напоминаниями
                      </label>
                    </div>

                    <button className="btn-primary" onClick={() => alert('Настройки спа успешно сохранены!')}>Сохранить настройки</button>
                  </div>

                  {/* Subscription details card */}
                  <div className="glass-card" style={{ padding: '30px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <h3 style={{ fontSize: '1.1rem', color: 'white', borderBottom: '1px solid hsl(var(--border))', paddingBottom: '10px' }}>Подписка и биллинг</h3>
                    
                    <div style={{ background: 'hsl(var(--primary) / 5%)', border: '1px solid hsl(var(--primary) / 10%)', padding: '20px', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <span style={{ fontSize: '0.8rem', color: 'hsl(var(--text-secondary))' }}>Текущий тарифный план</span>
                        <h4 style={{ fontSize: '1.2rem', color: 'white', fontWeight: 700 }}>Тариф «Премиум Спа»</h4>
                      </div>
                      <div style={{ textHeading: 'right' }}>
                        <span style={{ fontSize: '0.8rem', color: 'hsl(var(--text-secondary))' }}>Ежемесячный платеж</span>
                        <h4 style={{ fontSize: '1.2rem', color: 'white', fontWeight: 700 }}>5 000 ₽</h4>
                      </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.9rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'hsl(var(--text-secondary))' }}>Дата следующего списания:</span>
                        <span style={{ color: 'white', fontWeight: 500 }}>26 июня 2026 г.</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'hsl(var(--text-secondary))' }}>Привязанная карта:</span>
                        <span style={{ color: 'white', fontWeight: 500, fontFamily: 'monospace' }}>•••• •••• •••• 4242 (Stripe/ЮKassa)</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'hsl(var(--text-secondary))' }}>Статус подписки:</span>
                        <span style={{ color: '#10b981', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <CheckCircle size={14} /> Активна
                        </span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '15px', marginTop: 'auto' }}>
                      <button className="btn-secondary" style={{ flex: 1, justifyContent: 'center' }}>Изменить карту</button>
                      <button className="btn-secondary" style={{ flex: 1, justifyContent: 'center', borderColor: '#ef4444', color: '#ef4444' }}>Отменить подписку</button>
                    </div>
                  </div>

                </div>
              )}

            </div>
          </div>
        </div>
      )}

      {/* EVENT DETAIL MODAL OVERLAY */}
      {isModalOpen && selectedEvent && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.6)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            pointerEvents: 'auto',
          }}
          className="fade-in"
        >
          <div
            className="glass-card"
            style={{
              padding: '30px',
              width: '100%',
              maxWidth: modalMode === 'edit' ? '560px' : '500px',
              display: 'flex',
              flexDirection: 'column',
              gap: '20px',
              pointerEvents: 'auto',
            }}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
          >
            
            <div style={{ borderBottom: '1px solid hsl(var(--border))', paddingBottom: '15px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '1.25rem', color: 'white' }}>
                {selectedEvent.id === 'new'
                  ? 'Новая запись'
                  : modalMode === 'edit'
                  ? `Редактирование #${selectedEvent.id}`
                  : `Детали бронирования #${selectedEvent.id}`}
              </h3>
              <button 
                onClick={closeBookingModal}
                style={{ background: 'transparent', border: 'none', color: 'hsl(var(--text-secondary))', cursor: 'pointer', fontSize: '1.5rem', outline: 'none' }}
              >
                &times;
              </button>
            </div>

            <div style={{ display: modalMode === 'view' ? 'block' : 'none' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '0.9rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Имя гостя:</span>
                    <span style={{ color: 'white', fontWeight: 600 }}>{selectedEvent.extendedProps.guestName}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Номер комнаты:</span>
                    <span style={{ color: 'white', fontWeight: 500 }}>{selectedEvent.extendedProps.room}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Специалист спа:</span>
                    <span style={{ color: 'white', fontWeight: 500 }}>{selectedEvent.extendedProps.specialist}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Кабинет:</span>
                    <span style={{ color: 'white', fontWeight: 500 }}>{selectedEvent.extendedProps.cabinet}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Услуга велнес:</span>
                    <span style={{ color: 'white', fontWeight: 500 }}>{selectedEvent.extendedProps.service} ({selectedEvent.extendedProps.duration} мин)</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Время начала:</span>
                    <span style={{ color: 'white', fontWeight: 500 }}>{new Date(selectedEvent.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--text-secondary))' }}>Статус:</span>
                    <span style={{
                      fontSize: '0.75rem',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      background: `${(BOOKING_STATUS_COLORS[selectedEvent.extendedProps.status] || BOOKING_STATUS_COLORS.confirmed).backgroundColor}26`,
                      color: (BOOKING_STATUS_COLORS[selectedEvent.extendedProps.status] || BOOKING_STATUS_COLORS.confirmed).backgroundColor,
                      fontWeight: 600
                    }}>
                      {(BOOKING_STATUS_COLORS[selectedEvent.extendedProps.status] || BOOKING_STATUS_COLORS.confirmed).label}
                    </span>
                  </div>
                  {selectedEvent.extendedProps.comment && (
                    <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid hsl(var(--border))', padding: '12px', borderRadius: '8px', marginTop: '10px' }}>
                      <span style={{ display: 'block', fontSize: '0.75rem', color: 'hsl(var(--text-secondary))', marginBottom: '4px' }}>Комментарий администратора:</span>
                      <span style={{ color: 'white', fontSize: '0.85rem' }}>{selectedEvent.extendedProps.comment}</span>
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '15px', marginTop: '15px' }}>
                  {selectedEvent.id !== 'new' && (
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ flex: 1, justifyContent: 'center', borderColor: '#ef4444', color: '#ef4444' }}
                      onClick={handleDeleteBooking}
                    >
                      Отменить
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ flex: 1, justifyContent: 'center' }}
                    onMouseDown={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      startEditBooking()
                    }}
                  >
                    Редактировать
                  </button>
                  <button
                    type="button"
                    className="btn-primary"
                    style={{ flex: 1, justifyContent: 'center' }}
                    onClick={closeBookingModal}
                  >
                    Готово
                  </button>
                </div>
            </div>

            <div style={{ display: modalMode === 'edit' && editForm ? 'block' : 'none' }}>
              <form onSubmit={handleSaveBooking} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">Выбор гостя из базы</label>
                    <select
                      className="form-input"
                      value={editForm.guestId}
                      onChange={(e) => {
                        const client = clients.find((c) => String(c.id) === e.target.value)
                        setEditForm({
                          ...editForm,
                          guestId: e.target.value,
                          guestName: client?.name || editForm.guestName,
                        })
                      }}
                    >
                      <option value="">-- Выбрать гостя --</option>
                      {clients.map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">Имя гостя (для отображения)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={editForm.guestName}
                      onChange={(e) => setEditForm({ ...editForm, guestName: e.target.value })}
                      placeholder="Имя / Фамилия"
                      required
                    />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">Номер комнаты</label>
                    <input
                      type="text"
                      className="form-input"
                      value={editForm.room}
                      onChange={(e) => setEditForm({ ...editForm, room: e.target.value })}
                    />
                  </div>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">Длительность (мин)</label>
                    <input
                      type="number"
                      className="form-input"
                      min="15"
                      step="15"
                      value={editForm.duration}
                      onChange={(e) => setEditForm({ ...editForm, duration: e.target.value })}
                      required
                    />
                  </div>
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">Специалист</label>
                  <select
                    className="form-input"
                    value={editForm.specialistId}
                    onChange={(e) => {
                      const spec = specialists.find((s) => String(s.id) === e.target.value)
                      setEditForm({
                        ...editForm,
                        specialistId: e.target.value,
                        specialist: spec?.name || '',
                      })
                    }}
                    required
                  >
                    {specialists.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">Кабинет</label>
                  <select
                    className="form-input"
                    value={editForm.cabinetId}
                    onChange={(e) => {
                      const cab = cabinets.find((c) => String(c.id) === e.target.value)
                      setEditForm({
                        ...editForm,
                        cabinetId: e.target.value,
                        cabinet: cab?.name || '',
                      })
                    }}
                    required
                  >
                    {cabinets.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">Услуга</label>
                    <select
                      className="form-input"
                      value={editForm.serviceVariantId}
                      onChange={(e) => {
                        const variant = serviceVariants.find((v) => String(v.id) === e.target.value)
                        setEditForm({
                          ...editForm,
                          serviceVariantId: e.target.value,
                          service: variant?.service_name || '',
                          duration: variant?.duration_minutes || editForm.duration,
                        })
                      }}
                      required
                    >
                      {serviceVariants.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.service_name} ({v.duration_minutes} мин) — {v.price} ₽
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">Статус</label>
                    <select
                      className="form-input"
                      value={editForm.status}
                      onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
                    >
                      <option value="paid">Оплачено</option>
                      <option value="confirmed">Подтверждено</option>
                      <option value="unconfirmed">Не подтверждено</option>
                    </select>
                  </div>
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">Время начала</label>
                  <input
                    type="datetime-local"
                    className="form-input"
                    value={editForm.startLocal}
                    onChange={(e) => setEditForm({ ...editForm, startLocal: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">Комментарий</label>
                  <textarea
                    rows="3"
                    className="form-input"
                    style={{ resize: 'vertical' }}
                    value={editForm.comment}
                    onChange={(e) => setEditForm({ ...editForm, comment: e.target.value })}
                  />
                </div>

                <div style={{ display: 'flex', gap: '15px', marginTop: '8px' }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ flex: 1, justifyContent: 'center' }}
                    onClick={() => setModalMode('view')}
                  >
                    Отмена
                  </button>
                  <button
                    type="submit"
                    className="btn-primary"
                    style={{ flex: 1, justifyContent: 'center' }}
                    disabled={savingBooking}
                  >
                    {savingBooking ? 'Сохранение...' : 'Сохранить'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* MERGE GUESTS MODAL */}
      {mergeModalOpen && mergePrimary && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.6)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1100,
          }}
          onMouseDown={() => setMergeModalOpen(false)}
        >
          <div
            className="glass-card"
            style={{ padding: '30px', width: '100%', maxWidth: '520px', display: 'flex', flexDirection: 'column', gap: '16px' }}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h3 style={{ color: 'white', fontSize: '1.2rem' }}>Объединение профилей гостей</h3>
            <p style={{ color: 'hsl(var(--text-secondary))', fontSize: '0.9rem' }}>
              Основной профиль: <strong style={{ color: 'white' }}>{mergePrimary.guest_name}</strong>
            </p>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Имя после объединения</label>
              <input
                type="text"
                className="form-input"
                value={mergeDisplayName}
                onChange={(e) => setMergeDisplayName(e.target.value)}
              />
            </div>
            <div>
              <label className="form-label">Выберите дубликаты для слияния</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '200px', overflowY: 'auto' }}>
                {mergeCandidates.length === 0 ? (
                  <p style={{ color: 'hsl(var(--text-secondary))', fontSize: '0.85rem' }}>Похожие профили не найдены</p>
                ) : (
                  mergeCandidates.map((candidate) => (
                    <label key={candidate.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'white', fontSize: '0.9rem' }}>
                      <input
                        type="checkbox"
                        checked={mergeSelectedIds.includes(candidate.id)}
                        onChange={() => toggleMergeDuplicate(candidate.id)}
                        style={{ accentColor: 'hsl(var(--primary))' }}
                      />
                      {candidate.name} ({candidate.visits} визитов)
                    </label>
                  ))
                )}
              </div>
            </div>
            {mergeError && <p style={{ color: '#ef4444', fontSize: '0.85rem' }}>{mergeError}</p>}
            <div style={{ display: 'flex', gap: '12px' }}>
              <button className="btn-secondary" style={{ flex: 1, justifyContent: 'center' }} onClick={() => setMergeModalOpen(false)}>
                Отмена
              </button>
              <button
                className="btn-primary"
                style={{ flex: 1, justifyContent: 'center' }}
                disabled={mergeLoading || mergeSelectedIds.length === 0}
                onClick={handleMergeGuests}
              >
                {mergeLoading ? 'Объединение...' : 'Объединить'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
