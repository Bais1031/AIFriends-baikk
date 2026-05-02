<script setup>
import {ref, watch} from "vue";

const props = defineProps(['speaker'])
const mySpeaker = ref(props.speaker || 'longanyang')

watch(() => props.speaker, newVal => {
  if (newVal) mySpeaker.value = newVal
})

defineExpose({
  mySpeaker,
})
</script>

<template>
  <fieldset class="fieldset">
    <label class="label text-base">音色选择</label>
    <select v-model="mySpeaker" class="select w-60">
      <option disabled value="">请选择音色</option>
      <optgroup label="男声">
        <option value="longanyang">龙卷杨</option>
        <option value="longshuo">龙硕</option>
        <option value="longfei">龙飞</option>
        <option value="longshu">龙叔</option>
        <option value="longbai">龙白</option>
      </optgroup>
      <optgroup label="女声">
        <option value="longyue">龙悦</option>
        <option value="longjing">龙静</option>
        <option value="longmiao">龙淼</option>
        <option value="longxia">龙夏</option>
        <option value="longqi">龙琦</option>
      </optgroup>
    </select>
  </fieldset>
</template>
