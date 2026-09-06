import React from 'react'

const MONEY_PATTERN =
  /(\d+\s*paise|₹\s?[\d,]+(?:\.\d+)?|INR\s?[\d,]+(?:\.\d+)?)/g
const PAISE_PATTERN = /^(\d+)\s*paise$/
const MONEY_TOKEN_PATTERN =
  /^(\d+\s*paise|₹\s?[\d,]+(?:\.\d+)?|INR\s?[\d,]+(?:\.\d+)?)$/

/** Splits free text on "<int> paise" or an already-formatted INR amount and
 * wraps each money mention in <strong>, so a raw or historical audit string
 * still reads with the amount visually emphasized. */
export function HighlightMoney({ text }: { text: string }) {
  const parts = text.split(MONEY_PATTERN)

  return (
    <>
      {parts.map((part, index) => {
        const paiseMatch = PAISE_PATTERN.exec(part)
        if (paiseMatch?.[1]) {
          const rupees = Number(paiseMatch[1]) / 100
          const formatted = new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            maximumFractionDigits: 2,
          }).format(rupees)
          return <strong key={index}>{formatted}</strong>
        }
        if (MONEY_TOKEN_PATTERN.test(part)) {
          return <strong key={index}>{part}</strong>
        }
        return <React.Fragment key={index}>{part}</React.Fragment>
      })}
    </>
  )
}
