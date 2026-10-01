<template>
  <section class="page" data-module="shrub">
    <header class="page-head">
      <div>
        <h2>灌木管理</h2>
        <p class="page-desc">维护灌木，围绕修剪、防治、补植三条工作流推进养护作业，栽植面积随补植明细实时重算。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记灌木</button>
        <button class="btn" type="button" @click="exportRows">导出灌木管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}<small v-if="item.unit"> {{ item.unit }}</small></strong>
      </article>
    </div>

    <div v-if="successMessage" class="feedback success">{{ successMessage }}</div>
    <div v-if="errorMessage" class="feedback error">{{ errorMessage }}</div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>灌木编号</span>
        <input v-model="keyword" placeholder="按灌木编号检索" />
      </label>
      <label class="filter-item">
        <span>灌木状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>修剪/防治/补植进度</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <RouterLink v-if="column === '灌木编号'" class="link" :to="`/shrub/${row.id}`">
              {{ row[column] }}
            </RouterLink>
            <span v-else :class="{ 'status-badge': column === '灌木状态', [badgeClass(row)]: column === '灌木状态' }">
              {{ row[column] ?? '—' }}
            </span>
          </td>
          <td class="progress-cell">
            <span>{{ row['修剪进度'] }}</span> / <span>{{ row['防治进度'] }}</span> / <span>{{ row['补植进度'] }}</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action.name"
              class="link"
              :class="{ primary: action.primary, disabled: busyKey === `${row.id}-${action.name}` }"
              type="button"
              :disabled="busyKey === `${row.id}-${action.name}`"
              @click="runAction(action.name, row)"
            >
              {{ busyKey === `${row.id}-${action.name}` ? '提交中…' : action.name }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无符合条件的灌木数据，可先登记灌木</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条灌木记录</span>
      <span v-if="lastErrorDetail" class="error-text">上次失败原因：{{ lastErrorDetail }}（状态未改变，可直接重试）</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Stat = { label: string; value: number | string; unit?: string }

const ENDPOINT = '/api/shrub'
const columns = ['灌木编号', '品种名称', '栽植面积', '修剪周期', '高度范围', '花开季节', '管护人员', '灌木状态']
const actions = [
  { name: '安排修剪', primary: false },
  { name: '防治处理', primary: false },
  { name: '补植登记', primary: true },
]
const statuses = ['正常', '待修剪', '病虫害', '已补植']

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<Stat[]>([
  { label: '正常灌木', value: 0 },
  { label: '待修剪灌木', value: 0 },
  { label: '病虫害灌木', value: 0 },
  { label: '已补植灌木', value: 0 },
  { label: '栽植总面积（含补植）', value: 0, unit: '㎡' },
  { label: '补植累计面积', value: 0, unit: '㎡' },
])
const errorMessage = ref('')
const successMessage = ref('')
const lastErrorDetail = ref('')
const busyKey = ref('')
const keyword = ref('')
const statusFilter = ref('')

function badgeClass(row: Row): string {
  switch (row['灌木状态']) {
    case '待修剪':
      return 'badge-prune'
    case '病虫害':
      return 'badge-pest'
    case '已补植':
      return 'badge-replant'
    default:
      return 'badge-normal'
  }
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = ''
  successMessage.value = ''
  const code = window.prompt('登记灌木：请输入灌木编号（同一编号重复提交只算一次）')
  if (code === null) {
    return
  }
  const name = window.prompt('请输入品种名称')
  if (name === null) {
    return
  }
  const area = window.prompt('请输入栽植面积（平方米）')
  if (area === null) {
    return
  }
  void submitCreate({ 灌木编号: code, 品种名称: name, 栽植面积: area })
}

async function submitCreate(values: Record<string, string>) {
  try {
    const response = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values }) })
    const payload = (await response.json().catch(() => null)) as { ok: boolean; message: string } | null
    if (!response.ok || !payload) {
      throw new Error('灌木登记未送达，请稍后重试')
    }
    if (!payload.ok) {
      errorMessage.value = payload.message
      lastErrorDetail.value = payload.message
      return
    }
    successMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '灌木登记失败，可重试'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  busyKey.value = `${row.id}-${action}`
  try {
    const values: Record<string, string> = { action }
    if (action === '补植登记' && row['补植进度'] === '处理中') {
      const current = String(row['栽植面积'] ?? '')
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
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = (await response.json().catch(() => null)) as
      | { ok: boolean; message: string }
      | null
    if (!response.ok || !payload) {
      throw new Error('灌木管理动作未生效，请检查网络后重试')
    }
    if (!payload.ok) {
      // 跳级、重复、已补植再修剪等：明确展示原因，数据未改动，用户可直接重试。
      errorMessage.value = payload.message
      lastErrorDetail.value = payload.message
      return
    }
    successMessage.value = payload.message
    lastErrorDetail.value = ''
    await reload()
  } catch (error) {
    const message = error instanceof Error ? error.message : '灌木管理操作失败，可重试'
    errorMessage.value = message
    lastErrorDetail.value = message
  } finally {
    busyKey.value = ''
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) {
    query.set('keyword', keyword.value)
  }
  if (statusFilter.value) {
    query.set('status', statusFilter.value)
  }
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/summary`),
    ])
    if (!listResponse.ok) {
      throw new Error('灌木列表读取失败')
    }
    const payload = (await listResponse.json()) as { items: Row[]; total: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (summaryResponse.ok) {
      const summary = (await summaryResponse.json()) as {
        counts: Record<string, number>
        total_area: number
        replant_area: number
      }
      stats.value = [
        { label: '正常灌木', value: summary.counts['正常'] ?? 0 },
        { label: '待修剪灌木', value: summary.counts['待修剪'] ?? 0 },
        { label: '病虫害灌木', value: summary.counts['病虫害'] ?? 0 },
        { label: '已补植灌木', value: summary.counts['已补植'] ?? 0 },
        { label: '栽植总面积（含补植）', value: summary.total_area, unit: '㎡' },
        { label: '补植累计面积', value: summary.replant_area, unit: '㎡' },
      ]
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '灌木管理列表读取失败'
  }
}

onMounted(reload)
</script>
