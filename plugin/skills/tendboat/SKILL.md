---
name: tendboat
description: Taint-analyse this repository across languages and formats. Use when asked to find injection, secret-leak, path-traversal, SSRF, deserialization or missing-authorization defects, when asked what reaches a dangerous call, or before editing a file that handles untrusted input. tendboat holds the whole-repo index and the solver; you supply judgement about the file in front of you.
---

# tendboat

tendboat is the memory of the parts of this repository you are not looking at. It
holds a deterministic index (every function, call, import, HTTP route, deploy
hop), a knowledge base of contracts about third-party callees, and a solver that
composes function summaries to a fixpoint. It cannot read code the way you can,
and it never calls a model. You are the only model in this system.

**Every tool takes `repo` first: the absolute path of the repository you are
working in.** tendboat is reached over MCP, which is one long-lived process that may
serve several projects and was started somewhere neither of you chose — so it
cannot infer which repository you mean, and will not guess. You always know:
it is the directory you are working in. Everything else (`path`, `paths`) is
relative to that `repo`.

Everything you send it is JSON validated against a schema. A rejected call
returns the exact validation errors; read them, fix, and call again. Do not
paraphrase, do not send prose, do not invent field names.

## The sequence

1. **`tendboat_index(repo)`** — once per repository, or after a large checkout change.
   Deterministic, ~30 s on 2000 files, no tokens. Everything else needs it.

2. **`tendboat_scope(repo, paths)`** — call this FIRST when the question is about a change
   rather than the whole repository: a commit, a diff, a handful of files. It
   names the files at the other end of what yours touch, and says which are
   already described. A flow has two ends; describing one and not the other
   finds nothing, and that silence is indistinguishable from a clean result.
   Everything it reports is a table join or a name search over the index --
   `exact` is proven, `candidate` is offered.

3. **`tendboat_view(repo, path)`** — always call this before describing a file. It returns
   the file as a numbered listing with the parser's own facts attached to each
   line: functions and their parameter names, call sites with the callee's
   CANONICAL gid already resolved, string literals, config keys, entry points,
   and deploy mappings. Those annotations are authoritative. Where they disagree
   with your reading of the line, they win.

   Large files are split into bounded parts. When the result says `part N/M`,
   describe only functions marked `[ANALYSE]`, pass `part=N` to
   `tendboat_put_struct`, then call `tendboat_view` again for the next missing part.
   Cached functions are merged only after every part arrives; an interrupted
   sequence remains explicitly incomplete and is never solved as a clean file.

   It does NOT carry the field rules — those are in **The wire format** section
   at the end of this file, together with the JSON Schema each tool validates
   against. Read that once; it is the same for every file, and it is generated
   from the schema tendboat actually enforces, so it cannot be out of date.

4. **`tendboat_put_struct(repo, unit, part=1)`** — the file's STRUCTURE: functions, call sites,
   and port-to-port dataflow edges. **No security judgement here at all** — not
   even a hint of one. This split is not stylistic: when one pass does both, the
   model that is deciding what is dangerous stops enumerating call sites
   exhaustively, and calls that were never written down cannot be judged later.

5. **`tendboat_put_judge(repo, unit)`** — the same file's SECURITY assertions on the ports
   you just declared: sources, sinks, sanitizers, required authorization,
   contracts for external callees, and dangerous constants. Never before step 4
   for that file: judge assertions reference call labels that only exist once
   the structure is stored.

6. **`tendboat_solve(repo)`** — deterministic, ~1 s. Composes everything stored so far,
   including files described in earlier sessions, and returns the findings. Safe
   to call at any point; partial input gives partial results, not an error.

7. **`tendboat_triage(repo, verdicts)`** — after reviewing what `tendboat_solve` returned,
   send back what you decided. Two INDEPENDENT decisions per finding, and the
   full criteria come attached to every `tendboat_solve` that has anything unreviewed
   in it — read them there, they are the authority.

       {"id":"<8 hex>", "verdict":"tp", "severity":"critical|high|medium|low|info",
        "evidence":"..."}
       {"id":"<8 hex>", "verdict":"fp", "fp_reason":"no-flow|source-not-tainted|
        sanitizer-present|wrong-sink|wrong-cwe", "evidence":"...",
        "evidence_loc":"path:line (required for sanitizer-present)"}

   **`fp` means tendboat read the CODE wrong**, and you must say which of its five
   mistakes it made. It does NOT mean "not exploitable here". "This only runs
   locally", "the input is trusted", "this is not exposed today" are claims about
   the deployment, not the code — the deployment changes and the code outlives
   it. Lower the severity instead; `medium` and `low` exist for exactly that.

   **Evidence is required for every verdict** and must be checkable by someone
   who did not do the review: a quoted line, a callee name, a config key and its
   value, the name of the sanitizer you found. "Looks fine" is refused.

   Verdict, severity and evidence are all remembered. The next run finds the same
   flows, hides the false ones while saying how many it hid, and shows the stored
   severity instead of asking again — so the same finding is never reviewed
   twice. A verdict dies on its own when the source or sink line it was about
   changes, which is what stops a stale "not exploitable" from covering a line
   somebody has since made exploitable.

`tendboat_paths(repo, path, line)` answers "what already reaches here" without any work
from you. Prefer it whenever the question is about existing code rather than
code you are writing.

## Rules that matter more than the rest

**Never compose an identifier.** A gid is `<lang>:<module-path>#<local-name>`,
and it is minted by the index, not by you. `tendboat_view` prints the gid of every
call it could resolve; copy it verbatim. For a cross-file target use
`lookup_symbol(repo, name)`; for something launched across a process boundary — a
container CMD, a subprocess, an HTTP route — use `resolve_target(repo, spec)`. If
neither returns a target, the peer is outside this repository: say so with
`external`, do not guess a name. A wrong gid is worse than an absent one,
because it joins with nothing and the flow silently disappears.

**Emit, when unsure.** This feeds a sound over-approximating solver. A missed
source or sink is a false negative that nothing downstream can recover. An
extra one is a false positive that a human filters in seconds.

**A port is a structural position, never a variable name.** `param[0]`,
`$ret`, `<label>.arg[1]`, `@env:PATH`. `tendboat_view` prints the parameter names
against their indices — use those, do not re-derive an index from the signature.

**Check every call for a sanitizer, not only the risky-looking ones.** A missed
sanitizer turns a mitigated flow into a false positive. But do not claim one you
cannot justify: a check whose exception is swallowed, or whose result is
discarded, is not a sanitizer. Claiming it silently deletes a real finding, which
is the one failure mode with no recovery.

## What not to do

- Do not send text where JSON is expected. There is no text mode.
- Do not omit `repo`, and do not send a relative one or `.`. The server's own
  working directory is not yours and is not the project.
- Do not skip `tendboat_view` because you have the file open. Its annotations carry
  resolved identity you cannot derive from the source alone.
- Do not merge steps 4 and 5 into one call, and do not reorder them.
- Do not re-describe a file `tendboat_view` reports as already stored and unchanged.

<!-- BEGIN GENERATED wire format -- generated by tendboat; do not edit -->

## The wire format

Everything below is generated from tendboat's own schema, so it cannot drift
from what the tools actually accept. Read the rules first and the JSON
Schema second: the rules say what a field MEANS, the schema says what
shape it must have. A `@KEY` in the schema points at the rule of that
name in the rules block.

### Filling a StructUnit — `tendboat_put_struct`

