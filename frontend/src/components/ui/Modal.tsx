import { useEffect, useRef, type ReactNode } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
}

/**
 * A native <dialog>: the browser handles focus, Escape and the backdrop. `open` controls it; closing by
 * Escape or the close button calls `onClose`.
 */
export function Modal({ open, onClose, title, subtitle, children }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = `modal-${title.replace(/\W+/g, "-").toLowerCase()}`;

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    else if (!open && element.open) element.close();
  }, [open]);

  return (
    <dialog ref={dialog} className="modal" aria-labelledby={titleId} onClose={onClose}>
      <div className="modal-head">
        <div>
          <h2 id={titleId}>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <button type="button" className="icon-button" aria-label="Close" onClick={onClose}>
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" /></svg>
        </button>
      </div>
      {open && children}
    </dialog>
  );
}
