"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/components/i18n/i18n-provider";
import { correctAttendanceRow, type AttendanceRowResponse } from "@/lib/api-client";
import { attendanceApiErrorMessage } from "./attendance-flow";
export function AttendanceRowCorrection({ attendanceImportId, row, revision }: {attendanceImportId:string;row:AttendanceRowResponse;revision:number}) {
  const {t,locale}=useI18n(); const router=useRouter(); const dialog=useRef<HTMLDialogElement>(null);
  const [punches,setPunches]=useState(Array.isArray(row.punchTimes)?row.punchTimes.join(" "):"");
  const [reason,setReason]=useState("");const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault(); const values=punches.trim()?punches.trim().split(/[\s,，]+/):[];
    if(values.length>32||values.some(v=>!/^([01]\d|2[0-3]):[0-5]\d$/.test(v))) {setError(t("Enter punches as HH:mm separated by spaces."));return;}
    setBusy(true);setError("");
    try {await correctAttendanceRow(attendanceImportId,row.id,values,reason.trim(),revision);dialog.current?.close();setReason("");router.refresh();}
    catch(e){setError(attendanceApiErrorMessage(e,locale));}finally{setBusy(false);}
  }
  return <>
    <button className="mb-2 min-h-9 border border-teal-700 bg-white px-3 text-xs font-semibold text-teal-900 hover:bg-teal-50" type="button" onClick={()=>{setPunches(Array.isArray(row.punchTimes)?row.punchTimes.join(" "):"");setError("");dialog.current?.showModal();}}>{t("Correct punches")}</button>
    <dialog ref={dialog} className="fixed inset-0 m-auto max-h-[90vh] w-[calc(100%-2rem)] max-w-xl overflow-auto border border-zinc-300 bg-white p-5 text-zinc-950 shadow-2xl backdrop:bg-zinc-950/60" aria-labelledby={`correct-title-${row.id}`} onCancel={e=>{if(busy)e.preventDefault();}}>
      <form className="grid gap-4" onSubmit={submit}>
        <h2 className="text-lg font-semibold" id={`correct-title-${row.id}`}>{t("Correct punches")}</h2>
        <p className="text-sm text-zinc-600">{row.employeeName} · {row.workDate}</p>
        <p className="text-sm text-zinc-600">{t("Corrections preserve the source and audit history. Generate a new workbook after saving.")}</p>
        <label className="grid gap-2 text-sm font-semibold">{t("Punches")}<input autoFocus className="min-h-10 border border-zinc-300 bg-white px-3" value={punches} disabled={busy} onChange={e=>setPunches(e.target.value)} maxLength={256}/><span className="text-xs font-normal text-zinc-600">{t("Enter punches as HH:mm separated by spaces.")}</span></label>
        <label className="grid gap-2 text-sm font-semibold">{t("Reason")}<textarea className="min-h-24 border border-zinc-300 bg-white p-3" value={reason} disabled={busy} onChange={e=>setReason(e.target.value)} required minLength={1} maxLength={1000}/></label>
        {error?<p role="alert" className="text-sm text-red-800">{error}</p>:null}
        <div className="flex flex-wrap justify-end gap-2"><button type="button" className="min-h-10 border border-zinc-300 bg-white px-4 text-sm font-semibold" disabled={busy} onClick={()=>dialog.current?.close()}>{t("Cancel")}</button><button className="min-h-10 border border-teal-700 bg-teal-700 px-4 text-sm font-semibold text-white disabled:opacity-50" disabled={busy||!reason.trim()}>{t("Save correction")}</button></div>
      </form>
    </dialog>
  </>;
}