```
WIRE FORMAT (two abbreviations the schema refers to):
  @LINE  a Loc is just the ABSOLUTE 1-indexed line number, e.g. 142 -- copy it
         from the `NNNNN| ` margin, never count lines inside an excerpt. Do NOT
         emit a code snippet: tendboat reads it from the file itself.
  edges  a dataflow edge is an object with short keys: {"s":"param[0]",
         "d":"53b.arg[1]"}. `s`/`d` are ports, e.g. `53b.ret`->`$ret`,
         `@env:HOME`->`52.arg[0]`. A call is named by the LINE it is on,
         plus a letter when a line holds several.
  @CHANNEL what carries control OUT of this process, for a boundary target:
           exec http rpc queue event cron ffi config framework convention ipc
         NAME THE CALLEE, do not describe where it lives: call resolve_target
         with what the source says (`/entry.sh`, `python3 app/x.py`,
         `/api/lookup`) and put the gid it returns in `target`. When nothing
         here serves the call -- `apt-get`, someone else's API -- set `external`
         instead; that is correct, not a failure. `phase="build"` for an
         image-build step, which reaches nothing at runtime.

You extract STRUCTURE from a source file into a StructUnit: what gets called
(including framework/config/reflective dispatch, subprocess, HTTP, queue) and
how data flows port-to-port between params, call-args/rets, returns, and
globals. NO security judgments -- just calls and dataflow edges.

The file listing is authoritative for this file: its annotations --
functions, call sites, literals -- are parser output, not hints -- trust them
over your own reading. tendboat's tools exist for what the listing cannot hold:
  lookup_symbol(name)   name -> CANONICAL gid (see @GID)
  resolve_target(spec)  what a cross-boundary call launches -> its entry gid
Use your own tools to read another file or search the repository.

Output ONE StructUnit matching the schema. Read every field description.
-- HOW TO READ THE LISTING --
Lines are `NNNNN| <source>`, NNNNN = the file's own 1-based line number. A line
may be followed by annotation lines carrying the SAME number and `>`:

  NNNNN>  fn <gid> [first..last] [ENTRY]  params: 0=<name> 1=<name> ...
  NNNNN>  [<label>] <kind> <callee-gid> args=<n> rets=<n>   [rule <kind> <port> <cwes>]
  NNNNN>  call <qualifier.callee>/<argc> [recv]  (<args>)   [<name> = <gid>] | = <gid>(<sig>) | ?N
  NNNNN>  lit <value> <- <what it is attached to>
  NNNNN>  cfg <shape> <full.path.key> = <value>

Annotations are parser and structural-pass output, not hints: where they
disagree with your reading of the line, they win. Specifics:
  * `fn` sits on the line that declares the function; its range covers the
    decorators and modifiers above it.
  * `ENTRY <channel>` on a `fn` row is the channel the PARSER read out of this
    file. Copy it verbatim; the far end must match it character for character.
  * argc = EXPLICIT args as the parser counts them; Call.n_args ALSO counts the
    receiver as arg[0], so add 1 when the callee is an instance/class/bound
    method -- whether or not `recv` is shown, an implicit receiver still occupies
    param[0]. `args=` on a `call` annotation already includes it.
  * `[name = gid]` means the qualifier is an IMPORT resolved to that target --
    use it, do not guess the module. `= gid(sig)` is THE definition in this
    project: copy that gid verbatim into Call.target.gid. `?N` means N
    candidates, listed under it -- pick by the argument types. NO marker at all
    means the callee is NOT defined in this project, so emit an external gid and
    do not invent a local one.
  * `rule` means this callee already has an established Assume*, and the analyzer
    applies it whether or not you repeat it. Do not re-derive it; add what is
    missing.
  * A call's LABEL is what you refer to it by: the line number when it is the
    only call on that line, the number plus the printed letter otherwise
    (`52`, `53a`, `53b`). Use it wherever the schema wants a call id.
  * A line with no annotation had nothing the parser could resolve.

=== FIELD RULES (the schema references these as @KEY) ===
@PORT:
A dataflow endpoint -- structural positions only, NEVER a local variable name:
  param[i]              this fn's i-th parameter (0-indexed; receiver = param[0])
  $ret  $ret[i]  $exc   this fn's return slot(s) / exception slot
  <label>.arg[i]  <label>.ret   argument passed to / returned by that call
  @env:X @file:/p @secret:v:p @db:...   cross-unit global
  <any>.field  <any>.*   access-path suffix (field / container element)
@GID:
Canonical global function/type id: <lang>:<module-path>#<local-name>[!<sig>].

== HOW TO EMIT ==
  THIS file's defs:   copy the listing's `unit-gid:` line verbatim as
                      the part before `#`. Do NOT recompute it. If the
                      listing has no such line, compose it per the
                      table below.
  In-repo cross-file: call lookup_symbol(name) -- it returns the exact
                      gid the analyzer indexes; use it verbatim.
  External/stdlib:    compose per the table below.

module-path = the CONTAINER (package/namespace/module/file), NOT the
class. The class goes in local-name.
  java kotlin scala csharp groovy  package/namespace    com.foo
  python                           dotted module        app.views
  go                               import path          github.com/x/y/pkg
  cpp                              namespace            std
  rust                             crate::module        std::process
  swift ruby                       Module               Foundation
  php                              Namespace            App\Http\Controllers
  js ts c bash lua perl            repo-rel file path   src/app.js  scripts/x.sh
  docker                           image ref            acme/myapp
  hcl yaml                         repo-rel file        main.tf
  sql                              db.schema            mydb.public

local-name = <Class>.<method> for class members, or bare <func> for
top-level. Nested classes dot-join: Outer.Inner.method. Receiver/self
is NOT part of the name. Overloads: append !TypeA_TypeB. Lambdas:
<parent-local>.<lam@L:C>.

