# /upload

"Try your own swing": one clip in, then the new swing opens in `/ghost?swing=<id>` at the coach's call.

| File | Job |
|---|---|
| `upload-form.tsx` | The flow: clip, settings, send, progress, errors, then open the swing |
| `clip-drop.tsx` | Drag and drop (anywhere on the page) or pick a video, with a preview |
| `clip-settings.tsx` | Optional hitting hand, stroke and slowdown. Auto lets the service decide |
| `extra-inputs.tsx` | Optional second camera angle (with "Second clip offset (s)") and wrist sensor CSV |
| `progress-panel.tsx` | Real upload progress, then the steps while the service works |
| `process-clip.ts` | `POST /api/process` and what each answer means |

## The request

Multipart `POST /api/process` with `file`, plus `hand` (`R`/`L`), `stroke` (`forehand`/`backhand`) and `slowdown` (`1`/`4`/`8`) when they aren't Auto. Auto fields are left out. The catch-all proxy (`app/api/[...path]/route.ts`) forwards it to `POST /process` in `services/pipeline/server.py` (PR #41). The service answers once, after pose, coach and ghost are saved, with `swingId`. The page then opens `/ghost?swing=<swingId>`.

With a second camera angle or a wrist sensor CSV, the same request goes to `POST /api/process/multi` instead (Dev's route, same answer as `/process`), with `video_a`, `video_b`, `sensor_csv`, `slowdown_a`, `slowdown_b` and `offset_b_s`. Fields with nothing in them are left out; both angles use the one Slowdown setting, and the offset is only sent with a second angle. Without either extra, the request is exactly the single-clip one above. If the answer has `warnings` (a list of strings), the page stays on the "ready" panel and lists them, with **Open it in Ghost** to go on; without warnings it opens the swing straight away, as before. A 404 or 405 from `/process/multi` says the service can't take a second angle or sensor file yet.

The extra zones take their own drops (a file dropped on them never replaces the main video) and open their pickers from an input made on demand, so the page keeps a single `<input type=file>`.

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
