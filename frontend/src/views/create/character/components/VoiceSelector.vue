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
        <option value="longanyang">龙卷杨（沉稳）</option>
        <option value="longfei_v3">龙飞（活力）</option>
        <option value="longshuo_v3">龙硕（沉稳）</option>
        <option value="longshu_v3">龙叔（中年）</option>
        <option value="longlaotie_v3">龙老铁（东北）</option>
      </optgroup>
      <optgroup label="女声">
        <option value="longyue_v3">龙悦（温柔）</option>
        <option value="longyuan_v3">龙媛（知性）</option>
        <option value="longmiao_v3">龙淼（甜美）</option>
        <option value="longxiaochun_v3">龙小春（活泼）</option>
        <option value="longxiaoxia_v3">龙小夏（清新）</option>
        <option value="longxiaoyun_v3">龙小云（可爱）</option>
      </optgroup>
    </select>
  </fieldset>
</template>
