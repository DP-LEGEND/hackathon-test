import { ArrowDown, ArrowUpRight, Blocks, House, Info, Layers2, Settings2, UserRound } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { SectionHeader } from "@/components/layout/section-header";
import { StatePreview } from "@/components/shared/state-preview";
import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <AppShell
      appName="Your app"
      headerTitle={<span className="flex items-center gap-2 text-muted-foreground"><span>Workspace</span><span aria-hidden="true" className="mx-1 text-border">/</span><span className="text-foreground">Home</span></span>}
      navigation={[
        { label: "Home", href: "/", icon: <House aria-hidden="true" />, active: true },
        { label: "Components", href: "#components", icon: <Blocks aria-hidden="true" /> },
      ]}
      secondaryNavigation={[
        { label: "About this starter", href: "#shell-details", icon: <Info aria-hidden="true" /> },
      ]}
      userArea={
        <div className="flex items-center gap-2 px-2 py-1">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-full border bg-background text-muted-foreground"><UserRound aria-hidden="true" className="size-4" /></span>
          <div className="min-w-0 flex-1"><p className="text-xs font-medium">Your workspace</p><p className="mt-0.5 text-xs text-muted-foreground">Make it your own</p></div>
          <Button nativeButton={false} variant="ghost" size="icon" className="size-11" render={<a href="#shell-details" />} aria-label="Workspace configuration"><Settings2 aria-hidden="true" /></Button>
        </div>
      }
    >
      <div className="space-y-12 sm:space-y-14">
        <PageHeader
          eyebrow="A place to begin"
          title="Make room for your next idea."
          description="A simple foundation for whatever you’re building. Bring your purpose, connect your tools, and make it yours."
          actions={<Button nativeButton={false} className="h-10 px-4" render={<a href="#components" />}>Explore components <ArrowDown aria-hidden="true" /></Button>}
        />
        <section id="components" aria-labelledby="components-title" className="scroll-mt-8 space-y-5">
          <SectionHeader id="components-title" title="Your starting point" description="One flexible space. Thoughtful defaults for every state." actions={<span className="rounded-md border px-2 py-1 text-xs text-muted-foreground">UI shell preview</span>} />
          <StatePreview />
        </section>
        <section id="shell-details" aria-labelledby="details-title" className="scroll-mt-8 border-t pt-8">
          <SectionHeader id="details-title" title="A foundation, not a finished product" description="Keep the structure. Shape the experience around your users." />
          <div className="mt-7 grid gap-7 sm:grid-cols-3 sm:gap-8">
            {[
              { icon: Layers2, title: "Adapt the shell", description: "Add your name, navigation, and workspace controls. The layout takes care of the rest." },
              { icon: Blocks, title: "Build with consistency", description: "Compose pages from shared headers, state patterns, and the existing UI primitives." },
              { icon: ArrowUpRight, title: "Focus on your idea", description: "Replace this preview with your core experience. No product assumptions to work around." },
            ].map(({ icon: Icon, title, description }) => (
              <div key={title} className="min-w-0"><Icon aria-hidden="true" className="mb-3 size-4 text-muted-foreground" /><h3 className="text-sm font-medium">{title}</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p></div>
            ))}
          </div>
        </section>
        <footer className="flex flex-wrap justify-between gap-2 border-t pt-5 text-xs text-muted-foreground"><span>Your app. Your direction.</span><span>Built to be made your own.</span></footer>
      </div>
    </AppShell>
  );
}
