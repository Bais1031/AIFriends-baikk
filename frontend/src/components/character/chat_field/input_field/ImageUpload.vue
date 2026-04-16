<script setup>
import { ref, computed, onUnmounted } from 'vue'

const props = defineProps({
  modelValue: {
    type: [File, null],
    default: null
  }
})

const emit = defineEmits(['update:modelValue', 'clear'])

const fileInput = ref(null)
const isDragging = ref(false)
const isHovered = ref(false)

// 计算预览URL
const previewUrl = computed(() => {
  if (props.modelValue) {
    return URL.createObjectURL(props.modelValue)
  }
  return null
})

// 拖拽事件处理
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

// 文件选择处理
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

// 清除图片
const clearImage = (e) => {
  e.preventDefault()
  e.stopPropagation()
  emit('update:modelValue', null)
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

// 点击上传区域
const triggerFileInput = () => {
  if (!props.modelValue) {
    fileInput.value?.click()
  }
}

// 组件卸载时清理预览URL
onUnmounted(() => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
})
</script>

<template>
  <div
    class="image-upload-area"
    :class="{
      'dragging': isDragging,
      'has-image': modelValue,
      'hovered': isHovered
    }"
    @dragover.prevent="dragOver"
    @dragleave.prevent="dragLeave"
    @drop.prevent="drop"
    @click="triggerFileInput"
    @mouseenter="isHovered = true"
    @mouseleave="isHovered = false"
  >
    <input
      ref="fileInput"
      type="file"
      @change="handleFileChange"
      accept="image/*"
      style="display: none"
    >

    <!-- 无图片时的上传按钮 -->
    <div v-if="!modelValue" class="upload-btn">
      <span class="icon">📷</span>
    </div>

    <!-- 图片预览 -->
    <div v-else class="image-preview" @click.stop="triggerFileInput">
      <img :src="previewUrl" alt="预览图片" />
      <button
        @click.stop="clearImage"
        class="remove-btn"
        title="删除图片"
      >
        ✕
      </button>
    </div>
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

.image-upload-area.hovered,
.image-upload-area.dragging {
  background-color: rgba(255, 255, 255, 0.1);
}

.upload-btn {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  opacity: 0.7;
}

.icon {
  font-size: 20px;
}

.image-upload-area:hover .icon {
  opacity: 1;
  transform: scale(1.1);
}

.image-preview {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: 4px;
  overflow: hidden;
  background-color: rgba(0, 0, 0, 0.2);
}

.image-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 4px;
}

.remove-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(255, 77, 79, 0.9);
  color: white;
  border: none;
  cursor: pointer;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.remove-btn:hover {
  background: rgba(255, 120, 117, 1);
  transform: scale(1.2);
}
</style>