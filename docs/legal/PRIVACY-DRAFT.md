# Invest-pad privacy policy — DRAFT FOR LAWYER REVIEW

> **Not for publication.** Written from what the software actually does on 17 Nov 2026,
> so a lawyer can check it against the law that applies (in India, likely the Digital
> Personal Data Protection Act, 2023 and its rules). Items in [brackets] need decisions
> or facts only the operator has. Nothing here has been reviewed by a lawyer.

**Operator:** [legal name, address, contact email]. Invest-pad is a research tool. It is
separate from any investment advisory service and does not give investment advice.

## What we store

| Data | Why | Where |
|---|---|---|
| Email address, password (stored only as an argon2 hash) | To run your account | Our database |
| Session tokens and extension tokens (stored only as SHA-256 hashes) | To keep you signed in; to let the Chrome side panel and MCP clients act for you | Our database |
| What you put in: notes, documents and the text extracted from them, theses, assumptions, evidence, decisions, checklists, questions and answers, holdings you import, limits, reviews, captured web selections | To provide the service | Our database and file storage |
| Model API keys you add | To call the model you chose | Encrypted (Fernet) with a key held on the server; never logged, never shown again |
| Usage records (tokens and estimated cost per model call) | Cost limits and your usage view | Our database |
| A one-line record per request: time, method, path, status, duration, user id | Operating and debugging the service | Server logs. Request bodies, query strings, headers and cookies are not logged |

We do not use advertising or analytics trackers. [Confirm for the deployed site.]

## Who else receives your data

- **The model provider you choose.** When you ask a question, run a contradiction scan, or
  check a decision against “How I invest”, the relevant passages from your documents and
  notes, your question, and your “How I invest” text are sent to the model endpoint you
  configured (or [the included model provider], if you use included credit). Their
  handling of that data is governed by their terms. Invest-pad does not use DeepSeek's own
  hosted API.
- **Hosting providers:** [name the hosting, database and storage providers and regions].
- No one else, unless required by law.

## Your controls

- **Export:** Settings → Download my data gives a ZIP of everything you own, including
  history, as readable files and JSON.
- **Delete a document or note:** removes it, its extracted text, search index, and any
  AI-generated statements derived from it.
- **Delete your account:** Settings → Delete account removes every record you own and
  every uploaded file immediately. [State backup retention: copies may remain in backups
  for N days.]
- **Correction:** you can edit your content; history is kept as versions you can see.

## Retention

Data is kept until you delete it or your account. [Backup retention period.] [Log
retention period.]

## Security

Row-level security in the database separates users' data; every table you own is
covered and tested. Passwords and tokens are stored only as hashes. [Encryption at rest
and in transit for the deployed environment.]

## Contact and grievances

[Grievance officer / contact as required by law.]

## Changes

[How users are told about changes.]