Examples (note class is AFTER #):
  java:com.example#Foo.bar             NOT java:com.example.Foo#bar
  csharp:System.Diagnostics#Process.Start
  python:os#system   python:app.models#User.save
  cpp:std#vector.push_back   rust:std::process#Command.new
```

### Filling the judgement — `tendboat_put_judge`

```
WIRE FORMAT (two abbreviations the schema refers to):
  @LINE  a Loc is just the ABSOLUTE 1-indexed line number, e.g. 142 -- copy it
         from the `NNNNN| ` margin, never count lines inside an excerpt. Do NOT
         emit a code snippet: tendboat reads it from the file itself.
  label  a call is named by the LINE it is annotated under, plus a letter
         when a line holds several: `52`, `53a`, `53b`.

You are a security reviewer. Given a source file as a LISTING with the
structural pass's calls annotated onto its lines, emit taint assertions on
ports. The analyzer knows
NOTHING about which APIs are dangerous -- if you don't assert it, it's
invisible.

RECALL OVER PRECISION: this feeds a sound over-approximating analyzer.
A missed source or sink is a false negative (unfixable downstream). An
extra one is a false positive (filterable). When unsure, EMIT.

The listing already holds this file's call sites, arg counts, literals and
numbered source. For a canonical gid call
lookup_symbol; use your own tools to read another file.

For each fn (by fn_gid) -- enumerate EXHAUSTIVELY:
  sources[]   -- ports where a security-relevant property ORIGINATES via a
                 mechanism you can name AT THAT PORT, independent of what
                 any caller passes. If the only evidence is "a caller could
                 pass one", that is NOT a source -- the analyzer already
                 propagates caller taint into params via summaries; emitting
                 a Source there yields tautological findings and discards
                 the real origin.
                 Emit for:
                   - <label>.ret of a boundary read -- mechanism = the OS/file/
                     socket/HTTP/DB/wire that produced it.
                   - param[i] ONLY when this fn is invoked by something
                     OUTSIDE the codebase: framework dispatch (HTTP route,
                     message listener, scheduler), CLI main/argv, plugin/
                     SPI callback, native upcall, deserializer hook.
                   - param[0].<field> or @global that is state loaded from
                     config/DB/deserialization -- mechanism = that loader.
                   - <label>.ret of a weak/hardcoded construction (new Random(),
                     MD5, literal credential) -- mechanism = construction.
                 Do NOT emit for:
                   - param[i] of an ordinary function (public or private)
                     "because a caller might pass tainted data".
                   - <label>.ret of an in-repo callee (its summary carries the
                     origin out).
                 A pure transformer (basename/trim/toLower) is
                 assume_propagate, not Source. A boundary READER (readLine,
                 getConfig, nextToken) IS a Source.
  sinks[]     -- for EVERY call annotated in the listing, ask: is any of its
                 args dangerous if tainted? Emit an inline Sink on that
                 port. List EVERY CWE the operation can realize -- not just
                 the most obvious one. Emit
                 inline sinks[] IN ADDITION to assume_sink for the callee
                 gid -- inline is the exact port, assume is the pattern.
  sanitizes[] -- for EVERY annotated call, check the callee NAME: does it indicate
                 sanitisation, validation, encoding or an authz check? If yes, emit
                 Sanitize(call=<label>, removes=[CWEs it neutralizes]). Also
                 authz checks remove CWE-862/863/306. Missing a sanitize turns a mitigated
                 flow into a false positive, so check EVERY call's callee
                 name, not only the ones that look risky.
  requires[]  -- calls that MUTATE protected state. NOT output-only ops
                 (echo/print/log) -- those are sinks for CWE-532/200.

PORT INDEXING: use the `params:` mapping on each `fn` annotation.
When your `why` text names a parameter, copy the name at the port index
you emit -- do not re-derive the index from the source signature.

assumes[] -- one Assume* per DISTINCT external gid annotated in the listing: its
taint I/O relation (assume_source/sink/sanitize/propagate).
  For GETTERS/field-accessors, make assume_propagate FIELD-SPECIFIC:
  `in_port="self.<fieldName>" out_port="ret"` (e.g. getExitValue ->
  self.exitValue -> ret). The analyzer is field-sensitive; a bare
  `self -> ret` over-taints sibling fields.

An in-project callee needs no lookup: the analyzer composes function summaries
to a fixpoint, so its effect is already accounted for. An external one has no
body in this repo to read. Judge from the ports and the source you were given.
-- HOW TO READ THE LISTING --
Lines are `NNNNN| <source>`, NNNNN = the file's own 1-based line number. A line
may be followed by annotation lines carrying the SAME number and `>`:

  NNNNN>  fn <gid> [first..last] [ENTRY]  params: 0=<name> 1=<name> ...
  NNNNN>  [<label>] <kind> <callee-gid> args=<n> rets=<n>   [rule <kind> <port> <cwes>]
  NNNNN>  call <qualifier.callee>/<argc> [recv]  (<args>)   [<name> = <gid>] | = <gid>(<sig>) | ?N
  NNNNN>  lit <value> <- <what it is attached to>
  NNNNN>  cfg <shape> <full.path.key> = <value>

Annotations are parser and structural-pass output, not hints: where they
disagree with your reading of the line, they win. Specifics:
  * `fn` sits on the line that declares the function; its range covers the
    decorators and modifiers above it.
  * `ENTRY <channel>` on a `fn` row is the channel the PARSER read out of this
    file. Copy it verbatim; the far end must match it character for character.
  * argc = EXPLICIT args as the parser counts them; Call.n_args ALSO counts the
    receiver as arg[0], so add 1 when the callee is an instance/class/bound
    method -- whether or not `recv` is shown, an implicit receiver still occupies
    param[0]. `args=` on a `call` annotation already includes it.
  * `[name = gid]` means the qualifier is an IMPORT resolved to that target --
    use it, do not guess the module. `= gid(sig)` is THE definition in this
    project: copy that gid verbatim into Call.target.gid. `?N` means N
    candidates, listed under it -- pick by the argument types. NO marker at all
    means the callee is NOT defined in this project, so emit an external gid and
    do not invent a local one.
  * `rule` means this callee already has an established Assume*, and the analyzer
    applies it whether or not you repeat it. Do not re-derive it; add what is
    missing.
  * A call's LABEL is what you refer to it by: the line number when it is the
    only call on that line, the number plus the printed letter otherwise
    (`52`, `53a`, `53b`). Use it wherever the schema wants a call id.
  * A line with no annotation had nothing the parser could resolve.


ALSO, in the same answer, emit `config`: dangerous CONSTANTS -- values whose text AS WRITTEN is itself the weakness.
  1. is the token lexically constant here (a literal/keyword/flag whose value a reader knows from this line alone)?
  2. would replacing THAT token with a safe value fix the issue at this line, with no other change?
Both yes -> emit. An empty list is valid and common.

=== FIELD RULES (the schema references these as @KEY) ===
@GID:
Canonical global function/type id: <lang>:<module-path>#<local-name>[!<sig>].

== HOW TO EMIT ==
  THIS file's defs:   copy the listing's `unit-gid:` line verbatim as
                      the part before `#`. Do NOT recompute it. If the
                      listing has no such line, compose it per the
                      table below.
  In-repo cross-file: call lookup_symbol(name) -- it returns the exact
                      gid the analyzer indexes; use it verbatim.
  External/stdlib:    compose per the table below.

module-path = the CONTAINER (package/namespace/module/file), NOT the
class. The class goes in local-name.
  java kotlin scala csharp groovy  package/namespace    com.foo
  python                           dotted module        app.views
  go                               import path          github.com/x/y/pkg
  cpp                              namespace            std
  rust                             crate::module        std::process
  swift ruby                       Module               Foundation
  php                              Namespace            App\Http\Controllers
  js ts c bash lua perl            repo-rel file path   src/app.js  scripts/x.sh
  docker                           image ref            acme/myapp
  hcl yaml                         repo-rel file        main.tf
  sql                              db.schema            mydb.public

local-name = <Class>.<method> for class members, or bare <func> for
top-level. Nested classes dot-join: Outer.Inner.method. Receiver/self
is NOT part of the name. Overloads: append !TypeA_TypeB. Lambdas:
<parent-local>.<lam@L:C>.

Examples (note class is AFTER #):
  java:com.example#Foo.bar             NOT java:com.example.Foo#bar
  csharp:System.Diagnostics#Process.Start
  python:os#system   python:app.models#User.save
  cpp:std#vector.push_back   rust:std::process#Command.new
```

### The schemas, as JSON Schema

`unit` is a JSON **string** containing an object of this shape. It arrives
as a string on purpose: declared as a tool parameter these schemas would be
resident in your system prompt on every turn, including turns that never
touch tendboat.

#### `tendboat_put_struct` — StructUnit

```json
{
 "$defs": {
  "Call": {
   "additionalProperties": false,
   "description": "One control-transfer edge. `id` is how dataflow/assertions reference it.",
   "properties": {
    "id": {
     "description": "Id of a call within this fn: the label printed under its line -- the bare line number, plus a letter when a line holds several (52, 53a, 53b).",
     "maxLength": 8,
     "pattern": "^(?:c\\d+|\\d+[a-z]?)$",
     "type": "string"
    },
    "loc": {
     "description": "@LINE",
     "type": "integer"
    },
    "n_args": {
     "description": "How many args this call has (so <label>.arg[i] is bounded). COUNT THE RECEIVER: `obj.foo(x)` -> n_args=2, arg[0]=obj, arg[1]=x. An IMPLICIT receiver counts too: a bare `foo(x)` calling a method of this class is n_args=2, arg[0]=self, arg[1]=x -- arg[i] has to line up with the callee's param[i], and param[0] of an instance method IS the receiver. A free function `strlen(s)` -> n_args=1, arg[0]=s. `foo()` with all-literal args -> n_args=0.",
     "maximum": 32,
     "minimum": 0,
     "type": "integer"
    },
    "n_rets": {
     "description": "How many return values (0 for void).",
     "maximum": 8,
     "minimum": 0,
     "type": "integer"
    },
    "target": {
     "anyOf": [
      {
       "$ref": "#/$defs/TDirect"
      },
      {
       "$ref": "#/$defs/TVirtual"
      },
      {
       "$ref": "#/$defs/TBoundary"
      },
      {
       "$ref": "#/$defs/TFramework"
      },
      {
       "$ref": "#/$defs/TRegistered"
      },
      {
       "$ref": "#/$defs/TReflective"
      },
      {
       "$ref": "#/$defs/TAnyOf"
      },
      {
       "$ref": "#/$defs/TUnknown"
      }
     ],
     "discriminator": {
      "mapping": {
       "any_of": "#/$defs/TAnyOf",
       "boundary": "#/$defs/TBoundary",
       "direct": "#/$defs/TDirect",
       "framework": "#/$defs/TFramework",
       "reflective": "#/$defs/TReflective",
       "registered": "#/$defs/TRegistered",
       "unknown": "#/$defs/TUnknown",
       "virtual": "#/$defs/TVirtual"
      },
      "propertyName": "kind"
     }
    }
   },
   "required": [
    "id",
    "target",
    "n_args",
    "n_rets",
    "loc"
   ],
   "type": "object"
  },
  "DataflowEdge": {
   "additionalProperties": false,
   "description": "`src` reaches `dst`. One edge per distinct pair; duplicates are harmless.",
   "properties": {
    "d": {
     "description": "@PORT",
     "maxLength": 512,
     "pattern": "^(param\\[\\d+\\]|\\$ret(\\[\\d+\\])?|\\$exc|(?:c\\d+|\\d+[a-z]?)\\.(arg\\[\\d+\\]|ret(\\[\\d+\\])?)|@(env|file|db|queue|mem|cache|secret|config|cloud|k8s|mailbox|tfvar):[^\\s]+)(\\.[\\w*]+)*$",
     "type": "string"
    },
    "s": {
     "description": "@PORT",
     "maxLength": 512,
     "pattern": "^(param\\[\\d+\\]|\\$ret(\\[\\d+\\])?|\\$exc|(?:c\\d+|\\d+[a-z]?)\\.(arg\\[\\d+\\]|ret(\\[\\d+\\])?)|@(env|file|db|queue|mem|cache|secret|config|cloud|k8s|mailbox|tfvar):[^\\s]+)(\\.[\\w*]+)*$",
     "type": "string"
    }
   },
   "required": [
    "s",
    "d"
   ],
   "type": "object"
  },
  "EntryBind": {
   "additionalProperties": false,
   "description": "Binds one handler param to a source CWE-set (untrusted-input family).",
   "properties": {
    "cwes": {
     "description": "Analyzer seeds taint(param) with this set at the entry point.",
     "items": {
      "description": "The CWE you would cite in a finding, most specific first.",
      "maxLength": 9,
      "minLength": 5,
      "pattern": "^CWE-\\d{1,5}$",
      "type": "string"
     },
     "maxItems": 32,
     "minItems": 1,
     "type": "array"
    },
    "port": {
     "description": "param[i], or param[i].field for one field of the incoming value",
     "examples": [
      "param[1]",
      "param[1].body"
     ],
     "maxLength": 128,
     "type": "string"
    }
   },
   "required": [
    "port",
    "cwes"
   ],
   "type": "object"
  },
  "EntryDecl": {
   "additionalProperties": false,
   "description": "External -> fn edge. `channel` covers not just transports but also\nframework/config/convention triggers.",
   "properties": {
    "binds": {
     "description": "Per-param source CWEs (which params carry untrusted input).",
     "items": {
      "$ref": "#/$defs/EntryBind"
     },
     "maxItems": 16,
     "type": "array"
    },
    "channel": {
     "description": "What causes fn_gid to be invoked from OUTSIDE this codebase -- one per external trigger.\nFIRST: if the listing marks the fn `ENTRY <channel>`, or a `-- entries --` section names it, copy that channel VERBATIM -- the parser read it out of the file and cannot mis-spell it. Compose one yourself only for a trigger the listing does not carry:\n  exec:<gid>                CLI entry, container CMD/ENTRYPOINT, subprocess target\n  http:METHOD:host:/path    HTTP route (REST/GraphQL)\n  grpc:pkg.Svc/Method       RPC\n  queue:sys:topic           message consumer\n  event:domain:name         DOM/UI/cloud event\n  framework:<fw>:<trigger>  Spring @Controller, Flask @route, Rails action,\n                            k8s reconcile, docker build stage\n  config:<file>#<key>       class/handler named in a config value\n  convention:<pattern>      naming-convention dispatch (Rails, Next.js pages/)\n  cron:<spec>               scheduled\nSpell it exactly as @CHANNEL prescribes: the boundary on the other side must match character for character or the join finds nothing.",
     "maxLength": 512,
     "minLength": 2,
     "pattern": "^(http|grpc|exec|ffi|queue|ipc|signal|event|cloud|db|framework|config|convention|cron)(:.+)?$",
     "type": "string"
    },
    "fn_gid": {
     "description": "@GID",
     "examples": [
      "java:com.example#Foo.bar",
      "python:os#system",
      "go:net/http#Client.Do",
      "c:libc#system",
      "rust:std::process#Command.new",
      "js:src/app.js#handler"
     ],
     "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
     "type": "string"
    },
    "loc": {
     "description": "@LINE",
     "type": "integer"
    }
   },
   "required": [
    "channel",
    "fn_gid",
    "binds",
    "loc"
   ],
   "type": "object"
  },
  "StructFn": {
   "additionalProperties": false,
   "description": "Structural view of one function: what it calls and how data moves\nbetween call-ports, params, returns, and globals. NO security judgments.",
   "properties": {
    "attrs": {
     "items": {
      "enum": [
       "entry",
       "async",
       "ctor",
       "model"
      ],
      "type": "string"
     },
     "maxItems": 4,
     "type": "array"
    },
    "calls": {
     "description": "Every control-transfer OUT of this fn. See Target -- includes framework/registered/reflective, not just language-level calls. Name each one by the LINE it is on: the bare line number when it is the only call there, the number plus a letter in source order otherwise (`52`, `53a`, `53b`).",
     "items": {
      "$ref": "#/$defs/Call"
     },
     "maxItems": 96,
     "type": "array"
    },
    "dataflow": {
     "description": "Unordered set of resolved port-to-port edges. Resolve THROUGH intermediate locals, packing, formatting, builders and awaits, and emit only the endpoints -- never a local variable name:\n  bar(foo(p) + 1)      -> param[0] to 52.arg[0]; 52.ret to 53.arg[0]\n  o.f = p; bar(o)      -> param[0] to 52.arg[0].f (access-path suffix)\n  x = a if c else b    -> both edges (over-approximate)\nAn extra edge is a false positive and sound; a missing edge is a false negative and unfixable downstream. Prefer over-emitting.",
     "items": {
      "$ref": "#/$defs/DataflowEdge"
     },
     "maxItems": 256,
     "type": "array"
    },
    "gid": {
     "description": "@GID",
     "examples": [
      "java:com.example#Foo.bar",
      "python:os#system",
      "go:net/http#Client.Do",
      "c:libc#system",
      "rust:std::process#Command.new",
      "js:src/app.js#handler"
     ],
     "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
     "type": "string"
    },
    "loc": {
     "description": "@LINE",
     "type": "integer"
    },
    "n_params": {
     "maximum": 64,
     "minimum": 0,
     "type": "integer"
    },
    "param_names": {
     "description": "Names in PORT-INDEX order, length == n_params. Index 0 is the receiver on instance/class/bound methods (use whatever the language calls it -- the object the method is invoked on, implicit or not); explicit parameters follow. For a function with no receiver, index 0 is the first explicit parameter. This is the authoritative index<->name map the assert pass cites in its evidence.",
     "items": {
      "type": "string"
     },
     "maxItems": 64,
     "type": "array"
    }
   },
   "required": [
    "gid",
    "n_params",
    "param_names",
    "attrs",
    "loc",
    "calls",
    "dataflow"
   ],
   "type": "object"
  },
  "TAnyOf": {
   "additionalProperties": false,
   "properties": {
    "gids": {
     "items": {
      "description": "@GID",
      "examples": [
       "java:com.example#Foo.bar",
       "python:os#system",
       "go:net/http#Client.Do",
       "c:libc#system",
       "rust:std::process#Command.new",
       "js:src/app.js#handler"
      ],
      "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
      "type": "string"
     },
     "maxItems": 16,
     "minItems": 1,
     "type": "array"
    },
    "kind": {
     "const": "any_of",
     "type": "string"
    }
   },
   "required": [
    "kind",
    "gids"
   ],
   "type": "object"
  },
  "TBoundary": {
   "additionalProperties": false,
   "description": "A call that leaves this process or language.\n\nNAME THE CALLEE, do not describe where it lives. `resolve_target` turns what\nthe source says -- `/entry.sh`, `python3 app/ingest.py`, `/api/lookup`, a\nfully-qualified name -- into the gid of the entry point, and `target` carries\nthat gid. Then there is nothing to match.\n\nA resolved gid is authoritative. Free-form addresses are not stable enough\nto join independently described call and entry points.\n\n`external` is the honest answer when nothing in this repository serves the\ncall -- `apt-get`, `git`, someone else's HTTP API. It is not a failure and it\nis not counted as one. `resolve_target` says so explicitly when it finds\nnothing.\n\n`phase=\"build\"` marks a step that runs while the image is built, not while it\nserves: `RUN go build`, `RUN apt-get install`. Such calls have no runtime\nentry point.",
   "properties": {
    "external": {
     "description": "Set INSTEAD of `target` when nothing here serves the call: the command name, the foreign host and path. Correct and expected, not a failure.",
     "maxLength": 512,
     "type": "string"
    },
    "how": {
     "anyOf": [
      {
       "enum": [
        "exec",
        "http",
        "rpc",
        "queue",
        "event",
        "cron",
        "ffi",
        "config",
        "framework",
        "convention",
        "ipc"
       ],
       "type": "string"
      },
      {
       "type": "null"
      }
     ],
     "description": "Which mechanism carries control out of this process."
    },
    "kind": {
     "const": "boundary",
     "type": "string"
    },
    "phase": {
     "description": "`build` for an image-build step, which reaches nothing.",
     "enum": [
      "runtime",
      "build"
     ],
     "type": "string"
    },
    "target": {
     "anyOf": [
      {
       "description": "@GID",
       "examples": [
        "java:com.example#Foo.bar",
        "python:os#system",
        "go:net/http#Client.Do",
        "c:libc#system",
        "rust:std::process#Command.new",
        "js:src/app.js#handler"
       ],
       "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
       "type": "string"
      },
      {
       "type": "null"
      }
     ],
     "description": "Gid of the entry point this call reaches, from `resolve_target`. Set this whenever the callee lives in THIS repository."
    }
   },
   "required": [
    "kind",
    "how",
    "target",
    "external",
    "phase"
   ],
   "type": "object"
  },
  "TDirect": {
   "additionalProperties": false,
   "description": "Statically-known callee: same-module call, static method, FFI symbol.",
   "properties": {
    "gid": {
     "description": "@GID",
     "examples": [
      "java:com.example#Foo.bar",
      "python:os#system",
      "go:net/http#Client.Do",
      "c:libc#system",
      "rust:std::process#Command.new",
      "js:src/app.js#handler"
     ],
     "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
     "type": "string"
    },
    "kind": {
     "const": "direct",
     "type": "string"
    }
   },
   "required": [
    "kind",
    "gid"
   ],
   "type": "object"
  },
  "TFramework": {
   "additionalProperties": false,
   "description": "A framework will invoke `gid` (DI, annotation, scheduler, ORM hook,\nservlet mapping). Emit at the REGISTRATION site, not at the callee.",
   "properties": {
    "gid": {
     "description": "The fn the framework will call.",
     "examples": [
      "java:com.example#Foo.bar",
      "python:os#system",
      "go:net/http#Client.Do",
      "c:libc#system",
      "rust:std::process#Command.new",
      "js:src/app.js#handler"
     ],
     "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
     "type": "string"
    },
    "kind": {
     "const": "framework",
     "type": "string"
    }
   },
   "required": [
    "kind",
    "gid"
   ],
   "type": "object"
  },
  "TReflective": {
   "additionalProperties": false,
   "description": "Target computed from a runtime string. `hints` = the concrete gids it can\nresolve to, when a constant/switch/config makes that visible; empty = unknown.",
   "properties": {
    "hints": {
     "description": "Concrete gids this can resolve to, if inferable. Analyzer treats as any_of over hints; empty = havoc.",
     "items": {
      "description": "@GID",
      "examples": [
       "java:com.example#Foo.bar",
       "python:os#system",
       "go:net/http#Client.Do",
       "c:libc#system",
       "rust:std::process#Command.new",
       "js:src/app.js#handler"
      ],
      "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
      "type": "string"
     },
     "maxItems": 16,
     "type": "array"
    },
    "kind": {
     "const": "reflective",
     "type": "string"
    }
   },
   "required": [
    "kind",
    "hints"
   ],
   "type": "object"
  },
  "TRegistered": {
   "additionalProperties": false,
   "description": "`gid` is named as a string in a config/resource file and some loader will\ninstantiate or invoke it.",
   "properties": {
    "gid": {
     "description": "The fn the config value names.",
     "examples": [
      "java:com.example#Foo.bar",
      "python:os#system",
      "go:net/http#Client.Do",
      "c:libc#system",
      "rust:std::process#Command.new",
      "js:src/app.js#handler"
     ],
     "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
     "type": "string"
    },
    "kind": {
     "const": "registered",
     "type": "string"
    }
   },
   "required": [
    "kind",
    "gid"
   ],
   "type": "object"
  },
  "TUnknown": {
   "additionalProperties": false,
   "description": "Last resort. Prefer `reflective` with hints=[] over this.",
   "properties": {
    "kind": {
     "const": "unknown",
     "type": "string"
    }
   },
   "required": [
    "kind"
   ],
   "type": "object"
  },
  "TVirtual": {
   "additionalProperties": false,
   "description": "Instance dispatch: use the STATIC type. With no static type, `*#method`.",
   "properties": {
    "gid": {
     "pattern": "^(\\*#[\\w.]+|[a-z][\\w+]*:[\\w./\\-@:]+#[\\w.<>~@:!/]+)$",
     "type": "string"
    },
    "kind": {
     "const": "virtual",
     "type": "string"
    }
   },
   "required": [
    "kind",
    "gid"
   ],
   "type": "object"
  }
 },
 "additionalProperties": false,
 "description": "One source file as structure: what it calls, and what reaches what.\n\nExtract what the code DOES, not what it means for security -- a separate\npass judges that, and a CWE here is out of place. Copy unit_gid and file\nverbatim; one StructFn per function in the file.",
 "properties": {
  "entries": {
   "items": {
    "$ref": "#/$defs/EntryDecl"
   },
   "maxItems": 32,
   "type": "array"
  },
  "file": {
   "description": "Repo-relative source path (the one in the listing's header), or `<synthetic>` for [model] stubs.",
   "maxLength": 512,
   "minLength": 1,
   "pattern": "^(<[a-z]+>|[A-Za-z0-9_./\\-]+)$",
   "type": "string"
  },
  "fns": {
   "description": "Functions assigned to this tendboat_view part. May be empty when every function was safely reused from FnCache; unit-level entries are still emitted.",
   "items": {
    "$ref": "#/$defs/StructFn"
   },
   "maxItems": 96,
   "type": "array"
  },
  "unit_gid": {
   "maxLength": 512,
   "pattern": "^[a-z][\\w+]*:[\\w./\\-@:]+$",
   "type": "string"
  }
 },
 "required": [
  "unit_gid",
  "file",
  "entries",
  "fns"
 ],
 "type": "object"
}
```

#### `tendboat_put_judge` — AssertWithConfig

```json
{
 "$defs": {
  "AssertFn": {
   "additionalProperties": false,
   "description": "Agent B output: security semantics for one StructUnit.\n\n== YOUR TASK ==\nYou are a security reviewer. Given source code and its StructUnit (calls +\ndataflow graph), emit taint assertions on ports. The analyzer has ZERO\nbuilt-in knowledge -- if you don't assert it, it's invisible.\n\nFor each fn (referenced by fn_gid):\n  sources[]   -- which ports carry externally-originating / sensitive /\n                 dangerous-constant data. cwes = every CWE it can trigger.\n                 Typical: param[i] of an entry fn, <label>.ret of a\n                 read/recv/getenv, @env:X, @secret:...\n  sinks[]     -- which ports are dangerous if tainted. cwe = the specific\n                 MITRE CWE. Typical: <label>.arg[i] of exec/query/write/log/\n                 open/render/http-client/deserialize.\n  sanitizes[] -- which calls remove CWEs (escape/quote/validate) OR are\n                 auth checks (removes CWE-306/862/863).\n  requires[]  -- which calls require authorization (DB write/delete, admin\n                 op, resource mutation, protected write).\n\nassumes[] -- one Assume* per DISTINCT external gid annotated in the\nlisting: its taint I/O relation.\n\n== PORT REFERENCES ==\nUse port ids EXACTLY as the listing labels them: `53b.arg[0]`, `param[1]`,\n`52.ret`, `@env:X`. A call's label is the line it is annotated under.\n\n== CWE ==\nList every CWE id that applies. Enumerate exhaustively -- do not stop at\nthe first; an unlisted CWE cannot fire, an extra one is filtered by the\nanalyzer. Err toward listing more.",
   "properties": {
    "fn_gid": {
     "description": "@GID",
     "examples": [
      "java:com.example#Foo.bar",
      "python:os#system",
      "go:net/http#Client.Do",
      "c:libc#system",
      "rust:std::process#Command.new",
      "js:src/app.js#handler"
     ],
     "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
     "type": "string"
    },
    "requires": {
     "items": {
      "$ref": "#/$defs/Requires"
     },
     "maxItems": 48,
     "type": "array"
    },
    "sanitizes": {
     "items": {
      "$ref": "#/$defs/Sanitize"
     },
     "maxItems": 48,
     "type": "array"
    },
    "sinks": {
     "items": {
      "$ref": "#/$defs/Sink"
     },
     "maxItems": 48,
     "type": "array"
    },
    "sources": {
     "items": {
      "$ref": "#/$defs/Source"
     },
     "maxItems": 48,
     "type": "array"
    }
   },
   "required": [
    "fn_gid",
    "sources",
    "sinks",
    "sanitizes",
    "requires"
   ],
   "type": "object"
  },
  "AssertUnit": {
   "additionalProperties": false,
   "description": "Security semantics for one StructUnit: taint assertions on its ports.\n\nThe analyzer has ZERO built-in knowledge of dangerous APIs -- whatever you do\nnot assert is invisible to it, permanently. Port ids must match the\nStructUnit exactly (`53b.arg[0]`, `param[1]`, `52.ret`, `@env:X`); an id that\ndoes not appear there asserts nothing.",
   "properties": {
    "assumes": {
     "items": {
      "anyOf": [
       {
        "$ref": "#/$defs/AssumeSource"
       },
       {
        "$ref": "#/$defs/AssumeSink"
       },
       {
        "$ref": "#/$defs/AssumeSanitize"
       },
       {
        "$ref": "#/$defs/AssumePropagate"
       },
       {
        "$ref": "#/$defs/AssumeInvoke"
       }
      ],
      "discriminator": {
       "mapping": {
        "assume_invoke": "#/$defs/AssumeInvoke",
        "assume_propagate": "#/$defs/AssumePropagate",
        "assume_sanitize": "#/$defs/AssumeSanitize",
        "assume_sink": "#/$defs/AssumeSink",
        "assume_source": "#/$defs/AssumeSource"
       },
       "propertyName": "kind"
      }
     },
     "maxItems": 64,
     "type": "array"
    },
    "fns": {
     "items": {
      "$ref": "#/$defs/AssertFn"
     },
     "maxItems": 96,
     "type": "array"
    },
    "unit_gid": {
     "maxLength": 512,
     "pattern": "^[a-z][\\w+]*:[\\w./\\-@:]+$",
     "type": "string"
    }
   },
   "required": [
    "unit_gid",
    "assumes",
    "fns"
   ],
   "type": "object"
  },
  "AssumeInvoke": {
   "additionalProperties": false,
   "description": "`gid` CALLS one of its arguments (higher-order: map/then/submit/forEach).\nThe analyzer adds a synthetic call edge from the call-site to `callback_port`'s\nvalue with `passes` mapping caller-side data to the callback's params.",
   "properties": {
    "callback_port": {
     "description": "Which arg is the callback that gets invoked: `arg[1]`",
     "examples": [
      "arg[0]",
      "arg[1]"
     ],
     "maxLength": 128,
     "minLength": 3,
     "pattern": "^(<-\\s*|->\\s*)?(arg\\[(\\d+|\\*|\\d+\\.\\.)\\](\\.param\\[\\d+\\]|\\.ret)?|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*(\\s*(<-|->)\\s*(arg\\[(\\d+|\\*|\\d+\\.\\.)\\]|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*)?$",
     "type": "string"
    },
    "gid": {
     "description": "@GID",
     "examples": [
      "java:com.example#Foo.bar",
      "python:os#system",
      "go:net/http#Client.Do",
      "c:libc#system",
      "rust:std::process#Command.new",
      "js:src/app.js#handler"
     ],
     "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
     "type": "string"
    },
    "kind": {
     "const": "assume_invoke",
     "type": "string"
    },
    "loc": {
     "description": "@LINE",
     "type": "integer"
    },
    "passes": {
     "description": "What the callback receives as its params: `self.*` (each element), `arg[0]` (forwarded), etc. Empty = callback gets no tainted args.",
     "items": {
      "description": "Port on a function's boundary. Forms:\n  arg[0]  arg[*]  arg[1..]      positional param(s)\n  ret  ret[1]                   return value(s)\n  self                          receiver\n  arg[0].fieldName              access path into a param\n  arg[1].param[0]  arg[1].ret   higher-order: the callback's own param/ret\n  <- arg[0]     -> ret          direction prefix (sink / source)\n  arg[0] -> ret                 propagate spec",
      "maxLength": 128,
      "minLength": 3,
      "pattern": "^(<-\\s*|->\\s*)?(arg\\[(\\d+|\\*|\\d+\\.\\.)\\](\\.param\\[\\d+\\]|\\.ret)?|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*(\\s*(<-|->)\\s*(arg\\[(\\d+|\\*|\\d+\\.\\.)\\]|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*)?$",
      "type": "string"
     },
     "maxItems": 8,
     "type": "array"
    },
    "scope": {
     "description": "`agnostic` = a fact about a third-party or standard-library API, true in EVERY project that calls it (`org.slf4j#Logger.info` writes its arguments to the log everywhere). `project` = about this codebase's own abstractions, or a behaviour you inferred from how THIS project uses a dependency. Leave empty if unsure: a wrong `agnostic` rule is inherited by projects that never saw it derived.",
     "enum": [
      "",
      "agnostic",
      "project"
     ],
     "type": "string"
    },
    "why": {
     "description": "1-2 sentences: (a) what this API does at runtime, (b) which security-relevant PROPERTY that gives its output (for assume_source) or which consequence follows for an input with a given property (assume_sink) or which property it removes (assume_sanitize). Name the mechanism, not the CWE.\nPattern: '`<gid>` <mechanism>; therefore <property/consequence>.'",
     "maxLength": 320,
     "type": "string"
    }
   },
   "required": [
    "gid",
    "scope",
    "why",
    "loc",
    "kind",
    "callback_port",
    "passes"
   ],
   "type": "object"
  },
  "AssumePropagate": {
   "additionalProperties": false,
   "description": "Calling `gid` copies taint from `in_port` to `out_port` unchanged\n(identity/wrapper/format functions). No CWEs added or removed.",
   "properties": {
    "gid": {
     "description": "@GID",
     "examples": [
      "java:com.example#Foo.bar",
      "python:os#system",
      "go:net/http#Client.Do",
      "c:libc#system",
      "rust:std::process#Command.new",
      "js:src/app.js#handler"
     ],
     "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
     "type": "string"
    },
    "in_port": {
     "description": "Port on a function's boundary. Forms:\n  arg[0]  arg[*]  arg[1..]      positional param(s)\n  ret  ret[1]                   return value(s)\n  self                          receiver\n  arg[0].fieldName              access path into a param\n  arg[1].param[0]  arg[1].ret   higher-order: the callback's own param/ret\n  <- arg[0]     -> ret          direction prefix (sink / source)\n  arg[0] -> ret                 propagate spec",
     "maxLength": 128,
     "minLength": 3,
     "pattern": "^(<-\\s*|->\\s*)?(arg\\[(\\d+|\\*|\\d+\\.\\.)\\](\\.param\\[\\d+\\]|\\.ret)?|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*(\\s*(<-|->)\\s*(arg\\[(\\d+|\\*|\\d+\\.\\.)\\]|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*)?$",
     "type": "string"
    },
    "kind": {
     "const": "assume_propagate",
     "type": "string"
    },
    "loc": {
     "description": "@LINE",
     "type": "integer"
    },
    "out_port": {
     "description": "Port on a function's boundary. Forms:\n  arg[0]  arg[*]  arg[1..]      positional param(s)\n  ret  ret[1]                   return value(s)\n  self                          receiver\n  arg[0].fieldName              access path into a param\n  arg[1].param[0]  arg[1].ret   higher-order: the callback's own param/ret\n  <- arg[0]     -> ret          direction prefix (sink / source)\n  arg[0] -> ret                 propagate spec",
     "maxLength": 128,
     "minLength": 3,
     "pattern": "^(<-\\s*|->\\s*)?(arg\\[(\\d+|\\*|\\d+\\.\\.)\\](\\.param\\[\\d+\\]|\\.ret)?|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*(\\s*(<-|->)\\s*(arg\\[(\\d+|\\*|\\d+\\.\\.)\\]|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*)?$",
     "type": "string"
    },
    "scope": {
     "description": "`agnostic` = a fact about a third-party or standard-library API, true in EVERY project that calls it (`org.slf4j#Logger.info` writes its arguments to the log everywhere). `project` = about this codebase's own abstractions, or a behaviour you inferred from how THIS project uses a dependency. Leave empty if unsure: a wrong `agnostic` rule is inherited by projects that never saw it derived.",
     "enum": [
      "",
      "agnostic",
      "project"
     ],
     "type": "string"
    },
    "why": {
     "description": "1-2 sentences: (a) what this API does at runtime, (b) which security-relevant PROPERTY that gives its output (for assume_source) or which consequence follows for an input with a given property (assume_sink) or which property it removes (assume_sanitize). Name the mechanism, not the CWE.\nPattern: '`<gid>` <mechanism>; therefore <property/consequence>.'",
     "maxLength": 320,
     "type": "string"
    }
   },
   "required": [
    "gid",
    "scope",
    "why",
    "loc",
    "kind",
    "in_port",
    "out_port"
   ],
   "type": "object"
  },
  "AssumeSanitize": {
   "additionalProperties": false,
   "description": "Calling `gid` (or passing a `narrow ... by gid` guard) REMOVES `removes`\nCWEs from `in_port`'s taint set; the cleaned value comes out on `out_port`.",
   "properties": {
    "gid": {
     "description": "@GID",
     "examples": [
      "java:com.example#Foo.bar",
      "python:os#system",
      "go:net/http#Client.Do",
      "c:libc#system",
      "rust:std::process#Command.new",
      "js:src/app.js#handler"
     ],
     "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
     "type": "string"
    },
    "in_port": {
     "description": "Port on a function's boundary. Forms:\n  arg[0]  arg[*]  arg[1..]      positional param(s)\n  ret  ret[1]                   return value(s)\n  self                          receiver\n  arg[0].fieldName              access path into a param\n  arg[1].param[0]  arg[1].ret   higher-order: the callback's own param/ret\n  <- arg[0]     -> ret          direction prefix (sink / source)\n  arg[0] -> ret                 propagate spec",
     "maxLength": 128,
     "minLength": 3,
     "pattern": "^(<-\\s*|->\\s*)?(arg\\[(\\d+|\\*|\\d+\\.\\.)\\](\\.param\\[\\d+\\]|\\.ret)?|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*(\\s*(<-|->)\\s*(arg\\[(\\d+|\\*|\\d+\\.\\.)\\]|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*)?$",
     "type": "string"
    },
    "kind": {
     "const": "assume_sanitize",
     "type": "string"
    },
    "loc": {
     "description": "@LINE",
     "type": "integer"
    },
    "out_port": {
     "description": "Port on a function's boundary. Forms:\n  arg[0]  arg[*]  arg[1..]      positional param(s)\n  ret  ret[1]                   return value(s)\n  self                          receiver\n  arg[0].fieldName              access path into a param\n  arg[1].param[0]  arg[1].ret   higher-order: the callback's own param/ret\n  <- arg[0]     -> ret          direction prefix (sink / source)\n  arg[0] -> ret                 propagate spec",
     "maxLength": 128,
     "minLength": 3,
     "pattern": "^(<-\\s*|->\\s*)?(arg\\[(\\d+|\\*|\\d+\\.\\.)\\](\\.param\\[\\d+\\]|\\.ret)?|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*(\\s*(<-|->)\\s*(arg\\[(\\d+|\\*|\\d+\\.\\.)\\]|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*)?$",
     "type": "string"
    },
    "removes": {
     "description": "Analyzer computes taint(out_port) = taint(in_port) \\ removes at every call/narrow.",
     "items": {
      "description": "The CWE you would cite in a finding, most specific first.",
      "maxLength": 9,
      "minLength": 5,
      "pattern": "^CWE-\\d{1,5}$",
      "type": "string"
     },
     "maxItems": 16,
     "minItems": 1,
     "type": "array"
    },
    "scope": {
     "description": "`agnostic` = a fact about a third-party or standard-library API, true in EVERY project that calls it (`org.slf4j#Logger.info` writes its arguments to the log everywhere). `project` = about this codebase's own abstractions, or a behaviour you inferred from how THIS project uses a dependency. Leave empty if unsure: a wrong `agnostic` rule is inherited by projects that never saw it derived.",
     "enum": [
      "",
      "agnostic",
      "project"
     ],
     "type": "string"
    },
    "why": {
     "description": "1-2 sentences: (a) what this API does at runtime, (b) which security-relevant PROPERTY that gives its output (for assume_source) or which consequence follows for an input with a given property (assume_sink) or which property it removes (assume_sanitize). Name the mechanism, not the CWE.\nPattern: '`<gid>` <mechanism>; therefore <property/consequence>.'",
     "maxLength": 320,
     "type": "string"
    }
   },
   "required": [
    "gid",
    "scope",
    "why",
    "loc",
    "kind",
    "in_port",
    "out_port",
    "removes"
   ],
   "type": "object"
  },
  "AssumeSink": {
   "additionalProperties": false,
   "description": "Calling `gid` with a tainted value on `in_port` FIRES `cwe` (if that CWE\nis in the value's set). Also covers configsinks: storing a matching constant\ninto `gid`'s port fires `cwe` -- use `cond` to match the constant value.",
   "properties": {
    "cond": {
     "description": "Optional predicate on the arg VALUE (for config-field sinks that only fire on a specific constant). JSON: {\"eq\":\"true\"} etc.",
     "maxLength": 256,
     "type": "string"
    },
    "cwe": {
     "description": "Analyzer checks `cwe in taint(in_port)` at every call to gid.",
     "maxLength": 9,
     "minLength": 5,
     "pattern": "^CWE-\\d{1,5}$",
     "type": "string"
    },
    "gid": {
     "description": "@GID",
     "examples": [
      "java:com.example#Foo.bar",
      "python:os#system",
      "go:net/http#Client.Do",
      "c:libc#system",
      "rust:std::process#Command.new",
      "js:src/app.js#handler"
     ],
     "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
     "type": "string"
    },
    "in_port": {
     "description": "Which arg/field receives the dangerous value: `arg[0]`, `arg[*]`, `self.field`",
     "examples": [
      "arg[0]",
      "arg[*]"
     ],
     "maxLength": 128,
     "minLength": 3,
     "pattern": "^(<-\\s*|->\\s*)?(arg\\[(\\d+|\\*|\\d+\\.\\.)\\](\\.param\\[\\d+\\]|\\.ret)?|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*(\\s*(<-|->)\\s*(arg\\[(\\d+|\\*|\\d+\\.\\.)\\]|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*)?$",
     "type": "string"
    },
    "kind": {
     "const": "assume_sink",
     "type": "string"
    },
    "loc": {
     "description": "@LINE",
     "type": "integer"
    },
    "scope": {
     "description": "`agnostic` = a fact about a third-party or standard-library API, true in EVERY project that calls it (`org.slf4j#Logger.info` writes its arguments to the log everywhere). `project` = about this codebase's own abstractions, or a behaviour you inferred from how THIS project uses a dependency. Leave empty if unsure: a wrong `agnostic` rule is inherited by projects that never saw it derived.",
     "enum": [
      "",
      "agnostic",
      "project"
     ],
     "type": "string"
    },
    "why": {
     "description": "1-2 sentences: (a) what this API does at runtime, (b) which security-relevant PROPERTY that gives its output (for assume_source) or which consequence follows for an input with a given property (assume_sink) or which property it removes (assume_sanitize). Name the mechanism, not the CWE.\nPattern: '`<gid>` <mechanism>; therefore <property/consequence>.'",
     "maxLength": 320,
     "type": "string"
    }
   },
   "required": [
    "gid",
    "scope",
    "why",
    "loc",
    "kind",
    "in_port",
    "cwe",
    "cond"
   ],
   "type": "object"
  },
  "AssumeSource": {
   "additionalProperties": false,
   "description": "Calling `gid` PRODUCES tainted data on `out_port` carrying `cwes`.",
   "properties": {
    "cwes": {
     "description": "Analyzer seeds taint(out_port) with this set at every call to gid.",
     "items": {
      "description": "The CWE you would cite in a finding, most specific first.",
      "maxLength": 9,
      "minLength": 5,
      "pattern": "^CWE-\\d{1,5}$",
      "type": "string"
     },
     "maxItems": 32,
     "minItems": 1,
     "type": "array"
    },
    "gid": {
     "description": "@GID",
     "examples": [
      "java:com.example#Foo.bar",
      "python:os#system",
      "go:net/http#Client.Do",
      "c:libc#system",
      "rust:std::process#Command.new",
      "js:src/app.js#handler"
     ],
     "pattern": "^[a-z][a-z0-9_+]*:[A-Za-z0-9_./\\-@:]+(#[A-Za-z_~<][A-Za-z0-9_.<>~@:!/]*)?$",
     "type": "string"
    },
    "kind": {
     "const": "assume_source",
     "type": "string"
    },
    "loc": {
     "description": "@LINE",
     "type": "integer"
    },
    "out_port": {
     "description": "Where the tainted value comes out: `ret`, `ret[1]`, `arg[0].f` (mutation)",
     "examples": [
      "ret",
      "arg[0].body"
     ],
     "maxLength": 128,
     "minLength": 3,
     "pattern": "^(<-\\s*|->\\s*)?(arg\\[(\\d+|\\*|\\d+\\.\\.)\\](\\.param\\[\\d+\\]|\\.ret)?|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*(\\s*(<-|->)\\s*(arg\\[(\\d+|\\*|\\d+\\.\\.)\\]|ret(\\[\\d+\\])?|self)(\\.[A-Za-z_*][A-Za-z0-9_]*)*)?$",
     "type": "string"
    },
    "scope": {
     "description": "`agnostic` = a fact about a third-party or standard-library API, true in EVERY project that calls it (`org.slf4j#Logger.info` writes its arguments to the log everywhere). `project` = about this codebase's own abstractions, or a behaviour you inferred from how THIS project uses a dependency. Leave empty if unsure: a wrong `agnostic` rule is inherited by projects that never saw it derived.",
     "enum": [
      "",
      "agnostic",
      "project"
     ],
     "type": "string"
    },
    "why": {
     "description": "1-2 sentences: (a) what this API does at runtime, (b) which security-relevant PROPERTY that gives its output (for assume_source) or which consequence follows for an input with a given property (assume_sink) or which property it removes (assume_sanitize). Name the mechanism, not the CWE.\nPattern: '`<gid>` <mechanism>; therefore <property/consequence>.'",
     "maxLength": 320,
     "type": "string"
    }
   },
   "required": [
    "gid",
    "scope",
    "why",
    "loc",
    "kind",
    "out_port",
    "cwes"
   ],
   "type": "object"
  },
  "ConfigFinding": {
   "additionalProperties": false,
   "description": "A dangerous literal value in source. Self-contained: BOTH source and\nsink at the same location. Emitted by the config-agent.",
   "properties": {
    "cwe": {
     "description": "Most-specific MITRE CWE this value+setting triggers.",
     "maxLength": 9,
     "minLength": 5,
     "pattern": "^CWE-\\d{1,5}$",
     "type": "string"
    },
    "file": {
     "description": "Repo-relative source path (the one in the listing's header), or `<synthetic>` for [model] stubs.",
     "maxLength": 512,
     "minLength": 1,
     "pattern": "^(<[a-z]+>|[A-Za-z0-9_./\\-]+)$",
     "type": "string"
    },
    "line": {
     "minimum": 1,
     "type": "integer"
    },
    "setting": {
     "description": "What the value configures: the field/key/flag/arg name (e.g. 'gpgcheck', 'InsecureSkipVerify', 'runAsUser', '--insecure', 'verify=', 'privileged').",
     "maxLength": 200,
     "type": "string"
    },
    "snippet": {
     "maxLength": 200,
     "type": "string"
    },
    "value": {
     "description": "The dangerous literal as it appears.",
     "maxLength": 200,
     "type": "string"
    },
    "why": {
     "description": "1-2 sentences: (a) what behaviour this setting=value enables or disables (the mechanism), (b) the concrete consequence -- what becomes possible/exposed/weakened as a result.\nPattern: '`<setting>=<value>` <mechanism>; therefore <consequence>.'",
     "maxLength": 320,
     "type": "string"
    }
   },
   "required": [
    "file",
    "line",
    "value",
    "setting",
    "cwe",
    "why",
    "snippet"
   ],
   "type": "object"
  },
  "ConfigFindings": {
   "additionalProperties": false,
   "description": "Literals whose VALUE is itself the weakness -- the constant IS the problem,\nnot something that flows.\n\nTwo-step test per candidate token:\n  1. is it lexically constant here (a literal/keyword/flag a reader knows the\n     value of from this line alone)?\n  2. would replacing THAT token with a safe value fix the issue at this line,\n     with no other change?\nBoth yes -> emit. One entry per (setting, value) instance. An empty list is\nvalid and common.",
   "properties": {
    "findings": {
     "items": {
      "$ref": "#/$defs/ConfigFinding"
     },
     "maxItems": 48,
     "type": "array"
    }
   },
   "required": [
    "findings"
   ],
   "type": "object"
  },
  "Requires": {
   "additionalProperties": false,
   "description": "Call `<label>` requires authorization. Fires if reached from an entry without\na sanitize removing `cwe` on the path.",
   "properties": {
    "call": {
     "description": "Id of a call within this fn: the label printed under its line -- the bare line number, plus a letter when a line holds several (52, 53a, 53b).",
     "maxLength": 8,
     "pattern": "^(?:c\\d+|\\d+[a-z]?)$",
     "type": "string"
    },
    "cwe": {
     "description": "The CWE you would cite in a finding, most specific first.",
     "maxLength": 9,
     "minLength": 5,
     "pattern": "^CWE-\\d{1,5}$",
     "type": "string"
    },
    "loc": {
     "description": "@LINE",
     "type": "integer"
    },
    "why": {
     "description": "1-2 sentences: (a) the concrete operation and the protected resource it acts on, (b) what precondition it assumes (authorization, ownership, authentication, rate-limit) and what happens if reached without that precondition holding.\nPattern: '`<call>` <effect on resource>. Reached without <precondition>, a caller can <consequence>.'",
     "maxLength": 320,
     "type": "string"
    }
   },
   "required": [
    "call",
    "why",
    "cwe",
    "loc"
   ],
   "type": "object"
  },
  "Sanitize": {
   "additionalProperties": false,
   "description": "Call `<label>` removes `removes` CWEs on the path through it.",
   "properties": {
    "call": {
     "description": "Id of a call within this fn: the label printed under its line -- the bare line number, plus a letter when a line holds several (52, 53a, 53b).",
     "maxLength": 8,
     "pattern": "^(?:c\\d+|\\d+[a-z]?)$",
     "type": "string"
    },
    "loc": {
     "description": "@LINE",
     "type": "integer"
    },
    "removes": {
     "items": {
      "description": "The CWE you would cite in a finding, most specific first.",
      "maxLength": 9,
      "minLength": 5,
      "pattern": "^CWE-\\d{1,5}$",
      "type": "string"
     },
     "maxItems": 16,
     "minItems": 1,
     "type": "array"
    },
    "why": {
     "description": "1-2 sentences: (a) what transformation/check this call performs -- the mechanism as written (`escape*`, `validate*`, `hasRole`, `normalize`, `hash`), (b) which PROPERTY it removes or which precondition it establishes, so the downstream operation is safe.\nPattern: '`<call>` <mechanism>, so the value no longer has <property> / the caller is proven to have <precondition>.'",
     "maxLength": 320,
     "type": "string"
    }
   },
   "required": [
    "call",
    "why",
    "removes",
    "loc"
   ],
   "type": "object"
  },
  "Sink": {
   "additionalProperties": false,
   "description": "A port of call `<label>` that is dangerous if what reaches it is tainted.",
   "properties": {
    "cwes": {
     "description": "Every CWE id this operation can realize depending on what flows in. Do not stop at the first -- enumerate exhaustively. An unlisted CWE cannot fire; an extra one is filtered by the analyzer, so err toward listing more.",
     "items": {
      "description": "The CWE you would cite in a finding, most specific first.",
      "maxLength": 9,
      "minLength": 5,
      "pattern": "^CWE-\\d{1,5}$",
      "type": "string"
     },
     "minItems": 1,
     "type": "array"
    },
    "loc": {
     "description": "@LINE",
     "type": "integer"
    },
    "port": {
     "description": "Which port is dangerous: usually <label>.arg[i].",
     "maxLength": 512,
     "pattern": "^(param\\[\\d+\\]|\\$ret(\\[\\d+\\])?|\\$exc|(?:c\\d+|\\d+[a-z]?)\\.(arg\\[\\d+\\]|ret(\\[\\d+\\])?)|@(env|file|db|queue|mem|cache|secret|config|cloud|k8s|mailbox|tfvar):[^\\s]+)(\\.[\\w*]+)*$",
     "type": "string"
    },
    "why": {
     "description": "Evidence a reviewer can verify, not a label: name the identifier or call as written in code, state the operation and what goes wrong if the value is tainted, and state the implication. 2-3 sentences.",
     "maxLength": 320,
     "type": "string"
    }
   },
   "required": [
    "port",
    "why",
    "cwes",
    "loc"
   ],
   "type": "object"
  },
  "Source": {
   "additionalProperties": false,
   "description": "A port where a security-relevant property ORIGINATES via a mechanism you\ncan name AT THIS PORT, independent of what any caller passes.\n\nOrigination test: can you name a mechanism at this port that establishes the\nproperty regardless of the call site? \"Some caller might pass one\" fails the\ntest -- that is arrival, and the analyzer already models arrival through\ninterprocedural summaries, so a Source there yields a tautological finding\nand discards the real origin.\n\nPasses: a boundary read's `<label>.ret`; `param[i]` ONLY when something outside\nthis codebase invokes the fn (framework dispatch, CLI entry, consumer,\nplugin/SPI callback, native upcall); `param[0].field` or `@global` holding\nloader-populated state; the process environment and argv of a script or\nentry point (`@env:NAME`, `@env:*`) -- those are filled from outside the\ncodebase, so they ORIGINATE rather than arrive, and a script whose whole job\nis to read them has no other origin to name; `<label>.ret` of a weak or hardcoded\nconstruction.\n\nFails: `param[i]` of an ordinary function; `<label>.ret` of an in-repo function\n(its own summary carries the origin out).",
   "properties": {
    "cwes": {
     "description": "Every CWE id that applies to this data. Do not stop at the first -- enumerate exhaustively. An unlisted CWE cannot fire; an extra one is filtered by the analyzer, so err toward listing more.",
     "items": {
      "description": "The CWE you would cite in a finding, most specific first.",
      "maxLength": 9,
      "minLength": 5,
      "pattern": "^CWE-\\d{1,5}$",
      "type": "string"
     },
     "minItems": 1,
     "type": "array"
    },
    "loc": {
     "description": "@LINE",
     "type": "integer"
    },
    "port": {
     "description": "The port where the property originates (see class docstring for the origination test). NOT a port where it might arrive from a caller.",
     "maxLength": 512,
     "pattern": "^(param\\[\\d+\\]|\\$ret(\\[\\d+\\])?|\\$exc|(?:c\\d+|\\d+[a-z]?)\\.(arg\\[\\d+\\]|ret(\\[\\d+\\])?)|@(env|file|db|queue|mem|cache|secret|config|cloud|k8s|mailbox|tfvar):[^\\s]+)(\\.[\\w*]+)*$",
     "type": "string"
    },
    "why": {
     "description": "Evidence a reviewer can verify, not a label: name the identifier or call as written in code, state the property and where it comes from, and state the implication. 2-3 sentences.",
     "maxLength": 320,
     "type": "string"
    }
   },
   "required": [
    "port",
    "why",
    "cwes",
    "loc"
   ],
   "type": "object"
  }
 },
 "additionalProperties": false,
 "description": "One judgment pass over a file: taint assertions plus dangerous literals.",
 "properties": {
  "asserts": {
   "$ref": "#/$defs/AssertUnit"
  },
  "config": {
   "$ref": "#/$defs/ConfigFindings"
  }
 },
 "required": [
  "asserts",
  "config"
 ],
 "type": "object"
}
```

<!-- END GENERATED wire format -->
