<script setup>
import {useUserStore} from "@/stores/user.js";

const props = defineProps(['message', 'character', 'selectMode', 'selected'])
const emit = defineEmits(['toggleSelect'])

const user = useUserStore()

const previewImage = (url) => {
  const dialog = document.createElement('dialog');
  dialog.className = 'image-preview-dialog';
  dialog.onclick = () => {
    dialog.close();
    dialog.remove();
  };

  const img = document.createElement('img');
  img.src = url;
  img.onclick = (e) => e.stopPropagation();

  dialog.appendChild(img);
  document.body.appendChild(dialog);
  dialog.showModal();
}
</script>

<template>
  <div v-if="message.content || message.image_url" class="message-row" :class="{selectable: selectMode, selected: selected}" @click="selectMode && emit('toggleSelect')">
    <!-- 选择模式复选框 -->
    <div v-if="selectMode" class="checkbox-wrapper">
      <input type="checkbox" class="checkbox checkbox-sm checkbox-primary" :checked="selected" @click.stop="emit('toggleSelect')" />
    </div>

    <div v-if="message.role === 'ai'" class="chat chat-start">
      <div class="chat-image avatar">
        <div class="w-10 rounded-full">
          <img :src="character.photo" alt="">
        </div>
      </div>
      <div class="chat-bubble whitespace-pre-wrap break-all">
        <div v-if="message.content" class="text">{{ message.content }}</div>
        <div v-if="message.image_url" class="image-container mt-2">
          <img
            :src="message.image_url"
            alt="AI生成的图片"
            class="max-w-full rounded-lg cursor-pointer"
            @click.stop="selectMode ? null : previewImage(message.image_url)"
          />
          <div v-if="message.image_caption" class="image-caption mt-1 text-xs text-gray-500">
            {{ message.image_caption }}
          </div>
        </div>
      </div>
    </div>
    <div v-else class="chat chat-end">
      <div class="chat-image avatar">
        <div class="w-10 rounded-full">
          <img :src="user.photo" alt="">
        </div>
      </div>
      <div class="chat-bubble chat-bubble-success whitespace-pre-wrap">
        <div v-if="message.content" class="text">{{ message.content }}</div>
        <div v-if="message.image_url" class="image-container mt-2">
          <img
            :src="message.image_url"
            alt="用户发送的图片"
            class="max-w-full rounded-lg cursor-pointer"
            @click.stop="selectMode ? null : previewImage(message.image_url)"
          />
          <div v-if="message.image_caption" class="image-caption mt-1 text-xs text-gray-500">
            {{ message.image_caption }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-row {
  display: flex;
  align-items: flex-start;
  position: relative;
}

.message-row.selectable {
  cursor: pointer;
  border-radius: 8px;
  transition: background-color 0.15s;
}

.message-row.selectable:hover {
  background-color: oklch(var(--b2) / 0.5);
}

.message-row.selectable.selected {
  background-color: oklch(var(--p) / 0.1);
}

.checkbox-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  min-height: 40px;
  padding-top: 12px;
  flex-shrink: 0;
}

.message-row .chat {
  flex: 1;
  min-width: 0;
}

.image-preview-dialog {
  background: rgba(0, 0, 0, 0.75);
  border: none;
  max-width: 100vw;
  max-height: 100vh;
  width: 100vw;
  height: 100vh;
  margin: 0;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.image-preview-dialog::backdrop {
  background: transparent;
}

.image-preview-dialog img {
  max-width: 100%;
  max-height: 90vh;
  border-radius: 8px;
  cursor: default;
}

.image-container {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  margin-top: 8px;
}

.chat-start .image-container {
  justify-content: flex-start;
}

.chat-end .image-container {
  justify-content: flex-end;
}

.image-container img {
  max-width: 100%;
  max-height: 300px;
  width: auto;
  height: auto;
  object-fit: contain;
  border-radius: 8px;
  transition: transform 0.2s, box-shadow 0.2s;
  cursor: pointer;
}

.image-container img:hover {
  transform: scale(1.02);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.chat-start .image-container img {
  margin-right: 12px;
}

.chat-end .image-container img {
  margin-left: 12px;
}

.image-caption {
  text-align: center;
  color: #666;
  font-style: italic;
  margin-top: 4px;
  font-size: 12px;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .image-container img {
    max-height: 250px;
  }
}

@media (max-width: 480px) {
  .image-container img {
    max-height: 200px;
  }
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .image-caption {
    color: #aaa;
  }

  .image-container img:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  }
}

/* Light theme adjustments */
@media (prefers-color-scheme: light) {
  .image-container img:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }
}
</style>
