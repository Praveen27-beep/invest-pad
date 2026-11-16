-- 004: uploaded documents and the passages cut from them.
--
-- `document` is the record of an upload; the original file is kept on disk under its id.
-- `chunk` is derived: the extracted text, cut into passages that can be searched and
-- cited. Deleting a document deletes its chunks (and the application removes the file).

CREATE TABLE document (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    subject_id  uuid NOT NULL,
    title       text NOT NULL CHECK (length(trim(title)) > 0),
    filename    text NOT NULL,
    format      text NOT NULL CHECK (format IN ('pdf', 'xlsx', 'docx')),
    doc_type    text NOT NULL DEFAULT 'other',   -- annual report, concall, presentation… (free text from the pack)
    period      text NOT NULL DEFAULT '',        -- e.g. FY25, Q2 FY26
    doc_date    date,
    sha256      text NOT NULL,
    size_bytes  bigint NOT NULL,
    status      text NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'ready', 'no_text', 'failed')),
    status_note text NOT NULL DEFAULT '',
    pages       integer NOT NULL DEFAULT 0,      -- pages, sheets or sections, depending on the format
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, id),
    UNIQUE (owner_id, subject_id, sha256),       -- the same file twice under one company is a mistake
    FOREIGN KEY (owner_id, subject_id) REFERENCES subject (owner_id, id) ON DELETE CASCADE
);
CREATE INDEX document_subject ON document (owner_id, subject_id, created_at DESC);
SELECT enable_owner_isolation('document');

CREATE TABLE chunk (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    document_id uuid NOT NULL,
    ordinal     integer NOT NULL,                -- position within the document
    page        integer NOT NULL,                -- 1-based page, sheet or section number
    label       text NOT NULL DEFAULT '',        -- "p. 12", or a sheet name
    body        text NOT NULL,
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', body)) STORED,
    UNIQUE (owner_id, id),
    UNIQUE (document_id, ordinal),
    FOREIGN KEY (owner_id, document_id) REFERENCES document (owner_id, id) ON DELETE CASCADE
);
CREATE INDEX chunk_tsv ON chunk USING gin (tsv);
SELECT enable_owner_isolation('chunk');
