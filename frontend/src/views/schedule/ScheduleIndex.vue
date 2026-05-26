<script setup>
import {ref, computed, onMounted, useTemplateRef} from "vue";
import api from "@/js/http/api.js";
import ScheduleForm from "@/views/schedule/ScheduleForm.vue";

const today = new Date()
const currentYear = ref(today.getFullYear())
const currentMonth = ref(today.getMonth() + 1)
const selectedDay = ref(today.getDate())
const schedules = ref([])
const loading = ref(false)
const formRef = useTemplateRef('form-ref')
const editingSchedule = ref(null)

const weekDays = ['日', '一', '二', '三', '四', '五', '六']

const calendarDays = computed(() => {
  const year = currentYear.value
  const month = currentMonth.value
  const firstDay = new Date(year, month - 1, 1).getDay()
  const daysInMonth = new Date(year, month, 0).getDate()
  const days = []
  for (let i = 0; i < firstDay; i++) {
    days.push({day: null, key: `empty-${i}`})
  }
  for (let d = 1; d <= daysInMonth; d++) {
    days.push({day: d, key: `${year}-${month}-${d}`})
  }
  return days
})

const monthTitle = computed(() => {
  return `${currentYear.value}年${currentMonth.value}月`
})

const selectedDateSchedules = computed(() => {
  return schedules.value.filter(s => {
    const date = new Date(s.start_time)
    return date.getDate() === selectedDay.value
  }).sort((a, b) => new Date(a.start_time) - new Date(b.start_time))
})

const scheduleDays = computed(() => {
  const days = new Set()
  schedules.value.forEach(s => {
    const date = new Date(s.start_time)
    if (date.getMonth() + 1 === currentMonth.value) {
      days.add(date.getDate())
    }
  })
  return days
})

function prevMonth() {
  if (currentMonth.value === 1) {
    currentMonth.value = 12
    currentYear.value--
  } else {
    currentMonth.value--
  }
  loadSchedules()
}

function nextMonth() {
  if (currentMonth.value === 12) {
    currentMonth.value = 1
    currentYear.value++
  } else {
    currentMonth.value++
  }
  loadSchedules()
}

function selectDay(day) {
  if (day) {
    selectedDay.value = day
  }
}

function isToday(day) {
  return day === today.getDate()
    && currentMonth.value === today.getMonth() + 1
    && currentYear.value === today.getFullYear()
}

function isSelected(day) {
  return day === selectedDay.value
}

async function loadSchedules() {
  loading.value = true
  try {
    const res = await api.get('/api/schedule/get_list/', {
      params: {
        year: currentYear.value,
        month: currentMonth.value,
      }
    })
    if (res.data.result === 'success') {
      schedules.value = res.data.schedules
    }
  } catch (err) {
    console.error('加载日程失败:', err)
  } finally {
    loading.value = false
  }
}

function formatTime(isoString) {
  if (!isoString) return ''
  const date = new Date(isoString)
  return date.toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'})
}

function formatTimeRange(schedule) {
  const start = formatTime(schedule.start_time)
  if (schedule.end_time) {
    return `${start} - ${formatTime(schedule.end_time)}`
  }
  return start
}

function openCreateForm() {
  editingSchedule.value = null
  formRef.value?.open()
}

function openEditForm(schedule) {
  editingSchedule.value = schedule
  formRef.value?.open(schedule)
}

async function handleDelete(schedule) {
  if (!confirm(`确定删除日程"${schedule.title}"吗？`)) return
  try {
    await api.post('/api/schedule/delete/', {schedule_id: schedule.id})
    await loadSchedules()
  } catch (err) {
    console.error('删除日程失败:', err)
  }
}

async function handleSave() {
  await loadSchedules()
}

onMounted(() => {
  loadSchedules()
})
</script>

