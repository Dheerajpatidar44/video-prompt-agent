import React from "react";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "optional" | "required" | "success" | "error";
}

const variantStyles: Record<string, string> = {
  default: "bg-white/8 text-gray-300 border border-white/10",
  optional: "bg-white/5 text-gray-400 border border-white/8",
  required: "bg-blue-500/15 text-blue-400 border border-blue-500/25",
  success: "bg-green-500/15 text-green-400 border border-green-500/25",
  error:   "bg-red-500/15 text-red-400 border border-red-500/25",
};

export function Badge({ children, variant = "default" }: BadgeProps) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 10px",
        borderRadius: "99px",
        fontSize: "11px",
        fontWeight: 500,
        letterSpacing: "0.02em",
      }}
      className={variantStyles[variant]}
    >
      {children}
    </span>
  );
}
