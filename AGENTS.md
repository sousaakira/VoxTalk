# VoxTalk

Desktop voice-to-text: global hotkey activates the mic.

**Default STT:** local Parakeet TDT v3 via sherpa-onnx (same stack as Orca, ~670 MB).  
**Optional:** OpenAI GPT-4o(-mini) Transcribe in Settings.

## MegaBrain (shared project memory — MANDATORY workflow)

This project uses MegaBrain (MCP server `megacoder`, project `VOX`) as shared
long-term memory and backlog. In EVERY session:

0. **Register this session FIRST** — before reading rules, before touching code:
   `brain_register_session` (project `VOX`) with a **custom alias** naming the work
   (compound kebab-case, e.g. `stripe-webhook-retry`) and your runtime session id
   (`sessionId` = the Claude Code session UUID, so `claude --resume <id>` brings you back).
   That alias is your identity: tickets are claimed by it, one session at a time. Re-call it
   every so often to heartbeat, and use the SAME alias whenever you resume.
1. Call `brain_rules` (project `VOX`) and obey every rule it returns.
2. Before building anything, `brain_search` it — a past session likely recorded the answer.
3. Pull work with `brain_ready_tickets` → `brain_ticket_context` (pass your `alias`; this claims
   the ticket). Never work a ticket another live session holds — `brain_list_sessions` shows who.
4. Write knowledge back as you learn (`brain_upsert_nodes`: MEMORY for gotchas, DOC/SUBSYSTEM
   for maps; `brain_add_adr` for decisions). Link with `[[key]]` / `[[TYPE:key]]` wikilinks
   inside the content — they become graph edges automatically.
5. Before finishing, run your final diff through `review_code` (pass `projectRules` from
   `brain_rules`) — a verified multi-lens review — and fix what it confirms.
6. Finish tickets with a FINDING comment (`brain_comment_ticket`) + `brain_transition_ticket`
   (which releases your claim), then `brain_document_feature`. Call `brain_end_session` when
   you stop working so nothing stays locked behind a session nobody is running.
