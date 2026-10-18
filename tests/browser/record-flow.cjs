/** Real UI + real isolated backend + real OpenRouter. No mocked responses. */
const path = require('node:path');
const fs = require('node:fs/promises');
const {createRequire} = require('node:module');
const {chromium} = createRequire(path.resolve(__dirname, '../../web/package.json'))('playwright');
const assert = require('node:assert/strict');

async function main() {
  if (process.env.SIMPLIFY_LIVE_BROWSER_TEST !== '1') throw Error('Set SIMPLIFY_LIVE_BROWSER_TEST=1 to authorize live AI requests against a disposable backend.');
  const base = process.env.SIMPLIFY_WEB_URL || 'http://127.0.0.1:3000';
  const backend = process.env.SIMPLIFY_TEST_API_URL;
  if (!backend) throw Error('Set SIMPLIFY_TEST_API_URL to an isolated API instance; never target real customer data.');
  const out = path.resolve(process.env.SIMPLIFY_RECORDING_DIR || 'docs/recordings');
  await fs.mkdir(out, {recursive:true});
  const started = Date.now();
  const report = {name:'SimplifySimulation recorded live browser flow', started_at:new Date().toISOString(), data:'Fictional capacity estimates only; separate application database.', agent:'Real OpenRouter; no response stubbing', steps:[], browser_errors:[]};
  let browser, context, page, video;
  async function step(name, action) {
    const result = {name, start_seconds:Math.round((Date.now()-started)/100)/10};
    report.steps.push(result); console.log('STEP:',name);
    try {await action(); result.status='passed'; await page.waitForTimeout(650);}
    catch(e) {result.status='failed'; result.error=e.message; throw e;}
  }
  async function request(action, suffix) {
    const waiting=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith(suffix) && r.request().method()!=='GET',{timeout:180000});
    await action();const response=await waiting;const body=await response.json();
    assert.equal(response.status(),200,JSON.stringify(body.detail||body));return body;
  }
  try {
    browser=await chromium.launch({headless:true,slowMo:110,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH}:{}),args:['--no-sandbox']});
    context=await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:path.join(out,'.raw'),size:{width:1440,height:1000}}});
    // Only reroutes HTTP to a real isolated backend; no response body is fabricated.
    await context.route('**/api/**',async route=>{
      const original=new URL(route.request().url());
      const response=await route.fetch({url:new URL(original.pathname+original.search,backend).href,timeout:180000});
      await route.fulfill({response});
    });
    page=await context.newPage();video=page.video();page.setDefaultTimeout(25000);
    page.on('pageerror',e=>report.browser_errors.push(e.message));
    await step('Open the real frontend and create a synthetic decision',async()=>{
      await page.goto(base);await page.getByRole('heading',{name:'The future isn’t a guess.'}).waitFor();
      assert.match(await page.title(),/SimplifySimulation/);
      await page.getByLabel('Strategic question',{exact:true}).fill('SYNTHETIC VIDEO TEST: Should we expand capacity from 90 to 110 units/year to serve at least 95 units/year over the next 12 months? Use only fictional estimates; company-wide scope.');
      const p=await request(()=>page.getByRole('button',{name:'Explore decision'}).click(),'/projects');report.project_id=p.id;
      await page.getByRole('heading',{name:'Decision conversation',exact:true}).waitFor();
    });
    await step('Request clarification from the real AI agent',async()=>{
      await page.getByRole('checkbox',{name:/Allow sending this context/}).check();
      await request(()=>page.getByRole('button',{name:'Start clarification',exact:true}).click(),'/messages');
      await page.locator('.message.assistant').first().waitFor();
    });
    await step('Confirm the decision context',async()=>{
      await page.getByLabel('Review or correct the summary').fill('Fictional manufacturing capacity decision, not a business forecast. Company-wide scope, next 12 months, target served demand >=95 units/year. Current capacity fixed at 90 units/year; proposed capacity fixed at 110 units/year. Demand uncertainty will use our synthetic CSV. Independent sampling.');
      await request(()=>page.getByRole('button',{name:'Confirm context',exact:true}).click(),'/context-confirmation');
      await page.getByText(/Context confirmed/).waitFor();
    });
    await step('Upload two synthetic CSVs and verify PII exclusion',async()=>{
      const uploaded=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/sources/csv')&&r.request().method()==='POST');
      await page.getByLabel('Upload CSV files').setInputFiles([
        {name:'synthetic-demand.csv',mimeType:'text/csv',buffer:Buffer.from('month,demand,email\n2026-01,90,example1@example.invalid\n2026-02,100,example2@example.invalid\n2026-03,110,example3@example.invalid\n')},
        {name:'synthetic-costs.csv',mimeType:'text/csv',buffer:Buffer.from('cost\n50\n60\n')}
      ]);assert.equal((await uploaded).status(),200);
      await page.getByRole('heading',{name:'synthetic-costs.csv',exact:true}).waitFor();
      const card=page.locator('article.source-card').filter({has:page.getByRole('heading',{name:'synthetic-demand.csv',exact:true})});
      assert.equal(await card.getByRole('checkbox',{name:/Potential identifier/}).isDisabled(),true);
      report.pii_column_excluded=true;
    });
    const demandCard=()=>page.locator('article.source-card').filter({has:page.getByRole('heading',{name:'synthetic-demand.csv',exact:true})});
    await step('Discuss the CSV with the real agent',async()=>{
      await demandCard().getByRole('button',{name:'Discuss with agent',exact:true}).click();
      await page.locator('#agent-message').fill('Explain which columns support annual demand in this synthetic dataset. The email column is a fake identifier and must remain excluded. Do not approve sources or propose a model yet.');
      await request(()=>page.getByRole('button',{name:'Send to Agent SimplifySimulation'}).click(),'/messages');
      assert.equal(await page.getByLabel('Conversation source').inputValue()==='',false);
    });
    await step('Map only the needed numeric column and approve its source',async()=>{
      const card=demandCard();await card.getByRole('checkbox',{name:/^demand/}).check();
      await card.getByLabel('Business definition').fill('Synthetic annual demand observations');
      await card.getByLabel('Unit',{exact:true}).fill('units/year');
      await card.getByLabel('Observation period').fill('Fictional next-year scenarios');
      await card.getByLabel('Geography / population').fill('Demo company');
      await request(()=>card.getByRole('button',{name:'Validate selected data',exact:true}).click(),'/selection');
      await card.getByRole('checkbox',{name:/I reviewed the selected/}).check();
      await request(()=>card.getByRole('button',{name:'Approve this source version'}).click(),'/approve');
      await card.getByText('APPROVED',{exact:true}).waitFor();
    });
    await step('Exclude unused evidence and document explicit assumptions',async()=>{
      const card=page.locator('article.source-card').filter({has:page.getByRole('heading',{name:'synthetic-costs.csv',exact:true})});
      await card.getByRole('button',{name:'Exclude from decision'}).click();
      await card.getByRole('button',{name:'Include in decision'}).waitFor();
    });
    await step('Approve the combined evidence snapshot',async()=>{
      await page.getByText('Use explicit assumptions when evidence is unavailable',{exact:true}).click();
      await page.getByLabel('Estimates and their basis').fill('Fictional approved estimates: baseline capacity fixed at 90 units/year, strategy capacity fixed at 110 units/year. For stochastic annual demand use a triangular distribution with min 90, mode 100, max 110 based on the three approved synthetic CSV observations. Formula served=min(demand,capacity), target served>=95. These are simulation-testing assumptions only.');
      await request(()=>page.getByRole('button',{name:'Save explicit assumptions'}).click(),'/estimates');
      await page.getByRole('button',{name:'Check evidence readiness'}).click();
      await page.getByText('Evidence is ready for your review.').waitFor();
      await page.getByRole('checkbox',{name:/I approve the combined evidence/}).check();
      await request(()=>page.getByRole('button',{name:'Approve & freeze evidence snapshot'}).click(),'/evidence-snapshots');
    });
    await step('Request a source-grounded model from the real agent',async()=>{
      const p=await request(()=>page.getByRole('button',{name:'Ask agent to propose the model',exact:true}).click(),'/messages');
      assert.equal(p.status,'MODEL_PROPOSED','Agent did not return an executable model; inspect the saved reply.');
      await page.getByText('MODEL PROPOSED',{exact:true}).waitFor();
    });
    await step('Approve the model and complete 10,000 paired simulations',async()=>{
      await page.getByRole('checkbox',{name:/I approve this model, evidence/}).check();
      await request(()=>page.getByRole('button',{name:'Approve model & evidence',exact:true}).click(),'/approve');
      await page.getByText('READY TO RUN',{exact:true}).waitFor();
      const p=await request(()=>page.getByRole('button',{name:'Run simulation'}).click(),'/runs');
      await page.getByRole('heading',{name:'Decision outlook.',exact:true}).waitFor();
      const saved=await (await context.request.get(new URL(`/api/projects/${report.project_id}`,backend).href)).json();
      const run=saved.runs.at(-1);assert.equal(run.status,'COMPLETED');assert.equal(run.result.iterations,10000);
      report.engine_iterations_verified=run.result.iterations;report.completed_run_verified=true;
      await page.getByRole('heading',{name:'Strategy outcome distribution',exact:true}).scrollIntoViewIfNeeded();
    });
    await step('Record a fictional decision and verify persistence after reload',async()=>{
      await page.getByPlaceholder('Record your chosen action, conditions, and next review…').fill('Synthetic test decision: pilot capacity expansion and review demand. This is not a real company decision.');
      await request(()=>page.getByRole('button',{name:'Record decision',exact:true}).click(),'/decision');
      await page.reload();await page.getByRole('button',{name:'Decision library'}).click();
      await page.getByRole('button',{name:'Open decision'}).first().click();
      await page.getByRole('heading',{name:'Decision outlook.',exact:true}).waitFor();
      await page.getByText(/Synthetic test decision: pilot capacity expansion/).waitFor();
      assert.equal(report.browser_errors.length,0);
      report.persistence_verified=true;
    });
    await step('Run a real Tavily search without changing approved evidence',async()=>{
      await page.getByRole('button',{name:'Explore internet',exact:true}).click();
      await page.getByLabel('Search for evidence').fill('site:bi.go.id BI-Rate policy rate 2026');
      await page.getByRole('checkbox',{name:/Allow this search query/}).check();
      const p=await request(()=>page.getByRole('button',{name:'Search internet',exact:true}).click(),'/internet-search');
      assert.ok(p.search_results.results.length>0);
      await page.getByRole('button',{name:'Review this URL'}).first().waitFor();
      report.real_search_results=p.search_results.results.length;
    });
    await step('Check mobile layout',async()=>{
      await page.setViewportSize({width:390,height:844});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      report.mobile_horizontal_overflow=false;
    });
    report.status='passed';
  } catch(e) {report.status='failed';report.error=e.message;console.error(e.message);process.exitCode=1;}
  finally {
    report.duration_seconds=Math.round((Date.now()-started)/1000);
    if(context)await context.close();
    if(video){await video.saveAs(path.join(out,'simplifysimulation-desktop.webm'));await video.delete();}
    if(browser)await browser.close();
    await fs.writeFile(path.join(out,'test-report.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify({status:report.status,steps:report.steps.length,seconds:report.duration_seconds,output:out}));
  }
}
main().catch(e=>{console.error(e);process.exitCode=1});
