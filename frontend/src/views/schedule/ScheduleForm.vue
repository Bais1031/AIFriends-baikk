<script setup>
import {ref, useTemplateRef, watch} from "vue";
import api from "@/js/http/api.js";

const props = defineProps(['schedule'])
const emit = defineEmits(['save'])
const modalRef = useTemplateRef('modal-ref')

const title = ref('')
const description = ref('')
const startDate = ref('')
const startTime = ref('')
const endDate = ref('')
const endTime = ref('')
const location = ref('')
const repeatType = ref('none')
const reminderBefore = ref(30)
const saving = ref(false)

function open(existingSchedule) {
  if (existingSchedule) {
    title.value = existingSchedule.title
    description.value = existingSchedule.description || ''
    const start = new Date(existingSchedule.start_time)
    startDate.value = formatDate(start)
    startTime.value = formatTimeInput(start)
    if (existingSchedule.end_time) {
      const end = new Date(existingSchedule.end_time)
      endDate.value = formatDate(end)
      endTime.value = formatTimeInput(end)
    } else {
      endDate.value = ''
      endTime.value = ''
    }
    location.value = existingSchedule.location || ''
    repeatType.value = existingSchedule.repeat_type || 'none'
    reminderBefore.value = existingSchedule.reminder_before ?? 30
  } else {
    title.value = ''
    description.value = ''
    const now = new Date()
    startDate.value = formatDate(now)
    startTime.value = formatTimeInput(new Date(now.getTime() + 3600000))
    endDate.value = ''
    endTime.value = ''
    location.value = ''
    repeatType.value = 'none'
    reminderBefore.value = 30
  }
  modalRef.value?.showModal()
}

function formatDate(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function formatTimeInput(date) {
  const h = String(date.getHours()).padStart(2, '0')
  const m = String(date.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

async function handleSave() {
  if (!title.value.trim() || !startDate.value || !startTime.value) return
  saving.value = true
  try {
    const start_time = `${startDate.value}T${startTime.value}:00`
    let end_time = null
    if (endDate.value && endTime.value) {
      end_time = `${endDate.value}T${endTime.value}:00`
    }

    if (props.schedule) {
      await api.post('/api/schedule/update/', {
        schedule_id: props.schedule.id,
        title: title.value.trim(),
        description: description.value,
        start_time,
        end_time,
        location: location.value,
        repeat_type: repeatType.value,
        reminder_before: reminderBefore.value,
      })
    } else {
      await api.post('/api/schedule/create/', {
        title: title.value.trim(),
        description: description.value,
        start_time,
        end_time,
        location: location.value,
        repeat_type: repeatType.value,
        reminder_before: reminderBefore.value,
        source: 'text',
      })
    }
    modalRef.value?.close()
    emit('save')
  } catch (err) {
    console.error('保存日程失败:', err)
  } finally {
    saving.value = false
  }
}

defineExpose({open})
</script>

<template>
  <dialog ref="modal-ref" class="modal">
    <div class="modal-box max-w-lg">
      <form method="dialog">
        <button class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2">✕</button>
      </form>
      <h3 class="font-bold text-lg mb-4">{{ props.schedule ? '编辑日程' : '新建日程' }}</h3>

      <div class="flex flex-col gap-4">
        <!-- 标题 -->
        <label class="form-control">
          <div class="label"><span class="label-text">标题</span></div>
          <input v-model="title" type="text" class="input input-bordered w-full" placeholder="输入日程标题" />
        </label>

        <!-- 开始时间 -->
        <div class="flex gap-3">
          <label class="form-control flex-1">
            <div class="label"><span class="label-text">开始日期</span></div>
            <input v-model="startDate" type="date" class="input input-bordered w-full" />
          </label>
          <label class="form-control w-32">
            <div class="label"><span class="label-text">时间</span></div>
            <input v-model="startTime" type="time" class="input input-bordered w-full" />
          </label>
        </div>

        <!-- 结束时间 -->
        <div class="flex gap-3">
          <label class="form-control flex-1">
            <div class="label"><span class="label-text">结束日期（可选）</span></div>
            <input v-model="endDate" type="date" class="input input-bordered w-full" />
          </label>
          <label class="form-control w-32">
            <div class="label"><span class="label-text">时间</span></div>
            <input v-model="endTime" type="time" class="input input-bordered w-full" />
          </label>
        </div>

        <!-- 地点 -->
        <label class="form-control">
          <div class="label"><span class="label-text">地点（可选）</span></div>
          <input v-model="location" type="text" class="input input-bordered w-full" placeholder="输入地点" />
        </label>

        <!-- 重复 -->
        <label class="form-control">
          <div class="label"><span class="label-text">重复</span></div>
          <select v-model="repeatType" class="select select-bordered w-full">
            <option value="none">不重复</option>
            <option value="daily">每天</option>
            <option value="weekly">每周</option>
            <option value="monthly">每月</option>
          </select>
        </label>

        <!-- 提醒 -->
        <label class="form-control">
          <div class="label"><span class="label-text">提前提醒（分钟）</span></div>
          <input v-model.number="reminderBefore" type="number" class="input input-bordered w-full" min="0" />
        </label>

        <!-- 描述 -->
        <label class="form-control">
          <div class="label"><span class="label-text">描述（可选）</span></div>
          <textarea v-model="description" class="textarea textarea-bordered w-full" rows="3" placeholder="添加描述"></textarea>
        </label>
      </div>

      <div class="modal-action">
        <form method="dialog">
          <button class="btn">取消</button>
        </form>
        <button @click="handleSave" class="btn btn-primary" :disabled="saving || !title.trim()">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button>close</button>
    </form>
  </dialog>
</template>

<style scoped>
</style>
