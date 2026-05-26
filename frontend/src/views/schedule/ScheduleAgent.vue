<script setup>
import {nextTick, ref, useTemplateRef} from "vue";
import streamApi from "@/js/http/streamApi.js";

const emit = defineEmits(['scheduleCreated'])
const modalRef = useTemplateRef('modal-ref')
const scrollRef = useTemplateRef('scroll-ref')
const inputRef = useTemplateRef('input-ref')
const message = ref('')
const messages = ref([])
const isLoading = ref(false)

function open() {
  messages.value = [{
    role: 'ai',
    content: '你好！我是你的日程助手。你可以告诉我你想安排的事情，比如：\n\n- "明天下午3点开会"\n- "帮我看看这周有什么安排"\n- "下周五晚上7点和朋友聚餐，在万达广场"'
  }]
  modalRef.value?.showModal()
  nextTick(() => {
    inputRef.value?.focus()
  })
}

async function handleSend() {
  const content = message.value.trim()
  if (!content || isLoading.value) return

  message.value = ''
  messages.value.push({role: 'user', content})
  messages.value.push({role: 'ai', content: ''})
  isLoading.value = true

  scrollToBottom()

  try {
    await streamApi('/api/schedule/agent_chat/', {
      body: {message: content},
      onmessage(data, isDone) {
        if (isDone) {
          isLoading.value = false
          // 检查是否有日程创建，通知父组件刷新
          const lastMsg = messages.value[messages.value.length - 1]
          if (lastMsg?.content?.includes('日程创建成功')) {
            emit('scheduleCreated')
          }
          return
        }
        if (data.content) {
          messages.value[messages.value.length - 1].content += data.content
          scrollToBottom()
        }
      },
      onerror(err) {
        console.error('Agent 流错误:', err)
        isLoading.value = false
        messages.value[messages.value.length - 1].content += '\n\n[连接中断，请重试]'
      },
    })
  } catch (err) {
    console.error('Agent 请求失败:', err)
    isLoading.value = false
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  })
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

defineExpose({open})
</script>

<template>
  <dialog ref="modal-ref" class="modal">
    <div class="modal-box w-[480px] h-[600px] max-w-none flex flex-col p-0">
      <!-- 头部 -->
      <div class="flex items-center gap-3 px-4 py-3 border-b border-base-300 shrink-0">
        <div class="avatar">
          <div class="w-10 rounded-full">
            <img src="/avatars/schedule-bot-1.svg" alt="日程助手" />
          </div>
        </div>
        <div>
          <h3 class="font-bold text-sm">日程助手</h3>
          <p class="text-xs text-base-content/50">用自然语言管理你的日程</p>
        </div>
        <form method="dialog" class="ml-auto">
          <button class="btn btn-sm btn-circle btn-ghost">✕</button>
        </form>
      </div>

      <!-- 消息列表 -->
      <div ref="scroll-ref" class="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        <div
          v-for="(msg, index) in messages"
          :key="index"
          class="chat"
          :class="msg.role === 'user' ? 'chat-end' : 'chat-start'"
        >
          <div v-if="msg.role === 'ai'" class="chat-image avatar">
            <div class="w-8 rounded-full">
              <img src="/avatars/schedule-bot-1.svg" alt="" />
            </div>
          </div>
          <div
            class="chat-bubble whitespace-pre-wrap break-all text-sm"
            :class="msg.role === 'user' ? 'chat-bubble-primary' : ''"
          >{{ msg.content }}<span v-if="isLoading && index === messages.length - 1 && msg.role === 'ai'" class="loading loading-dots loading-xs ml-1"></span></div>
        </div>
      </div>

      <!-- 输入框 -->
      <div class="shrink-0 px-4 py-3 border-t border-base-300">
        <form @submit.prevent="handleSend" class="flex gap-2">
          <input
            ref="input-ref"
            v-model="message"
            @keydown="handleKeydown"
            class="input input-bordered flex-1"
            placeholder="输入日程，如：明天下午3点开会"
            :disabled="isLoading"
          />
          <button class="btn btn-primary" :disabled="isLoading || !message.trim()">
            发送
          </button>
        </form>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button>close</button>
    </form>
  </dialog>
</template>

<style scoped>
</style>
