import * as React from "react"
import { Eye, EyeOff } from "lucide-react"

import { Input } from "./input.jsx"
import { cn } from "@/lib/utils"

function PasswordInput({ className, showText = false, ...props }) {
  const [visible, setVisible] = React.useState(false)

  return (
    <div className="relative">
      <Input
        type={visible ? "text" : "password"}
        className={cn("pr-9", className)}
        {...props}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        tabIndex={-1}
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        className={`absolute inset-y-0 right-0 flex items-center px-2.5 text-muted-foreground transition-colors hover:text-foreground ${showText ? "auth-password-toggle" : ""}`}
      >
        {showText ? (
          visible ? "Hide" : "Show"
        ) : visible ? (
          <EyeOff className="h-4 w-4" />
        ) : (
          <Eye className="h-4 w-4" />
        )}
      </button>
    </div>
  );
}

export { PasswordInput }
