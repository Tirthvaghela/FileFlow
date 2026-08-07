import { AlertTriangle, HelpCircle } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./dialog.jsx";
import { Button } from "./button.jsx";

export default function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "default",
  onConfirm,
}) {
  const isDestructive = variant === "destructive";
  const Icon = isDestructive ? AlertTriangle : HelpCircle;
  const iconColor = isDestructive ? "var(--status-critical)" : "var(--brand)";

  function handleConfirm() {
    onOpenChange(false);
    onConfirm();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} disablePointerDismissal>
      <DialogContent showCloseButton={false} className="rounded-2xl bg-[var(--surface-1)] p-6 sm:max-w-[420px]">
        <span
          className="flex h-11 w-11 items-center justify-center rounded-full"
          style={{ color: iconColor, background: `color-mix(in srgb, ${iconColor} 14%, transparent)` }}
        >
          <Icon className="h-5 w-5" />
        </span>
        <DialogTitle className="mt-3 font-display text-base font-semibold text-[var(--text-primary)]">
          {title}
        </DialogTitle>
        <DialogDescription className="text-sm leading-relaxed text-[var(--text-secondary)]">
          {description}
        </DialogDescription>
        <div className="mt-2 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {cancelLabel}
          </Button>
          <Button variant={isDestructive ? "destructive" : "default"} onClick={handleConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
