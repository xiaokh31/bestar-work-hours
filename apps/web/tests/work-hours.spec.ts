import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const fixture = path.resolve("../../storage/synthetic-browser.xls");
const origin=process.env.TEST_WEB_URL ?? "http://localhost:3100";
test("synthetic attendance: no-login access, upload, correction, deletion, export, themes and languages", async ({page,context,request}, testInfo) => {
  const errors: string[]=[];page.on("pageerror",e=>errors.push(e.message));
  expect((await request.get("/api/attendance-imports")).status()).toBe(200);
  expect((await request.post("/api/auth/login",{data:{}})).status()).toBe(404);
  expect((await request.get("/api/auth/me")).status()).toBe(404);
  expect((await request.post("/api/attendance-imports",{headers:{Origin:"https://untrusted.invalid"},data:"invalid"})).status()).toBe(403);
  await page.goto("/");
  await expect(page).toHaveURL(/\/work-hours/);
  await expect(page.locator('[data-shell-user-cluster], input[type="password"], a[href="/login"]')).toHaveCount(0);
  await expect(page.getByRole("button",{name:/Sign in|Sign out|Log out/})).toHaveCount(0);
  // The previously open login URL also goes straight to the work-hours page.
  await page.goto("/login");
  await expect(page).toHaveURL(/\/work-hours/);
  expect((await context.cookies()).some(c=>c.name==="bestar_session")).toBe(false);
  await page.locator('input[type="file"]').setInputFiles(fixture);
  await page.getByRole("button",{name:"Upload .xls",exact:true}).click();
  await expect(page).toHaveURL(/attendanceImportId=/);
  const id=new URL(page.url()).searchParams.get("attendanceImportId")!;
  await page.getByRole("button",{name:"Parse",exact:true}).click();
  await expect(page.getByRole("button",{name:"Correct punches",exact:true}).first()).toBeVisible();
  await page.getByRole("button",{name:"Generate wage record",exact:true}).click();
  await expect(page.getByTestId("wage-record-file").getByRole("link",{name:"Download",exact:true})).toBeVisible();
  const firstFile=(await page.request.get(`/api/attendance-imports/${id}/files`)).json();
  const firstId=(await firstFile).items[0].id;
  const downloadPromise=page.waitForEvent("download");
  await page.getByRole("link",{name:"Download",exact:true}).click();
  const download=await downloadPromise;await download.saveAs(testInfo.outputPath("synthetic-original-export.xls"));
  expect(fs.readFileSync(testInfo.outputPath("synthetic-original-export.xls")).subarray(0,8).toString("hex")).toBe("d0cf11e0a1b11ae1");
  expect((await request.get(`/api/attendance-files/${firstId}/download`)).status()).toBe(200);
  await page.getByRole("button",{name:"Correct punches",exact:true}).first().click();
  const dialog=page.getByRole("dialog");await dialog.getByLabel("Punches",{exact:false}).fill("08:00 10:00");
  await dialog.getByLabel("Reason",{exact:true}).fill("Synthetic browser correction");await dialog.getByRole("button",{name:"Save correction"}).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByTestId("wage-record-file").getByRole("link",{name:"Download",exact:true})).toHaveCount(0);
  expect((await page.request.get(`/api/attendance-files/${firstId}/download`)).status()).toBe(409);
  await expect(page.getByText("Synthetic browser correction",{exact:false})).toBeVisible();
  await page.getByRole("button",{name:/Delete attendance row|Delete.*2026|Delete row/}).first().click();
  const deletion=page.getByRole("dialog");await deletion.getByLabel("Deletion reason",{exact:true}).fill("Synthetic browser deletion");
  await deletion.getByRole("button",{name:"Delete row",exact:true}).click();await expect(deletion).not.toBeVisible();
  await page.getByRole("button",{name:"Generate wage record",exact:true}).click();
  await expect(page.getByRole("link",{name:"Download",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Parse",exact:true}).click();
  await expect(page.getByRole("button",{name:"Generate wage record",exact:true})).toBeEnabled();
  const detail=await (await page.request.get(`/api/attendance-imports/${id}/parse-result`)).json();expect(detail.deletedRowCount).toBe(1);expect(detail.activeRowCount).toBe(59);
  for(const locale of ["en","zh-CN"]) {
    await page.getByRole("button",{name:locale==="en"?"English":"中文",exact:true}).click();
    await expect(page.locator("html")).toHaveAttribute("lang",locale);
    for(const theme of ["light","dark","system"]) {
      const labels=locale==="en"?{light:"Light theme",dark:"Dark theme",system:"Follow system theme"}:{light:"浅色主题",dark:"深色主题",system:"跟随系统主题"};
      await page.getByRole("button",{name:labels[theme as keyof typeof labels],exact:true}).click();
      await expect(page.locator("html")).toHaveAttribute("data-theme",theme);
      for(const width of [320,390,768,1366,1920]) {
        await page.setViewportSize({width,height:900});
        const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);expect(overflow,`${locale}/${theme}/${width} viewport overflow`).toBe(false);
        await page.evaluate(()=>{window.scrollTo(0,0);for(const el of document.querySelectorAll("div"))if(el.scrollLeft)el.scrollLeft=0;});
        if((width===390||width===1366)&&theme!=="system")await page.screenshot({path:testInfo.outputPath(`${locale}-${theme}-${width}.png`),fullPage:true});
      }
    }
  }
  expect(errors).toEqual([]);
  // IDs can be checked after restarting the Compose stack.
  fs.writeFileSync(path.resolve("../../storage/smoke-state.json"),JSON.stringify({id,firstId}));
});
