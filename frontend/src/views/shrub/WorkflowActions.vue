<template>
  <div class="workflow-actions">
    <div v-for="line in lines" :key="line.key" class="workflow-line">
      <button
        class="link"
        type="button"
        :disabled="busyKey === line.key"
        @click="onClick(line)"
      >
        {{ labelFor(line) }}
      </button>
      <span class="stage-tag" :data-stage="stageOf(line)">{{ stageOf(line) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import { request } from '@/api/client'

export type ShrubRow = {
  id: number
  灌木编号?: string
  栽植面积?: string | number
  原始栽植面积?: number
  补植面积合计?: number
  有效栽植面积?: number
  灌木状态?: string
  修剪状态?: string
  防治状态?: string
  补植状态?: string
  has_pest?: boolean
  补植明细?: Array<Record<string, string | number>>
  [key: string]: unknown
}

type ActionKey = '安排修剪' | '防治处理' | '补植登记'
type StageField = '修剪状态' | '防治状态' | '补植状态'
type Line = { key: ActionKey; stageField: StageField }

const props = defineProps<{ row: ShrubRow }>()
const emit = defineEmits<{
  (e: 'finished', message: string): void
  (e: 'failed', message: string): void
}>()

const STAGES = ['待处理', '处理中', '已完成'] as const
const lines: Line[] = [
  { key: '安排修剪', stageField: '修剪状态' },
  { key: '防治处理', stageField: '防治状态' },
  { key: '补植登记', stageField: '补植状态' },
]
const busyKey = ref<ActionKey | ''>('')

function stageOf(line: Line): string {
  return String(props.row[line.stageField] ?? STAGES[0])
}

function labelFor(line: Line): string {
  const stage = stageOf(line)
  if (stage === STAGES[1]) {
    return line.key === '安排修剪' ? '完成修剪' : line.key === '防治处理' ? '完成防治' : '完成补植'
  }
  if (stage === STAGES[2]) {
    return line.key === '安排修剪' ? '修剪已完成' : line.key === '防治处理' ? '防治已完成' : '已补植'
  }
  return line.key
}

function askReplantDetail(stage: string): Record<string, string> | null {
  const area = window.prompt(
    stage === STAGES[1]
      ? '补植处理中：更正补植面积请输入正数（㎡），留空则确认完工'
      : '请输入补植面积（㎡，必填正数）',
  )
  if (area === null) return null
  const trimmed = area.trim()
  if (trimmed === '') {
    return stage === STAGES[1] ? {} : null // 待处理不允许空面积；处理中空=完工
  }
  if (Number.isNaN(Number(trimmed)) || Number(trimmed) <= 0) {
    emit('failed', '补植面积必须为大于 0 的数值，请填写后重试')
    return null
  }
  const count = window.prompt('请输入补植数量（可留空）', '')
  return { 补植面积: trimmed, ...(count && count.trim() ? { 补植数量: count.trim() } : {}) }
}

async function onClick(line: Line) {
  const stage = stageOf(line)
  if (stage === STAGES[2]) {
    emit(
      'failed',
      line.key === '补植登记'
        ? '该灌木已完成补植，同一灌木编号不允许重复补植'
        : line.key === '防治处理'
          ? '该灌木当前没有在处理的病虫害，无需防治'
          : '修剪作业已完成，不能重复提交或跳级推进',
    )
    return
  }

  const values: Record<string, string> = { action: line.key }
  if (line.key === '补植登记') {
    const detail = askReplantDetail(stage)
    if (detail === null) return
    Object.assign(values, detail)
  }

  busyKey.value = line.key
  try {
    const response = await request(`/api/shrub/${props.row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = (await response.json().catch(() => null)) as
      | { ok?: boolean; message?: string }
      | null
    if (!response.ok || !payload || payload.ok !== true) {
      // 关键修复：解析后端 ok/message，失败说明原因且状态不变，用户可直接重试
      emit('failed', payload?.message || '灌木管理动作未生效，请稍后重试')
      return
    }
    emit('finished', payload.message || '操作已完成')
  } catch (error) {
    emit('failed', error instanceof Error ? error.message : '灌木管理操作失败')
  } finally {
    busyKey.value = ''
  }
}
</script>

<style scoped>
.workflow-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.workflow-line {
  display: flex;
  align-items: center;
  gap: 8px;
}
.stage-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  border: 1px solid var(--border);
  color: var(--muted);
  white-space: nowrap;
}
.stage-tag[data-stage='待处理'] {
  color: #b54708;
  border-color: #fedf89;
  background: #fffaeb;
}
.stage-tag[data-stage='处理中'] {
  color: #175cd3;
  border-color: #b2ccff;
  background: #eff8ff;
}
.stage-tag[data-stage='已完成'] {
  color: #067647;
  border-color: #abefc6;
  background: #ecfdf3;
}
.link:disabled {
  color: var(--muted);
  cursor: not-allowed;
}
</style>
