// Run against an existing local server: node tests/shell-upload.mjs
// Transport fixtures verify states; a real clip is checked separately through the live service.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { chromium, expect } from '@playwright/test';

const baseURL=process.env.GHOST_TEST_URL || 'http://localhost:3000';
const output=`build/browser-tests/design-review/shell-upload/${process.env.GHOST_REVIEW_ROUND || 'round-1'}`;
await mkdir(output,{recursive:true});
assert.equal(execFileSync('git',['diff','origin/main','--','app/ghost','components/ghost','public/swings','app/upload/process-clip.ts',':(exclude)components/ghost/ghost.css',':(exclude)components/ghost/landing.tsx'],{encoding:'utf8'}).trim(),'','Protected replay and upload transport remain unchanged');
const browser=await chromium.launch({channel:'msedge',headless:true});
const results=[];
async function capture(page,name) {
  await page.evaluate(async()=>{
    await document.fonts.ready;
    await Promise.all([...document.images].map(i=>{
      i.loading='eager';
      return i.decode().catch(()=>{});
    }));
  });
  await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${name}: no page overflow`);
  await page.screenshot({path:`${output}/${name}.png`,fullPage:true,animations:'disabled'});
}
async function shell(page,path) {
  await expect(page.locator('.site-header')).toHaveCount(1);
  await expect(page.locator('.site-footer')).toHaveCount(1);
  await expect(page.locator('main:visible')).toHaveCount(1);
  await expect(page.locator('.site-shell')).toHaveCSS('background-color','rgb(11, 15, 18)');
  const selected=path==='/ghost'?'/demo':path;
  await expect(page.locator(`.site-nav a[href="${selected}"]`)).toHaveAttribute('aria-current','page');
  await expect(page.locator('.site-nav')).toHaveText('HomeDemoTry your swing');
}
try {
  for(const [width,height] of [[1440,900],[768,1024],[390,844]]) {
    if(process.env.SHELL_TEST_WIDTH && width!==Number(process.env.SHELL_TEST_WIDTH)) continue;
    const context=await browser.newContext({baseURL,viewport:{width,height},reducedMotion:'reduce'});
    context.setDefaultTimeout(15000);
    context.setDefaultNavigationTimeout(30000);
    const page=await context.newPage(); const errors=[]; const externalFonts=[];
    // Routing holds the request before browser upload events. Expose this test-only XHR so
    // the fixture can explicitly advance from uploading to processing without a real server.
    await page.addInitScript(()=>{
      const NativeXHR=window.XMLHttpRequest;
      window.XMLHttpRequest=class extends NativeXHR {
        send(body) { window.__shellUploadXhr=this; return super.send(body); }
      };
    });
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(r.resourceType()==='font' && new URL(r.url()).origin!==new URL(baseURL).origin) externalFonts.push(r.url());});
    try {
      await page.goto('/upload');
      await expect(page.getByRole('button',{name:'Choose a video'})).toBeVisible();
      await shell(page,'/upload');
      await expect(page.getByRole('button',{name:'Build my ghost'})).toBeDisabled();
      await expect.poll(()=>page.locator('img[src="/upload/upload.svg"]').evaluate(i=>({width:i.width,height:i.height,loaded:i.complete && i.naturalWidth>0}))).toEqual({width:40,height:40,loaded:true});
      await capture(page,`${width}-upload-empty`);
      if(width===390) {
        const trigger=page.getByRole('button',{name:'Open navigation'});
        assert.ok((await trigger.boundingBox()).height>=44);
        await trigger.click();
        const dialog=page.getByRole('dialog');
        await expect(dialog.getByRole('link',{name:'Try your swing',exact:true})).toBeInViewport();
        await capture(page,'390-menu');
        await page.keyboard.press('Escape');
        await expect(trigger).toBeFocused();
      }
      const chooser=page.waitForEvent('filechooser');
      await page.getByRole('button',{name:'Choose a video'}).click();
      await (await chooser).setFiles({name:'invalid.txt',mimeType:'text/plain',buffer:Buffer.from('invalid')});
      await expect(page.locator('main').getByRole('alert')).toContainText('isn’t a MOV, MP4, M4V or AVI video.');
      await page.locator('input[type=file]').setInputFiles({name:'swing-fixture.mp4',mimeType:'video/mp4',buffer:Buffer.from('Synthetic transport fixture')});
      const slowdown=page.getByRole('radiogroup',{name:'Slowdown'});
      await slowdown.getByRole('radio',{name:'Auto',exact:true}).focus();
      await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight');
      await expect(slowdown.getByRole('radio',{name:'4×',exact:true})).toBeChecked();
      await expect(page.getByText('Plays 4× slower than real life, such as 120 fps slow motion played at 30 fps.')).toBeVisible();
      let reply='failure'; let pending; let payload='';
      await page.route('**/api/process',async route=>{
        payload=route.request().postDataBuffer().toString();
        if(reply==='pending'){pending=route;return;}
        await route.fulfill({status:reply==='waiting'?504:422,json:{detail:'Synthetic recoverable failure'}});
      });
      await page.getByRole('button',{name:'Build my ghost'}).click();
      await expect(page.getByRole('heading',{name:'Couldn’t build your ghost'})).toBeVisible();
      assert.match(payload,/name="slowdown"\r\n\r\n4/);
      assert.match(payload,/name="file"; filename="swing-fixture.mp4"/);
      assert.doesNotMatch(payload,/name="hand"|name="stroke"/,'Auto settings are omitted');
      await expect(page.getByText('swing-fixture.mp4',{exact:true})).toBeVisible();
      await capture(page,`${width}-upload-error`);
      reply='waiting'; await page.getByRole('button',{name:'Try again',exact:true}).click();
      await expect(page.getByRole('heading',{name:'Still processing, but this page stopped waiting'})).toBeVisible();
      await expect(page.getByRole('link',{name:'Open the swing list'})).toHaveAttribute('href','/ghost');
      await expect(page.locator('.upload-waiting')).toHaveAttribute('role','status');
      await capture(page,`${width}-upload-still-processing`);
      reply='pending'; await page.getByRole('button',{name:'Try again',exact:true}).click();
      await expect.poll(()=>!!pending).toBe(true);
      await expect(page.getByRole('heading',{name:'Working on your swing'})).toBeFocused();
      await expect(page.getByRole('progressbar',{name:'Upload'})).toHaveAttribute('aria-valuenow','0');
      await page.evaluate(()=>window.__shellUploadXhr.upload.dispatchEvent(new ProgressEvent('load')));
      await expect(page.getByText('The service reports back once, when your ghost is ready, so these steps are a rough guide. It can take a minute or two.')).toBeVisible();
      await expect(slowdown.getByRole('radio',{name:'4×',exact:true})).toBeDisabled();
      await capture(page,`${width}-upload-progress`);
      console.log(`${width}px: cancelling fixture request`);
      await page.getByRole('button',{name:'Stop waiting',exact:true}).click();
      await expect(page.getByRole('button',{name:'Build my ghost'})).toBeFocused();
      await expect(page.getByText(/Stopped waiting. The service may still finish that clip/)).toBeVisible();
      await expect(slowdown.getByRole('radio',{name:'4×',exact:true})).toBeChecked();
      // Chromium may not acknowledge a routed request after XHR cancellation; do not
      // wait indefinitely for that protocol response. Context cleanup owns the route.
      void pending.abort().catch(()=>{});
      console.log(`${width}px: removing preserved fixture`);
      await page.getByRole('button',{name:'Remove',exact:true}).click();
      await expect(page.getByRole('button',{name:'Build my ghost'})).toBeDisabled();
      // Use client navigation to catch duplicate shells and theme changes on route transitions.
      for(const path of ['/','/demo','/ghost','/upload']) {
        console.log(`${width}px: navigating to ${path}`);
        if(path==='/ghost') {
          await page.goto('/ghost');
        } else if(width===390) {
          await page.getByRole('button',{name:'Open navigation'}).click();
          await page.getByRole('dialog').locator(`a[href="${path}"]`).click();
        } else await page.locator(`.site-nav a[href="${path}"]`).click();
        await expect(page).toHaveURL(new URL(path,baseURL).href);
        await shell(page,path);
        if(path==='/ghost') {
          await expect(page.locator('main:visible')).toHaveCSS('background-color','rgb(11, 15, 18)');
          await expect(page.getByRole('button',{name:'1 Pick a swing',exact:true})).toBeVisible();
        }
        await capture(page,`${width}-${path==='/'?'home':path.slice(1)}`);
      }
      assert.deepEqual(externalFonts,[]); assert.deepEqual(errors,[]);
      results.push(`${width}px shared shell, upload states, settings, cancellation, navigation and local fonts: PASS`);
      console.log(results.at(-1));
    } catch(error) {
      console.error(`${width}px failure:`,error);
      await page.screenshot({path:`${output}/${width}-failure.png`,fullPage:true}).catch(()=>{});
      throw error;
    } finally {await Promise.race([context.close(),new Promise(resolve=>setTimeout(resolve,5000))]);}
  }
  const context=await browser.newContext({baseURL,viewport:{width:1440,height:900},reducedMotion:'reduce'});
  try {
    const page=await context.newPage();
    const catalogue=JSON.parse(await readFile('public/swings/catalogue.json','utf8'));
    for(const entry of catalogue.swings) {
      await page.goto('/ghost');
      await page.getByRole('button',{name:new RegExp(entry.id)}).click();
      const coach=JSON.parse(await readFile(`public/swings/${entry.coach}`,'utf8'));
      const cue=entry.stroke==='backhand'?'Nothing to fix in what the coach could check.':coach.cue;
      await expect(page.locator('blockquote')).toContainText(cue);
      if(entry.stroke==='forehand') {
        await page.evaluate(()=>document.fonts.ready);
        const fault=page.getByRole('region',{name:'Swing replay'}).getByText('Over-rotation: hips turn 157°',{exact:true});
        for(const [width,height] of [[1440,900],[1470,956]]) {
          await page.setViewportSize({width,height});
          await expect(fault).toBeInViewport({ratio:1});
          assert.equal(await page.evaluate(()=>scrollY),0,'Forehand fault is visible without scrolling');
          assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
          await page.screenshot({path:`${output}/${width}x${height}-forehand-coach.png`,animations:'disabled'});
        }
        await page.setViewportSize({width:1440,height:900});
        await page.locator('.site-brand').focus();
        await page.keyboard.press('Tab');
        const home=page.locator('.site-nav a[href="/"]');
        await expect(home).toBeFocused();
        await expect(home).toHaveCSS('outline-offset','-2px');
        results.push('Forehand fault fully visible without scrolling at 1440x900 and 1470x956: PASS');
      }
      await page.getByRole('button',{name:'Show the ghost',exact:true}).click();
      await page.getByRole('button',{name:'Show the court',exact:true}).click();
      await expect(page.getByText('PREDICTED BALL PATHS',{exact:true}).or(page.getByText('PREDICTED BALL PATH',{exact:true}))).toBeVisible();
      await expect(page.locator('blockquote')).toContainText(cue);
      await capture(page,`1440-ghost-${entry.stroke}`);
    }
    results.push('Protected forehand/backhand replay flow and current main coaching wording: PASS');
    console.log(results.at(-1));
  } finally {await context.close();}
} finally {
  await writeFile(`${output}/results.json`,JSON.stringify({browser:browser.version(),baseURL,results},null,2));
  await browser.close();
}
