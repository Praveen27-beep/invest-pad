"use client";

/**
 * `/research/notes/{id}` -- one exact, immutable note (FE 15). The id is a SAVED note's id;
 * an unsaved note has no URL. Validated with the shared resolver before any request.
 */

import { notFound, useParams } from "next/navigation";
import { researchDocument } from "@trackr/portfolio";
import { NoteDocument } from "../../../components/research/NoteDocument";

export default function NotePage() {
  const params = useParams<{ noteId: string }>();
  const doc = researchDocument(`/research/notes/${params.noteId}`);
  if (!doc || doc.kind !== "note") notFound();
  return <NoteDocument key={doc.ref} noteId={doc.ref} />;
}
