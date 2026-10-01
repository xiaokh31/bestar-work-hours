import { DEFAULT_LOCALE, type Locale } from "./catalog";
const labels: Record<string, [string,string]> = {
  READY:["Generated","已生成"], GENERATED:["Generated","已生成"], COMPLETED:["Completed","已完成"],
  UPLOADED:["Uploaded","已上传"], PARSED:["Parsed","已解析"], NOT_PARSED:["Not parsed","未解析"], PARSING:["Parsing","解析中"],
  WARNING:["Warning","警告"], REVIEW_REQUIRED:["Needs review","待复核"], ERROR:["Error","错误"], FAILED:["Failed","失败"],
  SUPERSEDED:["Superseded","已失效"], DELETED:["Deleted","已删除"], CORRECTED:["Corrected","已修正"],
  OK:["Healthy","正常"], UP:["Connected","已连接"], DOWN:["Unavailable","不可用"], DEGRADED:["Degraded","服务异常"], UNKNOWN:["Unknown","未知"],
  WAGE_RECORD_XLS:["Wage record workbook","工时 Excel"],
};
export function businessStatusLabel(value: string, locale: Locale = DEFAULT_LOCALE): string { return labels[value.toUpperCase()]?.[locale === "zh-CN" ? 1 : 0] ?? value; }
export const healthStatusLabel = businessStatusLabel;
export const generatedFileTypeLabel = businessStatusLabel;
