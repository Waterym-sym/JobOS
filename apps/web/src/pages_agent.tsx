import { useState } from 'react'

/**
 * 新建对话 —— Agent 中心外壳（本期只做 UI，不接后端）。
 * 提交消息后显示占位系统回复，后续接本机 Agent runner。
 */

type ChatMessage = {
  id: string
  role: 'user' | 'system'
  text: string
}

const QUICK_INTENTS: { icon: string; label: string; hint: string }[] = [
  { icon: '🔍', label: '智能筛选岗位', hint: '按条件从岗位池中筛选合适的岗位' },
  { icon: '📋', label: '简历诊断', hint: '对照目标 JD 分析简历匹配度' },
  { icon: '📦', label: '生成投递包', hint: '为候选岗位生成简历与招呼语' },
  { icon: '📊', label: '复盘分析', hint: '回顾投递漏斗与转化数据' },
]

let msgSeq = 0
function nextId() {
  msgSeq += 1
  return `m-${Date.now()}-${msgSeq}`
}

export function AgentChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')

  const send = (text?: string) => {
    const content = (text ?? input).trim()
    if (!content) return
    const userMsg: ChatMessage = { id: nextId(), role: 'user', text: content }
    const systemMsg: ChatMessage = {
      id: nextId(),
      role: 'system',
      text: 'Agent 后端待接入：当前仅为 UI 外壳，消息不会发送到任何服务。',
    }
    setMessages((prev) => [...prev, userMsg, systemMsg])
    setInput('')
  }

  return (
    <div className="agent-page">
      {messages.length === 0 ? (
        <div className="agent-welcome">
          <div className="agent-welcome-hero">
            <span className="agent-welcome-mark" aria-hidden="true">JO</span>
            <h1>想让 Agent 帮你做什么？</h1>
            <p>所有对话与数据只留在本机，Agent 不会把聊天原文发送到第三方。</p>
          </div>

          <div className="agent-intent-grid">
            {QUICK_INTENTS.map((intent) => (
              <button
                key={intent.label}
                type="button"
                className="agent-intent-card"
                onClick={() => send(intent.label)}
              >
                <span className="agent-intent-icon" aria-hidden="true">{intent.icon}</span>
                <div>
                  <strong>{intent.label}</strong>
                  <span>{intent.hint}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="agent-messages">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`agent-message agent-message--${msg.role}`}
            >
              <span className="agent-message-role" aria-hidden="true">
                {msg.role === 'user' ? '我' : 'Agent'}
              </span>
              <div className="agent-message-bubble">{msg.text}</div>
            </div>
          ))}
        </div>
      )}

      <div className="agent-input-bar">
        <textarea
          className="agent-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
          placeholder="输入你的需求，Enter 发送，Shift+Enter 换行"
          rows={1}
        />
        <button
          type="button"
          className="agent-send"
          onClick={() => send()}
          disabled={!input.trim()}
        >
          发送
        </button>
      </div>
    </div>
  )
}
