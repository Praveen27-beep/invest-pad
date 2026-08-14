# Key and Pepper Rotation

> Design note, written before any real client data exists. Rotation is cheap to design
> now and expensive to retrofit, because both procedures need schema support that is
> painful to add once `investor_secret` has rows in it.

Two independent secrets, from `db/crypto.py`:

| Secret | Env var | Protects | Rotation difficulty |
|---|---|---|---|
| Encryption key | `PORTFOLIO_ENCRYPTION_KEY` | `pan_enc`, `demat_enc` | Routine |
| PAN pepper | `PORTFOLIO_PAN_PEPPER` | `pan_hash` | **Hard, and conditionally impossible** |

They are separate so that leaking one does not defeat the other. That separation is also
why they rotate differently and must never rotate together.

---

## 1. Encryption key rotation — routine

Fernet ciphertext is opaque: nothing in a stored value says which key produced it. The
library's answer is `MultiFernet`, which decrypts with any key in a list and encrypts with
the first.

**Procedure:**

1. Generate a new key. Set the secret to `new,old` (ordered, new first).
   `db/crypto.py` currently reads a single key — it needs to accept a comma-separated list
   and build a `MultiFernet`. That is the only code change rotation requires.
2. Deploy. Every read now succeeds against either key; every new write uses the new one.
   **No downtime, and no window where data is unreadable.**
3. Re-encrypt: for each `investor_secret` row, decrypt and write back. The write uses the
   new key because it is first.
4. Once every row is migrated, set the secret to `new` alone and deploy again. The old key
   is now retired and can be destroyed.

**Cost:** one row per investor. At the scale this system is built for — ten clients, a few
dozen — it is instantaneous. Even at 100,000 investors it is a single pass of small
updates.

**Not blocked by the append-only trigger.** That trigger is on `transaction` only;
`investor_secret` is freely updatable, which is correct — a stored identifier is a current
fact, not a historical event.

**Audit:** re-encryption reads every PAN. Do **not** emit one `SECRET_READ` per row: a
routine maintenance task would flood the access log and bury the reads that matter. Emit
one `KEY_ROTATION` row carrying counts and both key identifiers. The log should record
that a rotation happened, not manufacture thousands of access events nobody will read.

---

## 2. Pepper rotation — hard, and conditionally impossible

`pan_hash = HMAC-SHA256(pepper, normalised_pan)`. A hash cannot be re-peppered from
itself; the only way to produce the new hash is to start from the PAN again.

**The PAN is recoverable only from `pan_enc`.** So:

> **INVARIANT: never store a `pan_hash` without also storing `pan_enc`.**
>
> A hash written without its ciphertext is permanently orphaned. It can never be
> re-peppered, which means that investor can never again be found by PAN after a rotation,
> and the only remedy is to ask a human being for their PAN a second time.

Nothing enforces this today. `investor_secret` allows `pan_hash` to be set with `pan_enc`
left NULL, and it should not — see §4.

**Procedure, given the invariant holds:**

1. For each row: decrypt `pan_enc`, compute `HMAC(new_pepper, pan)`, write to
   `pan_hash_next`, record `pepper_version`.
2. During the window, **look up by either hash**: `WHERE pan_hash = %s OR pan_hash_next = %s`.
   Both peppers must be readable, so the env carries both, ordered.
3. When every row is migrated, promote `pan_hash_next` into `pan_hash`, drop the old
   pepper, and clear the column.

**What breaks if you skip the dual-hash window:** every lookup by PAN fails for exactly as
long as the migration runs. What depends on those lookups is not obvious and is worth
listing before you find out the hard way — matching an inbound CAS to an investor,
deriving contract-note PDF passwords (Zerodha and Groww use uppercase PAN, Upstox
lowercase), and de-duplicating an investor who is onboarded twice.

**Ordering rule: never rotate both secrets at once.** Pepper rotation *depends on*
decryption working. If the encryption key is mid-rotation and a row happens to be
unreadable, that row's hash cannot be recomputed and you are left with a partial migration
you cannot resume. Rotate the key, confirm it is complete, then rotate the pepper.

---

## 3. When to rotate

| Trigger | Key | Pepper |
|---|---|---|
| Suspected compromise of that secret | immediately | immediately |
| Staff departure with production access | yes | yes |
| Routine hygiene | annually | rarely — the cost is real and the benefit small |
| The other secret was compromised | no | no — they are independent by design |

A pepper is not a password and does not need routine rotation. Rotate it because something
happened, not because a calendar said so.

---

## 4. The one change that must land before real data

Both procedures need to know which rows have been migrated. Without that, a rotation
interrupted half way cannot be resumed: there is no way to tell a re-encrypted row from an
untouched one, and re-running blindly is safe for the key but not for the pepper.

Migration `003_key_versioning.sql`, to be applied **before any real client data exists** —
it is three columns and a constraint now, and a data migration later:

```sql
ALTER TABLE investor_secret
    ADD COLUMN key_version    smallint NOT NULL DEFAULT 1,
    ADD COLUMN pepper_version smallint NOT NULL DEFAULT 1,
    ADD COLUMN pan_hash_next  text;

-- Enforce the invariant from section 2: a hash without its ciphertext can never be
-- re-peppered, so refuse to create one.
ALTER TABLE investor_secret
    ADD CONSTRAINT pan_hash_requires_ciphertext
    CHECK (pan_hash IS NULL OR pan_enc IS NOT NULL);

CREATE INDEX investor_secret_pan_hash_idx      ON investor_secret (pan_hash);
CREATE INDEX investor_secret_pan_hash_next_idx ON investor_secret (pan_hash_next)
    WHERE pan_hash_next IS NOT NULL;
```

That constraint is the important line. Everything else in this document is a procedure
someone can follow carefully; the constraint is the part that stops a mistake being
unrecoverable.

---

## 5. What is deliberately not built

No rotation tooling. Writing it now would mean maintaining a script against a schema and a
scale that do not exist yet, and the procedure is short enough to run by hand for the first
several years. What matters is that the schema permits it and the invariant is enforced —
both of which are §4.

Key storage itself is out of scope here: today both secrets come from the environment. A
managed KMS is the obvious next step, and neither procedure above changes if one is
adopted, because both are expressed in terms of "the secret" rather than where it is kept.
