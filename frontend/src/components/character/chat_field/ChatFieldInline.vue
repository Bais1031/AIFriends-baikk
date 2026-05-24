<script setup>
import {computed, nextTick, ref, useTemplateRef, watch} from "vue";
import InputField from "@/components/character/chat_field/input_field/InputField.vue";
import CharacterPhotoField from "@/components/character/chat_field/character_photo_field/CharacterPhotoField.vue";
import ChatHistory from "@/components/character/chat_field/chat_history/ChatHistory.vue";
import api from "@/js/http/api.js";

const props = defineProps(['friend'])
const inputRef = useTemplateRef('input-ref')
const chatHistoryRef = useTemplateRef('chat-history-ref')
const confirmRef = useTemplateRef('confirm-ref')
const history = ref([])

// 选择模式
const selectMode = ref(false)
const selectedIds = ref(new Set())

const bgStyle = computed(() => {
  if (props.friend) {
    return {
      backgroundImage: `url(${props.friend.character.background_image})`,
      backgroundSize: 'cover',
      backgroundPosition: 'center',
      backgroundRepeat: 'no-repeat',
    }
  }
  return {}
})

// 切换对话时重置状态
watch(() => props.friend?.id, () => {
  history.value = []
  exitSelectMode()
  nextTick(() => {
    inputRef.value?.focus()
  })
})

function handlePushBackMessage(msg) {
  history.value.push(msg)
  chatHistoryRef.value.scrollToBottom()
}

function handleAddToLastMessage(delta) {
  history.value.at(-1).content += delta
  chatHistoryRef.value.scrollToBottom()
}

function handlePushFrontMessage(msg) {
  history.value.unshift(msg)
}

// 选择模式操作
function enterSelectMode() {
  selectMode.value = true
  selectedIds.value = new Set()
}

function exitSelectMode() {
  selectMode.value = false
  selectedIds.value = new Set()
}

function toggleSelect(messageId) {
  const newSet = new Set(selectedIds.value)
  if (newSet.has(messageId)) {
    newSet.delete(messageId)
  } else {
    newSet.add(messageId)
  }
  selectedIds.value = newSet
}

function selectAll() {
  if (selectedIds.value.size === history.value.length) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(history.value.map(m => m.id))
  }
}

const isAllSelected = computed(() => {
  return history.value.length > 0 && selectedIds.value.size === history.value.length
})

// 清空全部
function confirmClearAll() {
  confirmRef.value?.showModal()
}

async function handleClearAll() {
  confirmRef.value?.close()
  try {
    await api.post('/api/friend/message/clear_history/', {
      friend_id: props.friend.id,
    })
    history.value = []
    chatHistoryRef.value?.reset()
  } catch (err) {
    console.error('清空聊天记录失败:', err)
  }
}

// 批量删除选中
async function handleDeleteSelected() {
  if (selectedIds.value.size === 0) return
  try {
    // 收集选中消息的数据库 ID（去重）
    const dbIds = new Set()
    for (const m of history.value) {
      if (selectedIds.value.has(m.id) && m.dbId) {
        dbIds.add(m.dbId)
      }
    }
    await api.post('/api/friend/message/delete_messages/', {
      friend_id: props.friend.id,
      message_ids: Array.from(dbIds),
    })
    history.value = history.value.filter(m => !selectedIds.value.has(m.id))
    exitSelectMode()
  } catch (err) {
    console.error('删除消息失败:', err)
  }
}
</script>

<template>
  <div class="flex flex-col h-full relative" :style="bgStyle">
    <!-- 半透明遮罩 -->
    <div class="absolute inset-0 bg-base-100/80 backdrop-blur-sm"></div>

    <!-- 内容 -->
    <div class="relative flex flex-col h-full">
      <!-- 顶部操作栏 -->
      <div class="absolute top-2 right-2 z-20 flex items-center gap-2">
        <template v-if="selectMode">
          <button @click="exitSelectMode" class="btn btn-sm btn-ghost">取消</button>
        </template>
        <template v-else>
          <div class="dropdown dropdown-end">
            <div tabindex="0" role="button" class="btn btn-sm btn-circle btn-ghost bg-black/30 backdrop-blur-sm text-white hover:bg-black/50 border-none">
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 16 16">
                <circle cx="8" cy="3" r="1.5"/>
                <circle cx="8" cy="8" r="1.5"/>
                <circle cx="8" cy="13" r="1.5"/>
              </svg>
            </div>
            <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box z-30 w-40 p-2 shadow-lg">
              <li v-if="history.length > 0"><a @click="enterSelectMode">选择消息</a></li>
              <li v-if="history.length > 0"><a @click="confirmClearAll" class="text-error">清空聊天记录</a></li>
              <li v-if="history.length === 0"><a class="text-base-content/40 pointer-events-none">暂无消息</a></li>
            </ul>
          </div>
        </template>
      </div>

      <ChatHistory
          ref="chat-history-ref"
          v-if="friend"
          :history="history"
          :friendId="friend.id"
          :character="friend.character"
          :inline="true"
          :selectMode="selectMode"
          :selectedIds="selectedIds"
          @pushFrontMessage="handlePushFrontMessage"
          @toggleSelect="toggleSelect"
      />

      <!-- 选择模式底部操作栏 -->
      <div v-if="selectMode" class="relative z-10 flex items-center justify-between px-4 py-3 bg-base-100/90 backdrop-blur-sm border-t border-base-300">
        <label class="flex items-center gap-2 cursor-pointer text-sm">
          <input type="checkbox" class="checkbox checkbox-sm checkbox-primary" :checked="isAllSelected" @change="selectAll" />
          {{ isAllSelected ? '取消全选' : '全选' }}
        </label>
        <button
          @click="handleDeleteSelected"
          class="btn btn-sm btn-error"
          :disabled="selectedIds.size === 0"
        >
          删除 ({{ selectedIds.size }})
        </button>
      </div>

      <InputField
          v-if="friend && !selectMode"
          ref="input-ref"
          :friendId="friend.id"
          :inline="true"
          @pushBackMessage="handlePushBackMessage"
          @addToLastMessage="handleAddToLastMessage"
      />
      <CharacterPhotoField v-if="friend" :character="friend.character" :inline="true" />
    </div>

    <!-- 清空确认弹窗 -->
    <dialog ref="confirm-ref" class="modal">
      <div class="modal-box">
        <h3 class="font-bold text-lg">清空聊天记录</h3>
        <p class="py-4">确定要清空与 {{ friend?.character?.name }} 的所有聊天记录吗？此操作不可撤销。</p>
        <div class="modal-action">
          <form method="dialog">
            <button class="btn">取消</button>
          </form>
          <button @click="handleClearAll" class="btn btn-error">清空</button>
        </div>
      </div>
      <form method="dialog" class="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  </div>
</template>

<style scoped>
</style>
