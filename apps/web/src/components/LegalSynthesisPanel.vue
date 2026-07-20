<script setup lang="ts">
import ConceptHyperlink from './ConceptHyperlink.vue'
import type { Synthesis } from '../types/api'

defineProps<{
  synthesis: Synthesis
}>()
</script>

<template>
  <div class="synthesis-panel">
    <h3>小综合</h3>
    <p class="generated-by">生成方式：{{ synthesis.generated_by }}（确定性模板，非模型自由生成）</p>
    <p class="synthesis-text">
      <template v-for="(segment, idx) in synthesis.text_segments" :key="idx">
        <ConceptHyperlink
          v-if="segment.concept_id"
          :concept-id="segment.concept_id"
          :text="segment.text"
        />
        <template v-else>{{ segment.text }}</template>
      </template>
    </p>
  </div>
</template>

<style scoped>
.synthesis-panel {
  background: #fafbfc;
  border-left: 1px solid #eee;
  padding: 20px;
  height: 100%;
  overflow-y: auto;
}
.generated-by {
  color: #999;
  font-size: 12px;
}
.synthesis-text {
  line-height: 1.9;
}
</style>
