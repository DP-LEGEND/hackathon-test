// Explicit live check: node tests/upload-live.mjs C:\clips\a-squash-swing.mov
// Processes one real clip through the local service. Never commit the clip or generated data.
import assert from 'node:assert/strict';
import { mkdir, stat, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium, expect } from '@playwright/test';

if(!process.argv[2]) throw new Error('Supply the absolute path to an authorized real squash clip outside this repository.');
const clip=resolve(process.argv[2]);
assert.ok((await stat(clip)).isFile(),'Clip exists');
const baseURL=process.env.GHOST_TEST_URL || 'http://localhost:3000';
const output='build/browser-tests/design-review/shell-upload/live';
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
  await slowdown.locator('label').filter({hasText:'Auto'}).click();
  await expect(page.getByText('Auto reads the clip’s timing. Slow-motion clips often need it set.')).toBeVisible();
  const chooser=page.waitForEvent('filechooser');
  await page.getByRole('button',{name:'Choose a video'}).click();
  await (await chooser).setFiles(clip);
  await expect(page.getByRole('button',{name:'Build my ghost'})).toBeEnabled();
  for(const name of ['Hitting hand','Stroke','Slowdown']) await expect(page.getByRole('radiogroup',{name}).getByRole('radio',{name:'Auto',exact:true})).toBeChecked();
  const responsePromise=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/process' && r.request().method()==='POST',{timeout:660000});
  void responsePromise.catch(()=>{});
  console.log('Submitting the supplied real clip with Auto settings.');
  await page.getByRole('button',{name:'Build my ghost'}).click();
  console.log('Submission started; waiting for the pipeline response.');
  const response=await responsePromise;
  const body=await response.json();
  result={passed:false,status:response.status(),elapsedSeconds:Math.round((Date.now()-started)/1000),swingId:body.swingId ?? null,detail:body.detail ?? body.error ?? null};
  assert.equal(response.status(),201,JSON.stringify(result));
  assert.ok(body.swingId,'Service returned a saved swing');
  await expect(page).toHaveURL(new RegExp(`/ghost\\?swing=${body.swingId}`),{timeout:30000});
  await expect(page.getByRole('button',{name:'Show the ghost',exact:true})).toBeVisible({timeout:60000});
  await expect(page.locator('canvas')).toHaveCount(1);
  await page.getByRole('button',{name:'Show the ghost',exact:true}).click();
  await page.getByRole('button',{name:'Show the court',exact:true}).click();
  await expect(page.getByText('PREDICTED BALL PATHS',{exact:true}).or(page.getByText('PREDICTED BALL PATH',{exact:true}))).toBeVisible();
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
