// MegaBrain SessionStart hook — hands the agent its REAL Claude Code session id so
// brain_register_session can map a custom alias to a session that actually resumes.
// Fails open: any problem here prints nothing and the session starts normally.
import { readFileSync } from 'node:fs';

let payload = {};
try {
  payload = JSON.parse(readFileSync(0, 'utf8') || '{}');
} catch {}

const id = typeof payload.session_id === 'string' ? payload.session_id : '';
const cwd = typeof payload.cwd === 'string' ? payload.cwd : process.cwd();
const project = 'VOX';

const context = [
  'MegaBrain — register this session BEFORE any other work (project ' + project + ').',
  id
    ? 'Your Claude Code session id is ' + id + ' — resume it with: claude --resume ' + id
    : 'Your session id was not in the hook payload. Recover it from the UUID segment of your own '
      + 'scratchpad/temp directory path (that IS the session id), or the newest .jsonl filename in '
      + 'the transcripts directory, or ask the user to run /status.',
  'Call brain_register_session with: project "' + project + '", kind "CLAUDE_CODE", sessionId "' + id + '",',
  'cwd "' + cwd + '", and a CUSTOM alias in compound kebab-case naming the work you are about to do',
  '(e.g. "stripe-webhook-retry"). Generic aliases are rejected. Reuse the SAME alias when you resume.',
  'Then take work with brain_ticket_context (pass that alias — it claims the ticket). Never work a',
  'ticket another live session holds; brain_list_sessions shows who holds what.',
].join('\n');

process.stdout.write(
  JSON.stringify({ hookSpecificOutput: { hookEventName: 'SessionStart', additionalContext: context } }),
);
