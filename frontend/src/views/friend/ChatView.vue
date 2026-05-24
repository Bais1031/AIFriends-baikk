<script setup>
import {ref, watch} from "vue";
import {useRoute, useRouter} from "vue-router";
import FriendIndex from "@/views/friend/FriendIndex.vue";
import ChatFieldInline from "@/components/character/chat_field/ChatFieldInline.vue";
import api from "@/js/http/api.js";

const route = useRoute()
const router = useRouter()
const friend = ref(null)
const loading = ref(false)

async function loadFriend(friendId) {
  if (!friendId) {
    friend.value = null
    return
  }
  loading.value = true
  try {
    const res = await api.post('/api/friend/get_or_create/', {
      friend_id: friendId,
    })
    const data = res.data
    if (data.result === 'success') {
      friend.value = data.friend
    }
  } catch (err) {
    friend.value = null
  } finally {
    loading.value = false
  }
}

function handleSelectConversation(friendData) {
  friend.value = friendData
  router.push({name: 'friend-chat', params: {friend_id: friendData.id}})
}

watch(() => route.params.friend_id, (newId) => {
  if (newId) {
    loadFriend(Number(newId))
  } else {
    friend.value = null
  }
}, {immediate: true})
</script>

<template>
  <div class="flex h-[calc(100vh-4rem)]">
    <!-- 左侧对话列表 -->
    <div class="w-80 min-w-80 border-r border-base-300 bg-base-100 flex flex-col">
      <FriendIndex :activeFriendId="friend?.id" @select="handleSelectConversation" />
    </div>

    <!-- 右侧聊天区域 -->
    <div class="flex-1 flex flex-col bg-base-200">
      <ChatFieldInline v-if="friend" :friend="friend" />
      <div v-else class="flex-1 flex items-center justify-center">
        <div class="text-center text-base-content/40">
          <svg class="w-20 h-20 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          <p class="text-lg">选择一个对话开始聊天</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
</style>
