'use client'

import React, { useState } from 'react'
import {
  CheckCheck,
  ExternalLink,
  ShieldCheck,
  Volume2,
  VolumeX,
} from 'lucide-react'
import type { RecoveryCase } from '@/lib/api'
import { formatCustomerName } from '@/lib/format'
import { SIMULATED_PAYMENT_LINK_PREFIX } from '@/lib/constants'
import { RazorpaySymbol, WhatsAppIcon } from '@/components/ui/BrandIcons'

interface WhatsAppPreviewProps {
  caseItem: RecoveryCase
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(rupees)
}

export function WhatsAppPreview({ caseItem }: WhatsAppPreviewProps) {
  const [lang, setLang] = useState<'en' | 'hi'>('en')

  const amountPaise = caseItem.amount_paise
  const discountPaise = caseItem.discount_paise_granted
  const payablePaise = amountPaise - discountPaise
  // Only the issued link; one derived from the case id resolves to nothing.
  const paymentLinkUrl = caseItem.payment_link_url ?? null
  const isSimulatedLink = (caseItem.payment_link_id ?? '').startsWith(
    SIMULATED_PAYMENT_LINK_PREFIX,
  )
  const customerName = formatCustomerName(caseItem.failure_event.customer_id)

  const isMandate =
    caseItem.failure_event.payment_rail === 'UPI_AUTOPAY' ||
    caseItem.failure_event.payment_rail === 'ENACH'

  const defaultMsgEn =
    discountPaise > 0
      ? `Hi ${customerName}, your recent payment of ${formatINR(amountPaise)} was interrupted. Complete your payment now with an instant ${formatINR(discountPaise)} discount!`
      : `Hi ${customerName}, we noticed your payment of ${formatINR(amountPaise)} was delayed. Please click below to securely complete your payment.`

  const defaultMsgHi =
    discountPaise > 0
      ? `Namaste ${customerName}, aapka ${formatINR(amountPaise)} ka payment complete nahi ho paya. Abhi pay karein aur payein instant ${formatINR(discountPaise)} discount!`
      : `Namaste ${customerName}, aapka ${formatINR(amountPaise)} ka payment process nahi ho paya. Kripya neeche diye link se turant payment complete karein.`

  const draftedEn = caseItem.dunning_message_en
  const draftedHi = caseItem.dunning_message_hi

  // Discover drafting model or engine from audit trail
  const draftEntry = caseItem.audit_trail.find(
    (a) =>
      a.event_name === 'agent.message_drafted' ||
      a.event_name === 'agent.plan_formulated',
  )
  const modelUsed =
    draftEntry?.model_metadata?.model || 'deterministic-rules-v1'
  const isAgentDrafted =
    !draftEntry?.model_metadata?.used_fallback &&
    modelUsed !== 'deterministic-rules-v1'

  const messageText =
    lang === 'en' ? draftedEn || defaultMsgEn : draftedHi || defaultMsgHi
  const [isPlayingAudio, setIsPlayingAudio] = useState(false)

  const handleToggleVoice = () => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
    if (isPlayingAudio) {
      window.speechSynthesis.cancel()
      setIsPlayingAudio(false)
      return
    }

    const utterance = new SpeechSynthesisUtterance(messageText)
    utterance.lang = lang === 'hi' ? 'hi-IN' : 'en-IN'
    utterance.rate = 0.92
    utterance.pitch = 1.0
    utterance.onend = () => {
      setIsPlayingAudio(false)
    }
    utterance.onerror = () => {
      setIsPlayingAudio(false)
    }
    setIsPlayingAudio(true)
    window.speechSynthesis.speak(utterance)
  }

  return (
    <div className="overflow-hidden rounded-panel border border-border bg-surface shadow-sm">
      {/* WhatsApp Chat Header */}
      <div className="flex items-center justify-between bg-[#075E54] px-4 py-3 text-white">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-xs font-bold text-[#075E54] shadow-xs">
            <RazorpaySymbol className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold">
                Razorpay Verified Merchant
              </span>
              <ShieldCheck className="h-3.5 w-3.5 text-[#25D366]" />
              <WhatsAppIcon className="h-3.5 w-3.5" />
            </div>
            <span className="block text-[10px] text-white/80">
              +91 98765 00000 · Official Recovery Bot
            </span>
          </div>
        </div>

        {/* Controls: Voice Synthesis + Language Switcher */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleToggleVoice}
            title={
              isPlayingAudio
                ? 'Stop voice call'
                : 'Simulate voice recovery call'
            }
            className={`flex items-center gap-1 rounded-control px-2 py-1 text-[10px] transition-colors ${
              isPlayingAudio
                ? 'animate-pulse bg-red-500 text-white'
                : 'bg-black/20 text-white hover:bg-black/30'
            }`}
          >
            {isPlayingAudio ? (
              <>
                <VolumeX className="h-3 w-3" />
                <span>Stop</span>
              </>
            ) : (
              <>
                <Volume2 className="h-3 w-3" />
                <span>Voice</span>
              </>
            )}
          </button>

          <div className="flex items-center gap-1 rounded-control bg-black/20 p-0.5 text-[10px]">
            <button
              type="button"
              onClick={() => {
                if (isPlayingAudio && typeof window !== 'undefined')
                  window.speechSynthesis.cancel()
                setIsPlayingAudio(false)
                setLang('en')
              }}
              className={`cursor-pointer rounded px-1.5 py-0.5 ${
                lang === 'en'
                  ? 'bg-white font-bold text-[#075E54]'
                  : 'text-white/80'
              }`}
            >
              EN
            </button>
            <button
              type="button"
              onClick={() => {
                if (isPlayingAudio && typeof window !== 'undefined')
                  window.speechSynthesis.cancel()
                setIsPlayingAudio(false)
                setLang('hi')
              }}
              className={`cursor-pointer rounded px-1.5 py-0.5 ${
                lang === 'hi'
                  ? 'bg-white font-bold text-[#075E54]'
                  : 'text-white/80'
              }`}
            >
              HI
            </button>
          </div>
        </div>
      </div>

      {/* Model & Drafting Origin Bar */}
      <div className="flex items-center justify-between border-b border-black/5 bg-[#054C44] px-3.5 py-1 text-[10px] text-white/90">
        <span className="flex items-center gap-1">
          <span
            className={`h-1.5 w-1.5 rounded-full ${isAgentDrafted ? 'animate-pulse bg-[#25D366]' : 'bg-white/60'}`}
          />
          {isAgentDrafted
            ? 'AI Personalized Outreach'
            : 'Deterministic Rules Template'}
        </span>
        <span className="max-w-[180px] truncate text-white/70">
          {modelUsed}
        </span>
      </div>

      {/* WhatsApp Chat Background Body */}
      <div className="flex min-h-[220px] flex-col justify-end space-y-3 bg-[#EFEAE2] p-4 dark:bg-[#0B141A]">
        {/* Outbound Dunning Bubble */}
        <div className="max-w-[85%] space-y-2 self-start rounded-panel rounded-tl-xs border border-black/5 bg-white p-3 shadow-xs dark:border-white/5 dark:bg-[#1F2C34]">
          <p className="text-xs leading-relaxed text-[#111B21] dark:text-[#E9EDEF]">
            {messageText}
          </p>

          {/* Interactive Single-Use Payment Link Card */}
          <div className="space-y-1.5 rounded-control border border-black/10 bg-[#F0F2F5] p-2.5 dark:border-white/10 dark:bg-[#111B21]">
            <div className="flex items-center justify-between text-[11px] font-bold text-ink">
              <span>Razorpay Secure Link</span>
              <span className="text-recovered">{formatINR(payablePaise)}</span>
            </div>
            {discountPaise > 0 && (
              <div className="flex items-center justify-between text-[10px] text-ink-muted">
                <span>Original: {formatINR(amountPaise)}</span>
                <span className="font-semibold text-accent">
                  Saved {formatINR(discountPaise)}
                </span>
              </div>
            )}
            {paymentLinkUrl ? (
              <div className="space-y-1 pt-1">
                <div className="flex items-center gap-1 text-[10px] text-accent">
                  <ExternalLink className="h-3 w-3" />
                  <span className="break-all">{paymentLinkUrl}</span>
                </div>
                {isSimulatedLink && (
                  <span className="text-[9px] text-ink-muted">
                    Sandbox link - no live gateway call was made.
                  </span>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-1 pt-1 text-[10px] text-ink-muted">
                <ExternalLink className="h-3 w-3" />
                <span>No payment link issued for this case yet.</span>
              </div>
            )}
          </div>

          <div className="flex items-center justify-end gap-1 text-[9px] text-ink-muted">
            <span>
              {new Date(caseItem.created_at).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
            <CheckCheck className="h-3.5 w-3.5 text-[#53BDEB]" />
          </div>
        </div>

        {/* Informational Mandate Guidance */}
        {isMandate && (
          <div className="text-center">
            <span className="inline-block rounded-control bg-white/80 px-2.5 py-1 text-[10px] text-ink-muted shadow-2xs dark:bg-[#1F2C34]/80">
              Automatic retry scheduled per RBI mandate circular
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
