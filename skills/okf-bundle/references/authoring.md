# Authoring a bundle

## Contents

- [A layout that works](#a-layout-that-works)
- [Write from the code](#write-from-the-code)
- [Evidence rules](#evidence-rules)
- [A worked Attested Computation](#a-worked-attested-computation)
- [Order of work](#order-of-work)

## A layout that works

Group by concern, one index per directory. A service of moderate size lands
around 20-25 documents; far more than that and each one is too thin to earn its
place.

```
knowledge/
  index.md            root listing, the only index that may carry frontmatter
  log.md
  architecture/       how it is built: scoping, the delivery paths, the data model
  api/                the surface: conventions, routes, any proxied contract
  computations/       operations modeled as Attested Computation, plus captured evidence
  playbooks/          procedures: local setup, end-to-end runs, how to add a thing
```

**Do not write one concept per struct or per table.** The code already documents
those, and a markdown copy is guaranteed to drift. One data-model document with
a `house:from`-pinned table is worth twenty mirrors.

Skip a `references/` directory unless something genuinely needs it. If a document
would be 90% overlap with an existing one, the two are one document.

## Write from the code

Read the source and describe what it does. Do not paraphrase the README, and do
not treat a generated specification as authoritative — both are usually behind.
Measuring that is worth doing once:

```sh
git log -1 --format=%ci -- docs/openapi.yaml
git log --oneline -- internal/api/handler/ | head -20
```

A snapshot six weeks behind the handlers will happily teach the bundle its own
errors.

The highest-value document is usually the one that only exists in someone's
head or on one laptop — the end-to-end runbook, the environment gotchas, the
failure whose symptom looks like something else. Prioritise by that, not by
what is easy to write.

**Write down the traps, not just the happy path.** "If every call returns 503
while listing still works, the token minting configuration is missing" saves an
afternoon. The configuration reference does not.

## Evidence rules

Grade every claim by what backs it, and say so in the document:

| Evidence | How to write it |
|---|---|
| In-repo code | Cite the file in `sources[]`, footnote the claims that came from it. |
| A contract owned by another service | Capture it live, **commit the raw capture**, cite the capture and pin the other repository's commit. |
| Observed once, not captured | Say "observed on \<date\>, not part of the committed capture". |
| No evidence | Do not write the document. Four invented contracts are worse than four absent ones. |

A concrete-looking number with no source reads as evidence without being any. If
a sample response shows `"count": 208` and nothing in the bundle can produce
that number, use a generic placeholder instead — the exact value teaches the
reader nothing and changes daily.

When a document describes something that does not currently work, mark it
`status: draft` and say what you observed, including how many times and where.

## A worked Attested Computation

````markdown
---
type: Attested Computation
title: Tail a job log
description: Streams a running job's event log through the service proxy.
tags: [live, logs]
runtime: my-service-live-query
parameters:
  - { name: connection_id, type: string, required: true, in: envelope }
  - { name: job_id, type: integer|string, required: true, in: params }
  - { name: format, type: string, required: false, in: params }
executor:
  resource: ../api/live-query.md
  receipt: [job_id, job_status, done, after_counter]
generated: { by: human:someone@example.com, at: 2026-08-24T21:30:00Z }
stale_after: 2027-02-24T00:00:00Z
sources:
  - id: capture
    resource: live-capture.json
    title: Live catalog capture, 2026-08-24
---

# Computation

```http
POST /v1/live/query
Content-Type: application/json

{
  "resource": "execution_logs",
  "connection_id": "@connection_id",
  "params": { "job_id": @job_id, "format": "@format" }
}
```

## Parameters

`job_id` is required and accepts an integer or a digits-only string.[^capture]

# Attestation

No attester. There is no deterministic checker for this computation, so the
optional `attester` field is absent: this is a contract for invoking the
operation, not evidence that any run happened.

[^capture]: Live catalog capture, 2026-08-24
````

Four things that document gets right and drafts usually get wrong:

1. **Every hole is a declared parameter.** `@connection_id` appears in the
   computation, so it is in `parameters`. Otherwise the document cannot be run
   without editing it, which the spec forbids.
2. **`in:` says where each parameter goes.** An unknown key, which consumers
   must tolerate, and it stops a reader putting an envelope field inside a
   payload that rejects unknown properties.
3. **One fenced block under `# Computation`.** Put the response sample under its
   own `# Response` heading — a `## Response` subsection is still inside the
   computation section, and a mechanical extractor may grab it instead.
4. **`# Attestation` states the gap out loud.** The type is called "Attested";
   a document that attests to nothing must say so rather than leave the reader
   to infer it from an absent field. Omit `attester` — never invent one.

Include `executor.receipt` only for fields a run actually returns. Omitting is
better than guessing.

## Order of work

1. Skeleton: root `index.md` with `okf_version`, `log.md`, one index per
   directory, and **one** real concept.
2. Wire the gate and put it in CI. Everything after this is born validated.
3. The contract other documents point at, then the conventions document.
4. The concepts with in-repo evidence.
5. The rest of the architecture and API documents.
6. The playbooks. The end-to-end one is worth the most time.
7. Only then anything needing captured evidence — and only after the capture.
8. Fill the root index, write the log entry, add one line to the README.
