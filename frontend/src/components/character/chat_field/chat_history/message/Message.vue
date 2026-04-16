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
}

.image-container img {
  max-width: 300px;
  border-radius: 8px;
  transition: transform 0.2s;
}

.image-container img:hover {
  transform: scale(1.02);
}

.image-caption {
  text-align: center;
  color: #666;
  font-style: italic;
}
</style>
