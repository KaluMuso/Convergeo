/* eslint-disable @vergeo/no-hardcoded-strings -- dev-only UI preview; gated off in production */
"use client";

import { BottomSheet } from "@vergeo/ui/src/bottom-sheet";
import { Button } from "@vergeo/ui/src/button";
import { ConfirmDialog } from "@vergeo/ui/src/confirm-dialog";
import { Modal } from "@vergeo/ui/src/modal";
import { ToastProvider, useToast } from "@vergeo/ui/src/toast";
import { useState } from "react";

function SectionBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <h3 className="font-display text-lg text-display-ink">{title}</h3>
      {children}
    </div>
  );
}

function OverlayTriggers() {
  const { toast } = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  return (
    <>
      <SectionBlock title="Modal">
        <Button loadingLabel="Loading" onClick={() => setModalOpen(true)}>
          Open modal
        </Button>
        <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Preview modal">
          <p className="text-text-2">Modal body with focus trap and ESC dismiss.</p>
        </Modal>
      </SectionBlock>

      <SectionBlock title="Bottom sheet">
        <Button loadingLabel="Loading" variant="secondary" onClick={() => setSheetOpen(true)}>
          Open bottom sheet
        </Button>
        <BottomSheet open={sheetOpen} onClose={() => setSheetOpen(false)} title="Filter options">
          <p className="text-text-2">Drag or tap scrim to dismiss on mobile.</p>
        </BottomSheet>
      </SectionBlock>

      <SectionBlock title="Confirm dialog">
        <Button loadingLabel="Loading" variant="destructive" onClick={() => setConfirmOpen(true)}>
          Open confirm
        </Button>
        <ConfirmDialog
          open={confirmOpen}
          onClose={() => setConfirmOpen(false)}
          title="Remove item?"
          body="This action cannot be undone in the preview."
          confirmLabel="Remove"
          cancelLabel="Cancel"
          destructive
          onConfirm={() => undefined}
        />
      </SectionBlock>

      <SectionBlock title="Toasts">
        <div className="flex flex-wrap gap-2">
          <Button
            loadingLabel="Loading"
            variant="secondary"
            onClick={() => toast("Saved successfully", { type: "success" })}
          >
            Success toast
          </Button>
          <Button
            loadingLabel="Loading"
            variant="secondary"
            onClick={() => toast("Something went wrong", { type: "error" })}
          >
            Error toast
          </Button>
          <Button
            loadingLabel="Loading"
            variant="secondary"
            onClick={() => toast("Added to cart", { type: "cart" })}
          >
            Cart toast
          </Button>
          <Button
            loadingLabel="Loading"
            variant="ghost"
            onClick={() => toast("Heads up — check your email", { type: "info" })}
          >
            Info toast
          </Button>
        </div>
      </SectionBlock>
    </>
  );
}

export function OverlaysSection() {
  return (
    <section id="overlays" className="scroll-mt-4 flex flex-col gap-6">
      <h2 className="font-display text-2xl text-display-ink">Overlays</h2>
      <ToastProvider>
        <OverlayTriggers />
      </ToastProvider>
    </section>
  );
}
