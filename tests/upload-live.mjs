// Explicit live check: node tests/upload-live.mjs path-to-clip [auto|1|4|8] [auto|forehand|backhand]
// Processes one real clip through the local service. Never commit the clip or generated data.
import assert from 'node:assert/strict';
import { mkdir, stat, writeFile } from 'node:fs/promises';
import { basename, resolve } from 'node:path';
import { chromium, expect } from '@playwright/test';

if(!process.argv[2]) throw new Error('Supply the path to an authorized real squash clip; keep it outside source control.');
const clip=resolve(process.argv[2]);
const slowdownValue=process.argv[3] || 'auto';
assert.ok(['auto','1','4','8'].includes(slowdownValue),'Slowdown must be auto, 1, 4 or 8');
const slowdownLabel=slowdownValue==='auto'?'Auto':`${slowdownValue}×`;
const strokeValue=process.argv[4] || 'auto';
assert.ok(['auto','forehand','backhand'].includes(strokeValue),'Stroke must be auto, forehand or backhand');
const strokeLabel=strokeValue[0].toUpperCase()+strokeValue.slice(1);
assert.ok((await stat(clip)).isFile(),'Clip exists');
const baseURL=process.env.GHOST_TEST_URL || 'http://localhost:3000';
const output=`build/browser-tests/design-review/shell-upload/${process.env.GHOST_LIVE_REVIEW || 'live'}`;
await mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({baseURL,viewport:{width:1440,height:900},reducedMotion:'reduce'});
context.setDefaultTimeout(30000);
const page=await context.newPage();
let result={passed:false};
const started=Date.now();
try {
  await page.goto('/upload');
  // Confirm interactive hydration before a fast automated file selection.
  const slowdown=page.getByRole('radiogroup',{name:'Slowdown'});
  await expect(async()=>{
    await slowdown.locator('label').filter({hasText:'1×'}).click();
    await expect(page.getByText('Normal-speed video, such as 60 fps.')).toBeVisible();
  }).toPass({timeout:15000});
  await slowdown.locator('label').filter({hasText:new RegExp(`^${slowdownLabel}$`)}).click();
  await expect(slowdown.getByRole('radio',{name:slowdownLabel,exact:true})).toBeChecked();
  const stroke=page.getByRole('radiogroup',{name:'Stroke',exact:true});
  await stroke.locator('label').filter({hasText:new RegExp(`^${strokeLabel}$`)}).click();
  await expect(stroke.getByRole('radio',{name:strokeLabel,exact:true})).toBeChecked();
  const chooser=page.waitForEvent('filechooser');
  await page.getByRole('button',{name:'Choose a video'}).click();
  await (await chooser).setFiles(clip);
  await expect(page.getByRole('button',{name:'Build my ghost'})).toBeEnabled();
  await expect(page.getByRole('radiogroup',{name:'Hitting hand'}).getByRole('radio',{name:'Auto',exact:true})).toBeChecked();
  await expect(stroke.getByRole('radio',{name:strokeLabel,exact:true})).toBeChecked();
  await expect(slowdown.getByRole('radio',{name:slowdownLabel,exact:true})).toBeChecked();
  const responsePromise=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/process' && r.request().method()==='POST',{timeout:660000});
  void responsePromise.catch(()=>{});
  console.log(`Submitting ${basename(clip)} with Slowdown ${slowdownLabel}, stroke ${strokeLabel}.`);
  await page.getByRole('button',{name:'Build my ghost'}).click();
  console.log('Submission started; waiting for the pipeline response.');
  const response=await responsePromise;
  const body=await response.json();
  result={passed:false,clip:basename(clip),slowdown:slowdownValue,stroke:strokeValue,status:response.status(),elapsedSeconds:Math.round((Date.now()-started)/1000),swingId:body.swingId ?? null,detail:body.detail ?? body.error ?? null};
  assert.equal(response.status(),201,JSON.stringify(result));
  assert.ok(body.swingId,'Service returned a saved swing');
  await expect(page).toHaveURL(new RegExp(`/ghost\\?swing=${body.swingId}`),{timeout:30000});
  await expect(page.getByRole('button',{name:'Show the ghost',exact:true})).toBeVisible({timeout:60000});
  await expect(page.locator('blockquote')).toBeVisible({timeout:60000});
  await expect(page.locator('canvas')).toHaveCount(1,{timeout:60000});
  await page.getByRole('button',{name:'Show the ghost',exact:true}).click();
  await page.getByRole('button',{name:'Show the court',exact:true}).click();
  await expect(page.getByText('PREDICTED BALL PATHS',{exact:true}).or(page.getByText('PREDICTED BALL PATH',{exact:true}))).toBeVisible({timeout:60000});
  await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));
  await page.screenshot({path:`${output}/1440-live-court.png`,fullPage:true,animations:'disabled'});
  await page.getByRole('button',{name:'Try another swing',exact:true}).click();
  const liveCard=page.getByRole('button',{name:new RegExp(body.swingId)});
  await expect(liveCard).toContainText('Live');
  await page.screenshot({path:`${output}/1440-live-card.png`,fullPage:true,animations:'disabled'});
  result={...result,passed:true,ghost:true,court:true,liveCard:true};
  console.log(JSON.stringify(result));
} catch(error) {
  await page.screenshot({path:`${output}/failure.png`,fullPage:true}).catch(()=>{});
  console.log('Visible state:',await page.locator('main:visible').innerText().catch(()=>''));
  throw error;
} finally {
  await writeFile(`${output}/result.json`,JSON.stringify(result,null,2));
  await context.close(); await browser.close();
}
