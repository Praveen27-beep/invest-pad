"use client";

import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";
import { BlockNoteView } from "@blocknote/mantine";
import { useCreateBlockNote } from "@blocknote/react";
import { forwardRef, useImperativeHandle } from "react";
import type { Block } from "@/lib/api";

export type EditorHandle = { currentBlockId: () => string | null };

/** The block editor. It hands the whole document back on every change; saving is the page's job. */
const Editor = forwardRef<EditorHandle, { initial: Block[]; onChange: (blocks: Block[]) => void }>(
  function Editor({ initial, onChange }, ref) {
    // BlockNote rejects an empty array, so a new note starts from its default empty block.
    const editor = useCreateBlockNote({ initialContent: initial.length ? (initial as never) : undefined });
    useImperativeHandle(ref, () => ({
      currentBlockId: () => {
        try { return editor.getTextCursorPosition().block.id; } catch { return null; }
      },
    }));
    return (
      <BlockNoteView editor={editor} theme="light" onChange={() => onChange(editor.document as unknown as Block[])} />
    );
  },
);
export default Editor;
