<template>
  <section class="page" data-module="shrub-detail">
    <header class="page-head">
      <div>
        <h2>灌木详情</h2>
        <p class="page-desc">清单页与本页共用同一份接口数据，花开季节、栽植面积等字段完全一致。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/shrub">返回灌木清单</RouterLink>
      </div>
    </header>

    <p v-if="errorText" class="feedback feedback-err" role="alert">{{ errorText }}</p>
    <p v-else-if="feedback.ok" class="feedback feedback-ok" role="status">{{ feedback.text }}</p>
    <p v-else-if="feedback.text" class="feedback feedback-err" role="alert">{{ feedback.text }}</p>

    <div v-if="entry" class="detail-grid">
      <article v-for="field in detailFields" :key="field" class="detail-item">
        <span class="detail-label">{{ field }}</span>
        <strong class="detail-value">{{ entry[field] ?? '—' }}</strong>
      </article>
      <article class="detail-item">
        <span class="detail-label">有效栽植面积</span>
        <strong class="detail-value">{{ entry['有效栽植面积'] }} ㎡</strong>
      </article>
      <article class="detail-item">
        <span class="detail-label">原始栽植面积</span>
        <strong class="detail-value">{{ entry['原始栽植面积'] }} ㎡</strong>
      </article>
      <article class="detail-item">
        <span class="detail-label">补植面积合计</span>
        <strong class="detail-value">{{ entry['补植面积合计'] }} ㎡</strong>
      </article>
    </div>

    <div v-if="entry" class="stage-panel">
      <h3>作业进度（只能按 待处理 → 处理中 → 已完成 推进）</h3>
      <WorkflowActions :row="entry" @finished="onFinished" @failed="onFailed" />
    </div>

    <div v-if="entry" class="replant-panel">
      <h3>补植明细（栽植面积按此重算）</h3>
      <table v-if="entry['补植明细']?.length" class="data-table">
        <thead>
          <tr><th>补植面积(㎡)</th><th>补植数量</th><th>补植日期</th><th>状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="(d, i) in entry['补植明细']" :key="i">
            <td>{{ d['补植面积'] }}</td>
            <td>{{ d['补植数量'] || '—' }}</td>
            <td>{{ d['补植日期'] }}</td>
            <td>{{ d['状态'] }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="page-desc">暂无补植明细。</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'
import WorkflowActions, { type ShrubRow } from './WorkflowActions.vue'

const route = useRoute()
const ENDPOINT = '/api/shrub'
const detailFields = ['灌木编号', '品种名称', '栽植面积', '修剪周期', '高度范围', '花开季节', '管护人员', '灌木状态', '修剪状态', '防治状态', '补植状态']

const entry = ref<ShrubRow | null>(null)
const errorText = ref('')
const feedback = ref<{ ok: boolean; text: string }>({ ok: true, text: '' })

function onFinished(message: string) {
  feedback.value = { ok: true, text: message }
  void reload()
}

function onFailed(message: string) {
  feedback.value = { ok: false, text: message }
  void reload()
}

async function reload() {
  const id = route.params.id
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail || `灌木 ${String(id)} 不存在或已归档`)
    }
    entry.value = await response.json()
  } catch (error) {
    errorText.value = error instanceof Error ? error.message : '灌木详情读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.detail-item {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.detail-label {
  display: block;
  color: var(--muted);
  font-size: 12px;
}
.detail-value {
  font-size: 15px;
}
.stage-panel,
.replant-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 16px;
}
.stage-panel h3,
.replant-panel h3 {
  margin: 0 0 10px;
  font-size: 14px;
}
.feedback {
  margin: 0 0 10px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.feedback-ok {
  color: #067647;
  background: #ecfdf3;
  border: 1px solid #abefc6;
}
.feedback-err {
  color: #b42318;
  background: #fef3f2;
  border: 1px solid #fda29b;
}
</style>
