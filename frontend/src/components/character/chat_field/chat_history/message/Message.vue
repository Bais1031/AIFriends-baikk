<script setup>
import {useUserStore} from "@/stores/user.js";

defineProps(['message', 'character'])

const user = useUserStore()

const previewImage = (url) => {
  // 创建模态框显示图片
  const modal = document.createElement('div');
  modal.className = 'fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4';
  modal.onclick = () => document.body.removeChild(modal);

  const img = document.createElement('img');
  img.src = url;
  img.className = 'max-w-full max-h-[90vh] rounded-lg';
  img.onclick = (e) => {
    e.stopPropagation();
  };

  modal.appendChild(img);
  document.body.appendChild(modal);
}
</script>

<template>
  <div v-if="message.content || message.image_url">
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
            @click="previewImage(message.image_url)"
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
            @click="previewImage(message.image_url)"
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
