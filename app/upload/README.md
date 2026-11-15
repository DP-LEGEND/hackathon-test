# /upload

"Try your own swing": one clip in, then the new swing opens in `/ghost?swing=<id>` at the coach's call.

| File | Job |
|---|---|
| `upload-form.tsx` | The flow: clip, settings, send, progress, errors, then open the swing |
| `clip-drop.tsx` | Drag and drop (anywhere on the page) or pick a video, with a preview |
| `clip-settings.tsx` | Optional hitting hand, stroke and slowdown. Auto lets the service decide |
| `progress-panel.tsx` | Real upload progress, then the steps while the service works |
| `process-clip.ts` | `POST /api/process` and what each answer means |

## The request

Multipart `POST /api/process` with `file`, plus `hand` (`R`/`L`), `stroke` (`forehand`/`backhand`) and `slowdown` (`1`/`4`/`8`) when they aren't Auto. Auto fields are left out. The catch-all proxy (`app/api/[...path]/route.ts`) forwards it to `POST /process` in `services/pipeline/server.py` (PR #41). The service answers once, after pose, coach and ghost are saved, with `swingId`. The page then opens `/ghost?swing=<swingId>`.

Upload progress is real (XMLHttpRequest). The service doesn't report its steps, so "Finding your swing… Measuring… Building your ghost…" move on a timer after the upload, and the panel says they're a rough guide.

Choosing or dropping a file the page can't use clears the clip chosen before it, so **Build my ghost** can't send the old clip; it stays disabled until a valid one is chosen. Leaving the page cancels an upload in progress. Next keeps the page alive in the background, so each visit mounts a new form: coming back always starts fresh, never on an old progress or "done" state.

| Answer | The page shows |
|---|---|
| 201 | Opens the swing in `/ghost` |
| 429 | "A clip is already processing" |
| 413, or a file over 250 MB before it's sent | "Clip too large" |
| 502 soon after the upload | The service isn't running, with the command to start it |
| 504, or a 502 long after the upload (the proxy's timeout) | Still processing: the swing should appear in `/ghost`'s list |
| 404 or 405 | The running service has no upload route yet (it predates PR #41) |
| Anything else (e.g. 422 "No fully tracked swing found…") | The server's message and a slowdown suggestion |

The 250 MB limit and the accepted extensions (MOV, MP4, M4V, AVI) mirror `server.py`.

## Known limit: the proxy's timeout

The catch-all proxy (Dev's file) stops waiting for the service after a fixed time, and processing a clip on CPU can take longer, as `services/pipeline/README.md` warns. A long clip then ends in the "still processing" message, although the service carries on and saves the swing. The page treats a 502 that arrives 25 s or more after the upload finished as that timeout, so it doesn't depend on the proxy's exact wait, as long as that wait is over 25 s. Since Dev's #66 the proxy answers its timeout with 504 instead, and the page always treats a 504 as still processing. The fix for long clips is a longer timeout for `process` in the proxy.
