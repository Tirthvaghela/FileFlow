import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { XIcon } from "lucide-react"

function Dialog({
  ...props
}) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />;
}

function DialogTrigger({
  ...props
}) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />;
}

function DialogPortal({
  ...props
}) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />;
}

function DialogClose({
  ...props
}) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />;
}

function DialogOverlay({
  className,
  ...props
}) {
  return (
    <DialogPrimitive.Backdrop
      data-slot="dialog-overlay"
      className={cn(
        "fixed inset-0 isolate z-50 duration-100 data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0",
        className
      )}
      style={{ background: "rgba(20,16,10,.55)" }}
      {...props} />
  );
}

// The small folder tab sticking out above a dialog panel's top-left
// corner -- same shape the prototype uses on every dialog, labelled per
// dialog (e.g. "PREVIEW", "SEARCH") with a red dot.
function DialogTab({ children }) {
  if (!children) return null;
  return (
    <div
      className="absolute -top-[22px] left-5 flex h-[22px] items-center gap-1.5 rounded-t-[4px] bg-[var(--surface-1)] px-2.5 text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-secondary)]"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-[var(--stamp)]" />
      {children}
    </div>
  );
}

function DialogContent({
  className,
  children,
  showCloseButton = true,
  tab,
  ...props
}) {
  return (
    <DialogPortal>
      <DialogOverlay />
      <div className="fixed top-1/2 left-1/2 z-50 w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2">
        <DialogTab>{tab}</DialogTab>
        <DialogPrimitive.Popup
          data-slot="dialog-content"
          className={cn(
            "relative grid w-full gap-4 bg-[var(--surface-1)] p-4 text-sm text-popover-foreground shadow-[0_24px_48px_-20px_var(--shade)] duration-100 outline-none sm:max-w-sm data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95",
            className
          )}
          style={{ borderRadius: "0 6px 6px 6px" }}
          {...props}>
          {children}
          {showCloseButton && (
            <DialogPrimitive.Close
              data-slot="dialog-close"
              render={
                <Button variant="ghost" className="absolute top-2 right-2" size="icon-sm" />
              }>
              <XIcon />
              <span className="sr-only">Close</span>
            </DialogPrimitive.Close>
          )}
        </DialogPrimitive.Popup>
      </div>
    </DialogPortal>
  );
}

function DialogHeader({
  className,
  ...props
}) {
  return (
    <div
      data-slot="dialog-header"
      className={cn("flex flex-col gap-1.5 border-b-2 border-[var(--text-primary)] pb-3", className)}
      {...props} />
  );
}

function DialogFooter({
  className,
  showCloseButton = false,
  children,
  ...props
}) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn(
        "-mx-4 -mb-4 flex flex-col-reverse gap-2 rounded-b-[6px] border-t border-[var(--border)] bg-[var(--surface-sunk)] p-4 sm:flex-row sm:items-center sm:justify-end",
        className
      )}
      {...props}>
      {children}
      {showCloseButton && (
        <DialogPrimitive.Close render={<Button variant="outline" />}>
          Close
        </DialogPrimitive.Close>
      )}
    </div>
  );
}

function DialogTitle({
  className,
  ...props
}) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn("font-heading text-xl font-extrabold leading-tight tracking-[-0.02em] text-[var(--text-primary)]", className)}
      {...props} />
  );
}

function DialogDescription({
  className,
  ...props
}) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn(
        "text-sm text-muted-foreground *:[a]:underline *:[a]:underline-offset-3 *:[a]:hover:text-foreground",
        className
      )}
      {...props} />
  );
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
}
