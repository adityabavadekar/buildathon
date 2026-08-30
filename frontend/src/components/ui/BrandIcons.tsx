'use client'

import React from 'react'

interface BrandIconProps {
  className?: string
  size?: number
}

/** Official Razorpay Blue Slash Logo */
export function RazorpayIcon({ className = 'h-5 w-5', size }: BrandIconProps) {
  return (
    <svg
      viewBox="0 0 512 512"
      fill="currentColor"
      className={className}
      width={size}
      height={size}
      aria-label="Razorpay"
    >
      <path
        fill="#0C2340"
        d="M0 0h512v512H0z"
        className="dark:fill-slate-900"
      />
      <path
        fill="#3395FF"
        d="M224.2 82.3h165.5l-82.6 150.2h-74.4l58.1-105.7H210.3l-81.5 252.9h-47.5L154.5 82.3h69.7z"
      />
      <path
        fill="#02042B"
        d="M342.3 277.1l-43.2 78.5H231l43.2-78.5h68.1z"
        className="dark:fill-blue-400"
      />
      <path
        fill="#528FF0"
        d="M285.5 380.3l-43.2 78.5H174.2l43.2-78.5h68.1z"
      />
    </svg>
  )
}

/** Razorpay Inline Symbol (Minimalist Slash) */
export function RazorpaySymbol({ className = 'h-4 w-4' }: BrandIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Razorpay"
    >
      <path
        d="M10.8 3h8.2l-4.1 7.5h-3.7l2.9-5.3H10.1L6 21H3.6L7.3 3h3.5z"
        fill="#3395FF"
      />
      <path
        d="M16.7 12.7l-2.1 3.9h-3.4l2.1-3.9h3.4z"
        fill="#02042B"
        className="dark:fill-blue-300"
      />
      <path
        d="M13.9 17.8l-2.1 3.9H8.4l2.1-3.9h3.4z"
        fill="#528FF0"
      />
    </svg>
  )
}

/** Official NPCI UPI Brand Icon */
export function UpiIcon({ className = 'h-4 w-4' }: BrandIconProps) {
  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      aria-label="UPI"
    >
      <path
        d="M27.5 7L13 32.5h9.8L18.3 41l16.7-25.5H25.2L27.5 7z"
        fill="#097939"
      />
      <path
        d="M34.5 15.5L20 41h9.8l-4.5 8.5L42 24H32.2l2.3-8.5z"
        fill="#ED752E"
      />
    </svg>
  )
}

/** Official WhatsApp Green Brand Icon */
export function WhatsAppIcon({ className = 'h-4 w-4' }: BrandIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      aria-label="WhatsApp"
    >
      <path
        fill="#25D366"
        d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91C2.13 13.66 2.59 15.36 3.45 16.86L2.05 22L7.3 20.62C8.75 21.41 10.38 21.83 12.04 21.83C17.5 21.83 21.95 17.38 21.95 11.92C21.95 9.27 20.92 6.78 19.05 4.91C17.18 3.04 14.69 2 12.04 2Z"
      />
      <path
        fill="#FFFFFF"
        d="M17.51 14.39C17.21 14.24 15.74 13.51 15.47 13.41C15.19 13.31 15 13.26 14.8 13.56C14.6 13.86 14.04 14.51 13.86 14.71C13.69 14.91 13.51 14.93 13.22 14.79C12.92 14.64 11.98 14.33 10.86 13.33C9.99 12.56 9.4 11.6 9.23 11.3C9.05 11.01 9.21 10.85 9.36 10.7C9.5 10.56 9.66 10.34 9.81 10.17C9.96 10 10.01 9.88 10.11 9.68C10.21 9.48 10.16 9.31 10.09 9.16C10.01 9.01 9.46 7.66 9.23 7.1C9.01 6.56 8.78 6.63 8.61 6.62C8.45 6.61 8.28 6.61 8.1 6.61C7.93 6.61 7.65 6.67 7.42 6.92C7.19 7.17 6.55 7.77 6.55 8.99C6.55 10.21 7.44 11.39 7.56 11.56C7.69 11.73 9.31 14.22 11.79 15.29C12.38 15.54 12.84 15.7 13.2 15.81C13.79 16 14.33 15.97 14.76 15.91C15.24 15.84 16.23 15.31 16.44 14.73C16.64 14.14 16.64 13.64 16.58 13.54C16.52 13.44 16.35 13.38 16.05 13.23L17.51 14.39Z"
      />
    </svg>
  )
}

/** RuPay Card / Payment Rail Icon */
export function RuPayIcon({ className = 'h-4 w-4' }: BrandIconProps) {
  return (
    <svg
      viewBox="0 0 36 24"
      fill="none"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      aria-label="RuPay"
    >
      <rect width="36" height="24" rx="3" fill="#092873" />
      <path d="M7 6h7.5c2.5 0 4 1.2 4 3.2s-1.5 3.2-4 3.2H10v5.6H7V6zm3 4.4h4.2c1 0 1.6-.4 1.6-1.2s-.6-1.2-1.6-1.2H10v2.4z" fill="#FFF" />
      <path d="M19 12.4l4.5 5.6h3.8l-4.8-6 4.3-6h-3.7L19 12.4z" fill="#00A651" />
      <path d="M25 6h4l3.5 12h-3.8L27 12h-2V6z" fill="#ED1C24" />
    </svg>
  )
}
