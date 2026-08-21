import type { SqlJsStatic } from "sql.js";

declare global {
  interface Window {
    initSqlJs?: () => Promise<SqlJsStatic>;
  }
}

export {};
