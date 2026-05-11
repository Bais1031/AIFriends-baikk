<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: [File, null],
    default: null
  }
})

const emit = defineEmits(['update:modelValue'])

const fileInput = ref(null)
const isDragging = ref(false)

const dragOver = (e) => {
  e.preventDefault()
  e.stopPropagation()
  isDragging.value = true
}

const dragLeave = (e) => {
  e.preventDefault()
  e.stopPropagation()
  isDragging.value = false
}

const drop = (e) => {
  e.preventDefault()
  e.stopPropagation()
  isDragging.value = false

  const files = e.dataTransfer.files
  if (files.length && files[0].type.startsWith('image/')) {
    handleFileSelect(files[0])
  }
}

const handleFileChange = (e) => {
  const file = e.target.files[0]
  if (file) {
    handleFileSelect(file)
  }
}

const handleFileSelect = (file) => {
  if (file.type.startsWith('image/')) {
    emit('update:modelValue', file)
  }
}

const triggerFileInput = () => {
  fileInput.value?.click()
}

watch(() => props.modelValue, (newVal) => {
  if (!newVal && fileInput.value) {
    fileInput.value.value = ''
  }
})
</script>

<template>
  <div
    class="image-upload-area"
    :class="{ 'dragging': isDragging, 'has-image': modelValue }"
    @dragover.prevent="dragOver"
    @dragleave.prevent="dragLeave"
    @drop.prevent="drop"
    @click="triggerFileInput"
  >
    <input
      ref="fileInput"
      type="file"
      @change="handleFileChange"
      accept="image/*"
      style="display: none"
    >
    <span class="icon" :class="{ 'selected': modelValue }">📷</span>
  </div>
</template>

<style scoped>
.image-upload-area {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.image-upload-area.dragging {
  background-color: rgba(255, 255, 255, 0.1);
}

.icon {
  font-size: 20px;
  opacity: 0.7;
  transition: all 0.2s ease;
}

.image-upload-area:hover .icon {
  opacity: 1;
}

.icon.selected {
  opacity: 1;
  filter: drop-shadow(0 0 4px rgba(59, 130, 246, 0.8));
}
</style>