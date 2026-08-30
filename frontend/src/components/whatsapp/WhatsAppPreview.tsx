'use client'

import React, { useState } from 'react'
import { CheckCheck, ExternalLink, ShieldCheck } from 'lucide-react'
import type { RecoveryCase } from '@/lib/api'

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

  const isMandate = caseItem.failure_event.payment_rail === 'UPI_AUTOPAY' || caseItem.failure_event.payment_rail === 'ENACH'

  // Extract LLM dunning messages from audit trail if available
  const planEntry = caseItem.audit_trail.find((e) => e.event_name === 'agent.plan_formulated')
  const metadata = planEntry?.model_metadata

  const defaultMsgEn = discountPaise > 0
    ? `Hi ${caseItem.failure_event.customer_id}, your recent payment of ${formatINR(amountPaise)} was interrupted. Complete your payment now with an instant ${formatINR(discountPaise)} discount!`
    : `Hi ${caseItem.failure_event.customer_id}, we noticed your payment of ${formatINR(amountPaise)} was delayed. Please click below to securely complete your payment.`

  const defaultMsgHi = discountPaise > 0
    ? `Namaste ${caseItem.failure_event.customer_id}, aapka ${formatINR(amountPaise)} ka payment complete nahi ho paya. Abhi pay karein aur payein instant ${formatINR(discountPaise)} discount!`
    : `Namaste ${caseItem.failure_event.customer_id}, aapka ${formatINR(amountPaise)} ka payment process nahi ho paya. Kripya neeche diye link se turant payment complete karein.`

  const messageText = lang === 'en' ? defaultMsgEn : defaultMsgHi

  return (
    <div className="rounded-panel border border-border bg-surface overflow-hidden shadow-sm">
      {/* WhatsApp Chat Header */}
      <div className="flex items-center justify-between bg-[#075E54] px-4 py-3 text-white">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-[#075E54] font-bold text-xs font-mono">
            RZ
          </div>
          <div>
            <div className="flex items-center gap-1">
              <span className="text-xs font-semibold">Razorpay Verified Merchant</span>
              <ShieldCheck className="h-3.5 w-3.5 text-[#25D366]" />
            </div>
            <span className="text-[10px] text-white/80 block font-mono">
              +91 98765 00000 · Official Recovery Bot
            </span>
          </div>
        </div>

        {/* Language Switcher */}
        <div className="flex items-center gap-1 rounded-control bg-black/20 p-0.5 text-[10px] font-mono">
          <button
            type="button"
            onClick={() => {
              setLang('en')
            }}
            className={`px-1.5 py-0.5 rounded cursor-pointer ${
              lang === 'en' ? 'bg-white text-[#075E54] font-bold' : 'text-white/80'
            }`}
          >
            EN
          </button>
          <button
            type="button"
            onClick={() => {
              setLang('hi')
            }}
            className={`px-1.5 py-0.5 rounded cursor-pointer ${
              lang === 'hi' ? 'bg-white text-[#075E54] font-bold' : 'text-white/80'
            }`}
          >
            Hinglish
          </button>
        </div>
      </div>

      {/* RBI Compliance Banner */}
      {isMandate && (
        <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-1.5 text-[10px] font-mono text-amber-700 flex items-center justify-between">
          <span>RBI Pre-Debit Mandate Notice (T-24h) Compliant</span>
          <span className="font-semibold text-recovered">Verified ✓</span>
        </div>
      )}

      {/* Chat Bubble Area */}
      <div className="bg-[#EFEAE2] p-4 space-y-3 min-h-40">
        <div className="max-w-[85%] rounded-2xl rounded-tl-xs bg-white p-3 shadow-xs border border-black/5 text-ink space-y-2.5">
          <p className="text-xs leading-relaxed">{messageText}</p>

          {/* Payment Link Card Inside WhatsApp */}
          <div className="rounded-control border border-border bg-surface-sunken p-2.5 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-mono">
              <span className="text-ink-muted">Payable Amount</span>
              <span className="font-bold text-ink">{formatINR(payablePaise)}</span>
            </div>
            {discountPaise > 0 && (
              <div className="flex items-center justify-between text-[10px] font-mono text-recovered">
                <span>Incentive Applied</span>
                <span>-{formatINR(discountPaise)}</span>
              </div>
            )}
            <a
              href="https://rzp.io/rzp/recovery-link"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-1.5 w-full rounded-control bg-[#25D366] hover:bg-[#20bd5a] text-white py-1.5 text-xs font-semibold transition-colors mt-1"
            >
              <span>Pay with UPI / Card</span>
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>

          {/* Delivery & Read Timestamp */}
          <div className="flex items-center justify-end gap-1 text-[9px] font-mono text-ink-subtle">
            <span>{new Date(caseItem.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            <CheckCheck className="h-3 w-3 text-[#34B7F1]" />
          </div>
        </div>

        {metadata && (
          <div className="text-[10px] font-mono text-ink-muted text-right">
            Generated via {metadata.model} · {metadata.output_tokens?.toString()} tokens
          </div>
        )}
      </div>
    </div>
  )
}
