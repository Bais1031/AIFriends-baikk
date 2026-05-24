<script setup>
import {nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch} from "vue";
import api from "@/js/http/api.js";

const props = defineProps(['activeFriendId'])
const emit = defineEmits(['select'])

const friends = ref([])
const isLoading = ref(false)
const hasFriends = ref(true)
const searchQuery = ref('')
const sentinelRef = useTemplateRef('sentinel-ref')
let searchTimer = null

function formatTime(isoString) {
  if (!isoString) return ''
  const date = new Date(isoString)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  if (isToday) {
    return date.toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'})
  }
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  if (date.toDateString() === yesterday.toDateString()) {
    return '昨天'
  }
  return date.toLocaleDateString('zh-CN', {month: 'numeric', day: 'numeric'})
}

function checkSentinelVisible() {
  if (!sentinelRef.value) return false
  const rect = sentinelRef.value.getBoundingClientRect()
  return rect.top < window.innerHeight && rect.bottom > 0
}

async function loadMore(reset = false) {
  if (isLoading.value || (!reset && !hasFriends.value)) return
  isLoading.value = true

  if (reset) {
    friends.value = []
    hasFriends.value = true
  }

  let newFriends = []
  try {
    const params = {items_count: friends.value.length}
    if (searchQuery.value.trim()) {
      params.search_query = searchQuery.value.trim()
    }
    const res = await api.get('/api/friend/get_list/', {params})
    const data = res.data
    if (data.result === 'success') {
      newFriends = data.friends
    }
  } catch (err) {
  } finally {
    isLoading.value = false
    if (newFriends.length === 0) {
      hasFriends.value = false
    } else {
      friends.value.push(...newFriends)
      await nextTick()
      if (checkSentinelVisible()) {
        await loadMore()
      }
    }
  }
}

function handleSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    loadMore(true)
  }, 300)
}

async function selectFriend(friend) {
  try {
    const res = await api.post('/api/friend/get_or_create/', {
      friend_id: friend.id,
    })
    const data = res.data
    if (data.result === 'success') {
      emit('select', data.friend)
    }
  } catch (err) {
  }
}

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

  if (sentinelRef.value) {
    observer.observe(sentinelRef.value)
  }
})

onBeforeUnmount(() => {
  observer?.disconnect()
  clearTimeout(searchTimer)
})
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- 搜索框 -->
    <div class="p-3 border-b border-base-300">
      <label class="input input-sm w-full flex items-center gap-2 bg-base-200">
        <svg class="w-4 h-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          v-model="searchQuery"
          @input="handleSearch"
          type="text"
          placeholder="搜索对话..."
          class="grow bg-transparent outline-none"
        />
      </label>
    </div>

    <!-- 对话列表 -->
    <div class="flex-1 overflow-y-auto">
      <div
        v-for="friend in friends"
        :key="friend.id"
        @click="selectFriend(friend)"
        class="flex items-center gap-3 px-3 py-3 cursor-pointer transition-colors hover:bg-base-200 border-l-2 border-l-transparent"
        :class="{'bg-base-200 border-l-2 border-l-primary': activeFriendId === friend.id}"
      >
        <!-- 头像 -->
        <div class="avatar shrink-0">
          <div class="w-12 rounded-full">
            <img :src="friend.character.photo" :alt="friend.character.name" />
          </div>
        </div>

        <!-- 对话信息 -->
        <div class="flex-1 min-w-0">
          <div class="flex items-center justify-between">
            <span class="font-medium text-sm truncate">{{ friend.character.name }}</span>
            <span class="text-xs text-base-content/50 shrink-0 ml-2">{{ formatTime(friend.last_message_time) }}</span>
          </div>
          <p class="text-xs text-base-content/60 truncate mt-1">
            {{ friend.last_message || '暂无消息' }}
          </p>
        </div>
      </div>

      <!-- 加载状态 -->
      <div v-if="isLoading" class="py-4 text-center text-sm text-base-content/40">加载中...</div>
      <div v-else-if="!hasFriends && friends.length === 0" class="py-8 text-center text-sm text-base-content/40">
        {{ searchQuery ? '没有找到匹配的对话' : '暂无对话' }}
      </div>
    </div>

    <!-- 无限滚动哨兵 -->
    <div ref="sentinel-ref" class="h-1"></div>
  </div>
</template>

<style scoped>
</style>
