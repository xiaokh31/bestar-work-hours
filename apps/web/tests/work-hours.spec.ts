import { test, expect } from "@playwright/test";

test("read-only attendance: direct access, existing records/download, themes and languages", async ({page,context,request}) => {
  // Only GET requests: this suite never uploads fixtures, generates files or edits attendance.
  const errors: string[]=[];page.on("pageerror",e=>errors.push(e.message));
  const importsResponse=await request.get("/api/attendance-imports");
  expect(importsResponse.status()).toBe(200);
  expect((await request.get("/api/auth/me")).status()).toBe(404);
  await page.goto("/");
  await expect(page).toHaveURL(url => url.pathname === "/");
  await expect(page.locator('[data-shell-user-cluster], input[type="password"], a[href="/login"]')).toHaveCount(0);
  await expect(page.getByRole("button",{name:/Sign in|Sign out|Log out/})).toHaveCount(0);
  await page.goto("/login");
  await expect(page).toHaveURL(url => url.pathname === "/");
  expect((await context.cookies()).some(c=>c.name==="bestar_session")).toBe(false);
  const {items}=await importsResponse.json();
  if(items.length) {
    const id=items[0].id;
    // Existing saved links retain their selection when redirected to the homepage.
    await page.goto(`/work-hours?attendanceImportId=${encodeURIComponent(id)}`);
    await expect(page).toHaveURL(url => url.pathname === "/" && url.searchParams.get("attendanceImportId") === id);
    await expect(page.locator('input[type="file"]')).toBeAttached();
    const files=await (await request.get(`/api/attendance-imports/${id}/files`)).json();
    const ready=files.items.find((file: {status:string})=>file.status==="READY");
    if(ready) {
      await expect(page.getByTestId("wage-record-file").getByRole("link",{name:/Download|下载/,exact:true}).first()).toBeVisible();
      const download=await request.get(`/api/attendance-files/${ready.id}/download`);
      expect(download.status()).toBe(200);
      expect((await download.body()).subarray(0,8).toString("hex")).toBe("d0cf11e0a1b11ae1");
    }
  }
  for(const locale of ["en","zh-CN"]) {
    await page.getByRole("button",{name:locale==="en"?"English":"中文",exact:true}).click();
    await expect(page.locator("html")).toHaveAttribute("lang",locale);
    for(const theme of ["light","dark","system"]) {
      const labels=locale==="en"?{light:"Light theme",dark:"Dark theme",system:"Follow system theme"}:{light:"浅色主题",dark:"深色主题",system:"跟随系统主题"};
      await page.getByRole("button",{name:labels[theme as keyof typeof labels],exact:true}).click();
      await expect(page.locator("html")).toHaveAttribute("data-theme",theme);
      for(const width of [320,390,768,1366,1920]) {
        await page.setViewportSize({width,height:900});
        const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);
        expect(overflow,`${locale}/${theme}/${width} viewport overflow`).toBe(false);
      }
    }
  }
  expect(errors).toEqual([]);
});
