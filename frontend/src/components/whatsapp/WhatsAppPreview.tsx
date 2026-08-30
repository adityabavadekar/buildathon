'use client'

import React, { useState } from 'react'
import { CheckCheck, ExternalLink, ShieldCheck } from 'lucide-react'
import type { RecoveryCase } from '@/lib/api'
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

  const isMandate =
    caseItem.failure_event.payment_rail === 'UPI_AUTOPAY' ||
    caseItem.failure_event.payment_rail === 'ENACH'

  const defaultMsgEn =
    discountPaise > 0
      ? `Hi ${caseItem.failure_event.customer_id}, your recent payment of ${formatINR(amountPaise)} was interrupted. Complete your payment now with an instant ${formatINR(discountPaise)} discount!`
      : `Hi ${caseItem.failure_event.customer_id}, we noticed your payment of ${formatINR(amountPaise)} was delayed. Please click below to securely complete your payment.`

  const defaultMsgHi =
    discountPaise > 0
      ? `Namaste ${caseItem.failure_event.customer_id}, aapka ${formatINR(amountPaise)} ka payment complete nahi ho paya. Abhi pay karein aur payein instant ${formatINR(discountPaise)} discount!`
      : `Namaste ${caseItem.failure_event.customer_id}, aapka ${formatINR(amountPaise)} ka payment process nahi ho paya. Kripya neeche diye link se turant payment complete karein.`

  const messageText = lang === 'en' ? defaultMsgEn : defaultMsgHi

  return (
    <div className="rounded-panel border border-border bg-surface overflow-hidden shadow-sm">
      {/* WhatsApp Chat Header */}
      <div className="flex items-center justify-between bg-[#075E54] px-4 py-3 text-white">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-[#075E54] font-bold text-xs font-mono shadow-xs">
            <RazorpaySymbol className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold">Razorpay Verified Merchant</span>
              <ShieldCheck className="h-3.5 w-3.5 text-[#25D366]" />
              <WhatsAppIcon className="h-3.5 w-3.5" />
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
            HI
          </button>
        </div>
      </div>

      {/* WhatsApp Chat Background Body */}
      <div className="bg-[#EFEAE2] dark:bg-[#0B141A] p-4 min-h-[220px] flex flex-col justify-end space-y-3">
        {/* Outbound Dunning Bubble */}
        <div className="max-w-[85%] self-start rounded-panel rounded-tl-xs bg-white dark:bg-[#1F2C34] p-3 shadow-xs border border-black/5 dark:border-white/5 space-y-2">
          <p className="text-xs text-[#111B21] dark:text-[#E9EDEF] leading-relaxed">
            {messageText}
          </p>

          {/* Interactive Single-Use Payment Link Card */}
          <div className="p-2.5 rounded-control bg-[#F0F2F5] dark:bg-[#111B21] border border-black/10 dark:border-white/10 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-mono font-bold text-ink">
              <span>Razorpay Secure Link</span>
              <span className="text-recovered">{formatINR(payablePaise)}</span>
            </div>
            {discountPaise > 0 && (
              <div className="flex items-center justify-between text-[10px] font-mono text-ink-muted">
                <span>Original: {formatINR(amountPaise)}</span>
                <span className="text-accent font-semibold">Saved {formatINR(discountPaise)}</span>
              </div>
            )}
            <div className="flex items-center gap-1 text-[10px] text-accent font-mono pt-1">
              <ExternalLink className="h-3 w-3" />
              <span>https://rzp.io/i/{caseItem.case_id.slice(0, 8)}</span>
            </div>
          </div>

          <div className="flex items-center justify-end gap-1 text-[9px] font-mono text-ink-muted">
            <span>{new Date(caseItem.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            <CheckCheck className="h-3.5 w-3.5 text-[#53BDEB]" />
          </div>
        </div>

        {/* Informational Mandate Guidance */}
        {isMandate && (
          <div className="text-center">
            <span className="inline-block rounded-control bg-white/80 dark:bg-[#1F2C34]/80 px-2.5 py-1 text-[10px] font-mono text-ink-muted shadow-2xs">
              Automatic retry scheduled per RBI mandate circular
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
