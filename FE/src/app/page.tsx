
"use client";

import { useEffect, useState } from "react";
import { checkBackend } from "@/lib/api";

export default function Home() {
  const [status, setStatus] = useState("Đang kiểm tra kết nối...");

  useEffect(() => {
    checkBackend()
      .then(() => {
        setStatus("Đã kết nối Backend thành công!");
      })
      .catch(() => {
        setStatus("Không thể kết nối Backend!");
      });
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <div className="w-full max-w-xl rounded-2xl bg-white p-8 shadow-lg">
        <h1 className="text-2xl font-bold text-slate-800">
          Electricity Consumption Analytics
        </h1>

        <p className="mt-3 text-sm text-slate-500">
          Hệ thống phân tích mức tiêu thụ điện năng
          và dự đoán nhu cầu điện.
        </p>

        <div className="mt-8 rounded-xl bg-slate-50 p-5">
          <p className="text-sm font-medium text-slate-600">
            Backend Connection
          </p>

          <p className="mt-2 font-semibold text-blue-600">
            {status}
          </p>
        </div>
      </div>
    </main>
  );
}
