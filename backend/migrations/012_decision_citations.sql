-- An answer may cite one of the user's recorded decisions (the decisive reason in their
-- own words), so "why did I buy this?" can be answered in Ask and the side panel with the
-- decision itself as the source. Decisions are append-only; deleting the company deletes
-- them and, by cascade, any claim that cited them.
ALTER TABLE citation ADD COLUMN decision_id uuid;
ALTER TABLE citation DROP CONSTRAINT citation_check;
ALTER TABLE citation ADD CONSTRAINT citation_one_source
    CHECK (num_nonnulls(chunk_id, note_id, decision_id) = 1);
ALTER TABLE decision ADD CONSTRAINT decision_owner_id_key UNIQUE (owner_id, id);
ALTER TABLE citation ADD FOREIGN KEY (owner_id, decision_id) REFERENCES decision (owner_id, id) ON DELETE CASCADE;
