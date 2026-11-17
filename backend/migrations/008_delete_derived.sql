-- Deleting a source deletes what was derived from it (non-negotiable).
--
-- 1. A claim is the model's sentence built from every passage it cites. If any one of
--    those passages is deleted, the sentence was partly derived from deleted text, so the
--    whole claim goes (its other citations go with it by cascade). Before this, a claim
--    survived as long as one citation remained.
CREATE OR REPLACE FUNCTION drop_uncited_claim() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM claim WHERE id = OLD.claim_id;
    RETURN NULL;
END $$;

-- 2. Evidence the user wrote stays (it is their own words) and is marked "source deleted".
--    Evidence that is an accepted AI claim is model text derived from the source, so its
--    wording is removed; the row stays so the assumption's history still shows that
--    evidence existed and was withdrawn with its source.
CREATE OR REPLACE FUNCTION mark_evidence_source_deleted() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE evidence
       SET source_deleted = true,
           body = CASE WHEN kind = 'ai' THEN '(AI statement removed with its source)' ELSE body END
     WHERE ((TG_TABLE_NAME = 'chunk' AND chunk_id = OLD.id)
        OR (TG_TABLE_NAME = 'note' AND note_id = OLD.id))
       -- When a whole company is deleted, its evidence is being deleted in the same cascade;
       -- touching it would fail the foreign-key re-check, so skip it (the company row is
       -- already gone when this runs).
       AND EXISTS (SELECT 1 FROM assumption a JOIN position p ON p.id = a.position_id
                     JOIN subject s ON s.id = p.subject_id WHERE a.id = evidence.assumption_id);
    RETURN OLD;
END $$;

CREATE TRIGGER note_deleted BEFORE DELETE ON note
    FOR EACH ROW EXECUTE FUNCTION mark_evidence_source_deleted();
