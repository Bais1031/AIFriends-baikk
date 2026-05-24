<script setup>
import SendIcon from "@/components/character/icons/SendIcon.vue";
import MicIcon from "@/components/character/icons/MicIcon.vue";
import ImageUpload from "@/components/character/chat_field/input_field/ImageUpload.vue";
import {computed, onUnmounted, ref, useTemplateRef} from "vue";
import streamApi from "@/js/http/streamApi.js";
import Microphone from "@/components/character/chat_field/input_field/Microphone.vue";

const props = defineProps(['friendId', 'inline'])
const emit = defineEmits(['pushBackMessage', 'addToLastMessage'])
const inputRef = useTemplateRef('input-ref')
const message = ref('')
const selectedImage = ref(null)  // 存储选中的图片文件
const previewUrl = computed(() => {
  if (selectedImage.value) {
    return URL.createObjectURL(selectedImage.value)
  }
  return null
})

function clearSelectedImage() {
  selectedImage.value = null
}
let processId = 0
const showMic = ref(false)

let mediaSource = null;
let sourceBuffer = null;
let audioPlayer = new Audio(); // 全局播放器实例
let audioQueue = [];           // 待写入 Buffer 的二进制队列
let isUpdating = false;        // Buffer 是否正在写入

const initAudioStream = () => {
    audioPlayer.pause();
    audioQueue = [];
    isUpdating = false;

    mediaSource = new MediaSource();
    audioPlayer.src = URL.createObjectURL(mediaSource);

    mediaSource.addEventListener('sourceopen', () => {
        try {
            sourceBuffer = mediaSource.addSourceBuffer('audio/mpeg');
            sourceBuffer.addEventListener('updateend', () => {
                isUpdating = false;
                processQueue();
            });
        } catch (e) {
            console.error("MSE AddSourceBuffer Error:", e);
        }
    });

    audioPlayer.play().catch(e => console.error("等待用户交互以播放音频"));
};

const processQueue = () => {
    if (isUpdating || audioQueue.length === 0 || !sourceBuffer || sourceBuffer.updating) {
        return;
    }

    isUpdating = true;
    const chunk = audioQueue.shift();
    try {
        sourceBuffer.appendBuffer(chunk);
    } catch (e) {
        console.error("SourceBuffer Append Error:", e);
        isUpdating = false;
    }
};

const stopAudio = () => {
    audioPlayer.pause();
    audioQueue = [];
    isUpdating = false;

    if (mediaSource) {
        if (mediaSource.readyState === 'open') {
            try {
                mediaSource.endOfStream();
            } catch (e) {
            }
        }
        mediaSource = null;
    }

    if (audioPlayer.src) {
        URL.revokeObjectURL(audioPlayer.src);
        audioPlayer.src = '';
    }
};

const handleAudioChunk = (base64Data) => {  // 将语音片段添加到播放器队列中
    try {
        const binaryString = atob(base64Data);
        const len = binaryString.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        audioQueue.push(bytes);
        processQueue();
    } catch (e) {
        console.error("Base64 Decode Error:", e);
    }
};

onUnmounted(() => {
    audioPlayer.pause();
    audioPlayer.src = '';
});

function focus() {
  inputRef.value.focus()
}

async function handleSend(event, audio_msq) {
  let content
  if (audio_msq) {
    content = audio_msq.trim()
  } else {
    content = message.value.trim()
  }

  // 检查是否有消息或图片
  if (!content && !selectedImage.value) return

  initAudioStream()

  const curId = ++ processId
  message.value = ''

  // 准备用户消息
  const imageFile = selectedImage.value
  const userMessage = {
    role: 'user',
    content: content || '[图片]',
    image_url: imageFile ? URL.createObjectURL(imageFile) : null,
    id: crypto.randomUUID()
  }

  // 立即清除选中的图片
  selectedImage.value = null

  emit('pushBackMessage', userMessage)
  emit('pushBackMessage', {role: 'ai', content: '', id: crypto.randomUUID()})

  try {
    // 根据是否有图片选择不同的API
    if (imageFile) {
      // 有图片，使用多模态API
      const formData = new FormData()
      formData.append('friend_id', props.friendId)
      formData.append('message', content || '')
      formData.append('image', imageFile)

      await streamApi('/api/friend/message/chat/multimodal/', {
        body: formData,
        onmessage(data, isDone) {
          if (curId !==processId) return

          if (data.content) {
            emit('addToLastMessage', data.content)
          }
          if (data.audio) {
            handleAudioChunk(data.audio)
          }
        },
        onerror(err) {
          console.error('Stream error:', err)
        },
      })
    } else {
      // 没有图片，使用原来的API
      await streamApi('/api/friend/message/chat/', {
        body: {
          friend_id: props.friendId,
          message: content,
        },
        onmessage(data, isDone) {
          if (curId !==processId) return

          if (data.content) {
            emit('addToLastMessage', data.content)
          }
          if (data.audio) {
            handleAudioChunk(data.audio)
          }
        },
        onerror(err) {
          console.error('Stream error:', err)
        },
      })
    }
  } catch (err) {
    console.error('Send error:', err)
  }
}

function close() {
  ++ processId
  showMic.value = false
  stopAudio()
}

function handleStop() {
  ++ processId
  stopAudio()
}

defineExpose({
  focus,
  close,
})
</script>

<template>
  <div v-if="!showMic" :class="inline
    ? 'w-full px-4 pb-4 flex flex-col items-end gap-1'
    : 'absolute bottom-4 left-2 w-86 flex flex-col items-end gap-1'">
    <!-- 图片预览条 -->
    <div v-if="previewUrl" class="image-preview-bar">
      <img :src="previewUrl" alt="预览" class="preview-thumb" />
      <button @click="clearSelectedImage" class="preview-remove" title="删除图片">✕</button>
    </div>

    <form @submit.prevent="handleSend" class="w-full h-12 flex items-center relative">
      <!-- 图片上传按钮 -->
      <div class="absolute left-2 z-10">
        <ImageUpload
          v-model="selectedImage"
          class="image-upload-btn"
        />
      </div>

      <!-- 输入框 -->
      <input
          ref="input-ref"
          v-model="message"
          class="input bg-black/30 backdrop-blur-sm text-white text-base w-full h-full rounded-2xl pr-20 pl-12"
          type="text"
          placeholder="输入消息或上传图片..."
      >

      <!-- 发送按钮 -->
      <div @click="handleSend" class="absolute right-2 w-8 h-8 flex justify-center items-center cursor-pointer">
        <SendIcon />
      </div>

      <!-- 麦克风按钮 -->
      <div @click="showMic = true" class="absolute right-10 w-8 h-8 flex justify-center items-center cursor-pointer">
        <MicIcon />
      </div>
    </form>
  </div>
  <microphone
      v-else
      @close="showMic = false"
      @send="handleSend"
      @stop="handleStop"
  />
</template>

<style scoped>
.image-upload-btn {
  width: 32px;
  height: 32px;
  overflow: hidden;
  opacity: 0.8;
}

.image-upload-btn:hover {
  opacity: 1;
}

.image-preview-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(8px);
  border-radius: 8px;
}

.preview-thumb {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 4px;
}

.preview-remove {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(255, 77, 79, 0.9);
  color: white;
  border: none;
  cursor: pointer;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.preview-remove:hover {
  background: rgba(255, 120, 117, 1);
  transform: scale(1.1);
}
</style>