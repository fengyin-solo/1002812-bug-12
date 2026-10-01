<template>
  <section class="page" data-module="shrub-detail">
    <header class="page-head">
      <div>
        <h2>灌木明细</h2>
        <p class="page-desc">与清单页同一份后端数据，花开季节、灌木状态、作业进度两边保持一致。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/shrub">返回灌木清单</RouterLink>
      </div>
    </header>

    <div v-if="errorMessage" class="feedback error">{{ errorMessage }}</div>
    <div v-if="successMessage" class="feedback success">{{ successMessage }}</div>

    <article v-if="entry" class="detail-card">
      <header class="detail-head">
        <div>
          <h3>{{ entry['灌木编号'] }} · {{ entry['品种名称'] }}</h3>
          <span class="status-badge" :class="statusClass">{{ entry['灌木状态'] }}</span>
        </div>
      </header>

      <dl class="detail-grid">
        <div v-for="field in detailFields" :key="field" class="detail-item">
          <dt>{{ field }}</dt>
          <dd>{{ entry[field] ?? '—' }}</dd>
        </div>
        <div class="detail-item">
          <dt>修剪进度</dt>
          <dd>{{ entry['修剪进度'] }}</dd>
        </div>
        <div class="detail-item">
          <dt>防治进度</dt>
          <dd>{{ entry['防治进度'] }}</dd>
        </div>
        <div class="detail-item">
          <dt>补植进度</dt>
          <dd>{{ entry['补植进度'] }}</dd>
        </div>
      </dl>

      <h4>作业推进</h4>
      <p class="page-desc">每个动作只能把对应工作流推进一格：待处理 → 处理中 → 已完成，重复点击会收到明确反馈。</p>
      <div class="detail-actions">
        <button
          v-for="action in actions"
          :key="action.name"
          class="btn"
          :class="{ primary: action.primary, disabled: busyId === action.name }"
          type="button"
          :disabled="busyId === action.name"
          @click="runAction(action)"
        >
          {{ busyId === action.name ? '提交中…' : action.name }}
        </button>
      </div>

      <h4>补植明细</h4>
      <table v-if="entry['补植明细']?.length" class="data-table">
        <thead>
          <tr><th>明细编号</th><th>灌木编号</th><th>品种名称</th><th>补植面积（平方米）</th><th>补植说明</th></tr>
        </thead>
        <tbody>
          <tr v-for="detail in entry['补植明细']" :key="String(detail.id)">
            <td>{{ detail.id }}</td>
            <td>{{ detail['灌木编号'] }}</td>
            <td>{{ detail['品种名称'] }}</td>
            <td>{{ detail['补植面积'] }}</td>
            <td>{{ detail['补植说明'] || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-state">尚无补植明细；补植工作流推进到「已完成」时登记，重复提交只计一次。</p>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'

type Entry = Record<string, string | number | null> & {
  '补植明细'?: { id: number; '灌木编号': string; '品种名称': string; '补植面积': number; '补植说明': string }[]
}

const route = useRoute()
const ENDPOINT = '/api/shrub'
const detailFields = ['灌木编号', '品种名称', '栽植面积', '修剪周期', '高度范围', '花开季节', '管护人员', '灌木状态']
const actions = [
  { name: '安排修剪', primary: false },
  { name: '防治处理', primary: false },
  { name: '补植登记', primary: true },
]

const entry = ref<Entry | null>(null)
const errorMessage = ref('')
const successMessage = ref('')
const busyId = ref('')

const entryId = computed(() => Number(route.params.id))

const statusClass = computed(() => ({
  'badge-normal': entry.value?.['灌木状态'] === '正常',
  'badge-prune': entry.value?.['灌木状态'] === '待修剪',
  'badge-pest': entry.value?.['灌木状态'] === '病虫害',
  'badge-replant': entry.value?.['灌木状态'] === '已补植',
}))

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entryId.value}`)
    if (!response.ok) {
      throw new Error('灌木明细读取失败')
    }
    entry.value = (await response.json()) as Entry
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '灌木明细读取失败'
  }
}

async function runAction(action: { name: string }) {
  errorMessage.value = ''
  successMessage.value = ''
  busyId.value = action.name
  try {
    const values: Record<string, string> = { action: action.name }
    if (action.name === '补植登记' && entry.value?.['补植进度'] === '处理中') {
      const current = String(entry.value['栽植面积'] ?? '')
      const input = window.prompt(
        '补植即将完成，请登记本次补植面积（平方米，需大于 0）：',
        current && current !== '0' ? current : '',
      )
      if (input === null) {
        errorMessage.value = '已取消补植完成登记，当前进度保持「处理中」，可稍后重试'
        return
      }
      values['补植面积'] = input
    }
    const response = await request(`${ENDPOINT}/${entryId.value}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = (await response.json().catch(() => null)) as { ok: boolean; message: string } | null
    if (!response.ok || !payload) {
      throw new Error('灌木动作未送达，请检查网络后重试')
    }
    if (!payload.ok) {
      // 业务被拦下：说明原因，状态没变，用户可直接再点一次重试。
      errorMessage.value = payload.message
      return
    }
    successMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '灌木操作失败，可重试'
  } finally {
    busyId.value = ''
  }
}

onMounted(reload)
</script>
