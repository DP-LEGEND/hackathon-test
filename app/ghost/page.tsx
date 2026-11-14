// Ghost demo screen. Owner: Teammate A.
// Placeholder only. This becomes the 3D replay: your swing (orange) beside the
// ghost (cyan), the 3D court with two PREDICTED ball paths, and the coach caption.
// Build against mock data first; data shapes are in lib/ghost/types.ts.

export default function GhostPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-3 p-6">
      <p className="text-sm text-muted-foreground">Ghost · placeholder</p>
      <h1 className="text-3xl font-semibold tracking-tight">See the shot before you practise it.</h1>
      <p className="text-muted-foreground">
        The 3D swing replay, ghost overlay and predicted ball flight will appear here.
      </p>
    </main>
  );
}
