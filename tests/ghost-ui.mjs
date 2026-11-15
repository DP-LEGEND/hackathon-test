// Run against an existing server: node tests/ghost-ui.mjs
// Transport fixtures exercise error/cancel/retry UI; they do not claim a live video analysis.
import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
const baseURL = process.env.GHOST_TEST_URL || 'http://localhost:3000';
const output = `build/browser-tests/design-review/ghost/${process.env.GHOST_REVIEW_ROUND || 'round-1'}`;
await mkdir(output, { recursive: true });
assert.equal(execFileSync('git', ['diff', 'origin/main', '--', 'app/ghost', 'app/upload', 'public/swings', ':(exclude)app/ghost/page.tsx', ':(exclude)app/ghost/ghost-stage.tsx', ':(exclude)app/ghost/wrist-panel.tsx'], { encoding: 'utf8' }).trim(), '', 'Existing journeys and saved numbers must be unchanged from main');
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const results = [];
async function capture(page, name) {
  await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map(i => { i.loading='eager'; return i.decode().catch(() => {}); })); });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${name}: overflow`);
  await page.screenshot({ fullPage: true, animations: 'disabled', path: `${output}/${name}.png`, style: 'nextjs-portal { visibility:hidden!important; }' });
}
try {
  for (const [width,height] of [[1440,900],[768,1024],[390,844]]) {
    const context = await browser.newContext({ baseURL, viewport:{width,height}, reducedMotion:'reduce' });
    const page=await context.newPage();
    const errors=[]; const remoteFonts=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{ if (r.resourceType()==='font' && new URL(r.url()).origin!==new URL(baseURL).origin) remoteFonts.push(r.url()); });
    try {
      await page.goto('/');
      await expect(page.getByRole('heading',{name:'See your swing. Find your edge.'})).toBeVisible();
      await expect(page.getByRole('link',{name:'Analyse your swing'})).toHaveAttribute('href','/upload');
      const demoLink=page.getByRole('link',{name:'See the demo',exact:true});
      await expect(demoLink).toHaveAttribute('href','/demo?swing=7178110a0b06-swing-0027');
      await expect(demoLink).toBeInViewport({ratio:1});
      await expect(page.getByRole('link',{name:'Analyse your swing'})).toBeInViewport({ratio:1});
      await expect(page.getByRole('link',{name:/Archive|Log in|^Test$/})).toHaveCount(0);
      await expect(page.locator('main')).not.toContainText(/unavailable|not supplied|not connected|CSV/i);
      await expect(page.locator('.ghost-theme').first()).toHaveCSS('background-color','rgb(11, 15, 18)');
      await capture(page,`${width}-landing`);
      await page.screenshot({path:`${output}/${width}-hero.png`,animations:'disabled',style:'nextjs-portal { visibility:hidden!important; }'});
      const slider=page.getByRole('slider',{name:'Explore the process'});
      await slider.focus(); await slider.press('End'); await expect(slider).toHaveValue('2');
      await expect(page.locator('article[data-active=true]')).toContainText('Predicted shots');
      await capture(page,`${width}-process-selected`);
      if(width===390) {
        assert.ok((await page.getByRole('button',{name:'Menu',exact:true}).boundingBox()).height >= 44, 'Mobile menu has a 44px touch target');
        await page.getByRole('button',{name:'Menu',exact:true}).click();
        await expect(page.getByRole('dialog')).toBeVisible();
        await expect(page.getByRole('dialog').getByRole('link',{name:'Demo',exact:true})).toBeInViewport();
        await expect(page.getByRole('button',{name:'Close',exact:true})).toBeInViewport();
        await capture(page,`${width}-menu`);
        await page.keyboard.press('Escape');
        await expect(page.getByRole('button',{name:'Menu',exact:true})).toBeFocused();
        await page.locator('.ghost-processPanels').evaluate(el=>el.scrollTo({left:0,behavior:'instant'}));
        await expect(slider).toHaveValue('0');
      }
      assert.deepEqual(remoteFonts,[],'Fonts must load from the local app');
      await page.goto('/demo');
      await expect(page.getByRole('button',{name:'Start with the demo swing'})).toBeVisible();
      await page.getByRole('button',{name:'Start with the demo swing'}).click();
      await expect(page.getByRole('heading',{name:"The coach's call",exact:true})).toBeVisible();
      await expect(page.getByRole('button',{name:'Show the ghost',exact:true})).toBeVisible();
      await expect(page.locator('blockquote')).toBeVisible();
      await page.evaluate(()=>document.fonts.ready);
      await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));
      if(width===1440) {
        const canvas=await page.locator('canvas').boundingBox();
        assert.ok(canvas && canvas.y>=0 && canvas.y+canvas.height<=height, 'The complete coach replay canvas fits above the fold');
        await expect(page.locator('figure')).toBeInViewport({ratio:1});
      }
      await capture(page,`${width}-demo`);
      assert.deepEqual(errors,[],'No uncaught errors');
      results.push(`${width}px landing, navigation, stage selection, local fonts and Demo wrapper: PASS`);
      console.log(results.at(-1));
    } finally { await context.close(); }
  }
  const motionContext=await browser.newContext({baseURL,viewport:{width:320,height:844},reducedMotion:'no-preference'});
  try {
    const page=await motionContext.newPage();
    await page.goto('/');
    await expect(page.getByRole('heading',{name:'See your swing. Find your edge.'})).toBeVisible();
    const ghost=page.locator('.ghost-flyingGhost');
    await expect.poll(()=>ghost.evaluate(el=>el.style.transform)).not.toBe('');
    const initial=await ghost.evaluate(el=>el.style.transform);
    await page.evaluate(()=>scrollTo(0,400));
    await expect.poll(()=>ghost.evaluate(el=>el.style.transform)).not.toBe(initial);
    await page.emulateMedia({reducedMotion:'reduce'});
    await expect(ghost).toHaveCSS('transform','none');
    await capture(page,'320-reduced-motion');
    results.push('320px overflow, live scroll motion and reduced-motion alternative: PASS');
    console.log(results.at(-1));
  } finally { await motionContext.close(); }
  const context=await browser.newContext({baseURL,viewport:{width:1440,height:900},reducedMotion:'reduce'});
  try {
    const page=await context.newPage();
    // Optional voice is deliberately skipped; saved cue wording is compared with its source.
    await page.route('**/api/coach/*/voice',r=>r.fulfill({status:404,json:{detail:'No voice in regression fixture'}}));
    const catalogue=JSON.parse(await readFile('public/swings/catalogue.json','utf8'));
    for (const entry of catalogue.swings) {
      await page.goto('/ghost');
      await expect(page.getByRole('button',{name:'1 Pick a swing',exact:true})).toBeVisible();
      await page.getByRole('button',{name:new RegExp(entry.id)}).click();
      await expect(page.getByRole('button',{name:'Show the ghost',exact:true})).toBeVisible();
      await expect(page.locator('canvas')).toHaveCount(1);
      const coach=JSON.parse(await readFile(`public/swings/${entry.coach}`,'utf8'));
      // Main #68 deliberately scopes the backhand's no-fault cue to checks it could perform.
      const expectedCue=entry.stroke==='backhand' ? 'Nothing to fix in what the coach could check.' : coach.cue;
      await expect(page.locator('blockquote')).toContainText(expectedCue);
      const timeline=page.getByRole('slider',{name:'Swing time'});
      await timeline.focus(); await timeline.press('Home'); await timeline.press('ArrowRight');
      const tau=await timeline.inputValue();
      await page.getByRole('button',{name:'Play',exact:true}).click();
      await expect.poll(()=>timeline.inputValue()).not.toBe(tau);
      await page.getByRole('button',{name:'Pause',exact:true}).click();
      await page.getByRole('button',{name:'Show the ghost',exact:true}).click();
      await expect(page.getByRole('button',{name:'Show the court',exact:true})).toBeVisible();
      await page.getByRole('button',{name:'Show the court',exact:true}).click();
      await expect(page.getByRole('button',{name:'Try another swing',exact:true})).toBeVisible();
      await expect(page.getByText('PREDICTED BALL PATHS',{exact:true}).or(page.getByText('PREDICTED BALL PATH',{exact:true}))).toBeVisible();
      await expect(page.locator('blockquote')).toContainText(expectedCue);
      await capture(page,`1440-ghost-${entry.stroke}`);
    }
    results.push('Existing /ghost forehand + backhand: exact step names, current main coach wording, playback, ghost and court/PREDICTED paths: PASS');
    console.log(results.at(-1));
    let reply='failure'; let pending;
    await page.route('**/api/process',async route=>{ if(reply==='pending'){pending=route;return;} await route.fulfill({status:reply==='failure'?422:201,json:reply==='failure'?{detail:'Synthetic recoverable failure'}:{swingId:catalogue.defaultSwing}}); });
    await page.goto('/upload');
    await expect(page.getByRole('button',{name:'Build my ghost'})).toBeDisabled();
    const choose = page.waitForEvent('filechooser');
    await page.getByRole('button',{name:'Choose a video'}).click();
    await (await choose).setFiles({name:'fixture.txt',mimeType:'text/plain',buffer:Buffer.from('invalid')});
    await expect(page.locator('main').getByRole('alert')).toContainText('isn’t a MOV');
    await page.locator('input[type=file]').setInputFiles({name:'fixture.mp4',mimeType:'video/mp4',buffer:Buffer.from('Synthetic transport fixture')});
    await page.getByRole('button',{name:'Build my ghost'}).click();
    await expect(page.locator('main').getByRole('alert')).toContainText('Synthetic recoverable failure');
    await expect(page.getByText('fixture.mp4',{exact:true})).toBeVisible();
    await capture(page,'1440-upload-failure');
    reply='pending'; await page.getByRole('button',{name:'Try again',exact:true}).click();
    await expect.poll(()=>!!pending).toBe(true);
    await expect(page.getByRole('heading',{name:'Working on your swing'})).toBeVisible();
    await page.getByRole('button',{name:/Cancel|Stop waiting/}).click();
    await expect(page.getByRole('button',{name:'Build my ghost'})).toBeEnabled();
    await pending.abort().catch(()=>{});
    reply='success'; await page.getByRole('button',{name:'Build my ghost'}).click();
    await expect(page).toHaveURL(new RegExp('/ghost\\?swing='+catalogue.defaultSwing));
    await expect(page.getByRole('button',{name:'Show the ghost',exact:true})).toBeVisible();
    results.push('Existing /upload: invalid file, preserved valid file, Try again, processing, cancellation, success navigation: PASS (transport fixtures)');
    console.log(results.at(-1));
  } finally { await context.close(); }
} finally { await writeFile(`${output}/results.json`,JSON.stringify({browser:browser.version(),baseURL,results},null,2));await browser.close(); }
