<script setup>
import Message from "@/components/character/chat_field/chat_history/message/Message.vue";
import {nextTick, onBeforeUnmount, onMounted, useTemplateRef, watch} from "vue";
import api from "@/js/http/api.js";

const props = defineProps(['history', 'friendId', 'character', 'inline', 'selectMode', 'selectedIds'])
const emit = defineEmits(['pushFrontMessage', 'toggleSelect'])
const scrollRef = useTemplateRef('scroll-ref')
const sentinelRef = useTemplateRef('sentinel-ref')
let isLoading = false
let hasMessages = true
let lastMessageId = 0

function checkSentinelVisible() {  // 判断哨兵是否能被看到
  if (!sentinelRef.value) return false

  const sentinelRect = sentinelRef.value.getBoundingClientRect()
  const scrollRect = scrollRef.value.getBoundingClientRect()
  return sentinelRect.top < scrollRect.bottom && sentinelRect.bottom > scrollRect.top
}

async function loadMore() {
  if (isLoading || !hasMessages) return
  isLoading = true

  let newMessages = []
  try {
    const res = await api.get('/api/friend/message/get_history/', {
      params: {
        last_message_id: lastMessageId,
        friend_id: props.friendId,
      }
    })
    const data = res.data
    if (data.result === 'success') {
      newMessages = data.messages
    }
  } catch (err) {
  } finally {
    isLoading = false

    if (newMessages.length === 0) {
      hasMessages = false
    } else {
      const oldHeight = scrollRef.value.scrollHeight
      const oldTop = scrollRef.value.scrollTop

      for (const m of newMessages) {
        emit('pushFrontMessage', {
          role: 'ai',
          content: m.output,
          id: crypto.randomUUID(),
          dbId: m.id,
        })
        emit('pushFrontMessage', {
          role: 'user',
          content: m.user_message,
          id: crypto.randomUUID(),
          dbId: m.id,
        })
        lastMessageId = m.id
      }

      await nextTick()

      const newHeight = scrollRef.value.scrollHeight
      scrollRef.value.scrollTop = oldTop + newHeight - oldHeight

      if (checkSentinelVisible()) {
        await loadMore()
      }
    }
  }
}

// 切换对话时重新加载
watch(() => props.friendId, (newId, oldId) => {
  if (newId && newId !== oldId) {
    reset()
    nextTick(() => {
      loadMore()
    })
  }
})

let observer = null
onMounted(async () => {
  await loadMore()

  observer = new IntersectionObserver(
    entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          loadMore()
        }
      })
    },
    {root: null, rootMargin: '2px', threshold: 0}
  )

  observer.observe(sentinelRef.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
})

async function scrollToBottom() {
  await nextTick()

  scrollRef.value.scrollTop = scrollRef.value.scrollHeight
}

function reset() {
  isLoading = false
  hasMessages = true
  lastMessageId = 0
}

defineExpose({
  scrollToBottom,
  reset,
})
</script>

<template>
  <div ref="scroll-ref" :class="inline
    ? 'flex-1 w-full overflow-y-scroll no-scrollbar pt-18 pb-20 px-2'
    : 'absolute top-18 left-0 w-90 h-112 overflow-y-scroll no-scrollbar'">
    <div ref="sentinel-ref" class="h-2"></div>
    <Message
        v-for="message in history"
        :key="message.id"
        :message="message"
        :character="character"
        :selectMode="selectMode"
        :selected="selectedIds?.has(message.id)"
        @toggleSelect="emit('toggleSelect', message.id)"
    />
  </div>
</template>

<style scoped>
/* 隐藏 Chrome, Safari 和 Opera 的滚动条 */
.no-scrollbar::-webkit-scrollbar {
  display: none;
}

/* 隐藏 IE, Edge 和 Firefox 的滚动条 */
.no-scrollbar {
  -ms-overflow-style: none; /* IE and Edge */
  scrollbar-width: none; /* Firefox */
}
</style>