<template>
  <div class="flex justify-center p-6">
    <div class="flex gap-6 w-full max-w-5xl">
      <!-- 左侧日历 -->
      <div class="card bg-base-100 shadow-sm w-80 shrink-0">
        <div class="card-body p-4">
          <!-- 月份切换 -->
          <div class="flex items-center justify-between mb-2">
            <button @click="prevMonth" class="btn btn-sm btn-ghost btn-circle">❮</button>
            <span class="font-bold text-lg">{{ monthTitle }}</span>
            <button @click="nextMonth" class="btn btn-sm btn-ghost btn-circle">❯</button>
          </div>

          <!-- 星期标题 -->
          <div class="grid grid-cols-7 gap-1 text-center text-xs text-base-content/60 mb-1">
            <span v-for="w in weekDays" :key="w">{{ w }}</span>
          </div>

          <!-- 日期格子 -->
          <div class="grid grid-cols-7 gap-1">
            <div
              v-for="item in calendarDays"
              :key="item.key"
              @click="selectDay(item.day)"
              class="aspect-square flex flex-col items-center justify-center rounded-lg text-sm cursor-pointer transition-colors"
              :class="{
                'hover:bg-base-200': item.day && !isSelected(item.day),
                'bg-primary text-primary-content font-bold': item.day && isSelected(item.day),
                'ring-2 ring-primary ring-offset-1': item.day && isToday(item.day) && !isSelected(item.day),
                'text-base-content/30': !item.day,
              }"
            >
              <span>{{ item.day }}</span>
              <span v-if="item.day && scheduleDays.has(item.day)" class="w-1 h-1 rounded-full mt-0.5"
                :class="isSelected(item.day) ? 'bg-primary-content' : 'bg-primary'"></span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧日程列表 -->
      <div class="flex-1 min-w-0">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xl font-bold">
            {{ currentMonth }}月{{ selectedDay }}日 日程
          </h2>
          <button @click="openCreateForm" class="btn btn-primary btn-sm">
            + 新建日程
          </button>
        </div>

        <div v-if="loading" class="text-center py-8 text-base-content/40">加载中...</div>

        <div v-else-if="selectedDateSchedules.length === 0" class="text-center py-12">
          <svg class="w-16 h-16 mx-auto mb-4 text-base-content/20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" stroke-width="1.5"></rect>
            <line x1="16" y1="2" x2="16" y2="6" stroke-width="1.5"></line>
            <line x1="8" y1="2" x2="8" y2="6" stroke-width="1.5"></line>
            <line x1="3" y1="10" x2="21" y2="10" stroke-width="1.5"></line>
          </svg>
          <p class="text-base-content/40">暂无日程</p>
        </div>

        <div v-else class="flex flex-col gap-3">
          <div
            v-for="schedule in selectedDateSchedules"
            :key="schedule.id"
            class="card bg-base-100 shadow-sm hover:shadow-md transition-shadow"
          >
            <div class="card-body p-4 flex-row items-start gap-4">
              <!-- 时间线 -->
              <div class="flex flex-col items-center shrink-0 pt-1">
                <div class="w-3 h-3 rounded-full bg-primary"></div>
                <div class="w-0.5 h-full bg-base-300 mt-1"></div>
              </div>

              <!-- 内容 -->
              <div class="flex-1 min-w-0">
                <div class="flex items-start justify-between gap-2">
                  <div>
                    <h3 class="font-bold" :class="{'line-through text-base-content/40': schedule.status === 'completed'}">
                      {{ schedule.title }}
                    </h3>
                    <p class="text-sm text-base-content/60 mt-1">{{ formatTimeRange(schedule) }}</p>
                    <p v-if="schedule.location" class="text-sm text-base-content/50 mt-1">📍 {{ schedule.location }}</p>
                    <p v-if="schedule.description" class="text-sm text-base-content/60 mt-2">{{ schedule.description }}</p>
                  </div>
                  <div class="flex gap-1 shrink-0">
                    <button @click="openEditForm(schedule)" class="btn btn-xs btn-ghost">编辑</button>
                    <button @click="handleDelete(schedule)" class="btn btn-xs btn-ghost text-error">删除</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <ScheduleForm ref="form-ref" :schedule="editingSchedule" @save="handleSave" />
  </div>
</template>

<style scoped>
</style>
