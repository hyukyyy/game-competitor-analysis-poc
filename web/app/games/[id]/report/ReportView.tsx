"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function ReportView({ markdown }: { markdown: string }) {
  return (
    <>
      <div className="mb-4 flex justify-end print:hidden">
        <button
          type="button"
          onClick={() => window.print()}
          className="rounded border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-900 transition hover:bg-zinc-100"
        >
          Download PDF
        </button>
      </div>

      <article className="print-article rounded-lg border border-zinc-200 bg-white p-8 shadow-sm">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: (props) => (
              <h1
                className="mb-4 border-b border-zinc-200 pb-3 text-2xl font-bold text-zinc-900"
                {...props}
              />
            ),
            h2: (props) => (
              <h2
                className="mt-10 mb-4 border-b border-zinc-100 pb-2 text-xl font-semibold text-zinc-900"
                {...props}
              />
            ),
            h3: (props) => (
              <h3
                className="mt-6 mb-2 text-lg font-semibold text-zinc-900"
                {...props}
              />
            ),
            p: (props) => (
              <p className="my-3 leading-relaxed text-zinc-700" {...props} />
            ),
            ul: (props) => (
              <ul
                className="my-3 list-disc space-y-1 pl-6 text-zinc-700"
                {...props}
              />
            ),
            ol: (props) => (
              <ol
                className="my-3 list-decimal space-y-1 pl-6 text-zinc-700"
                {...props}
              />
            ),
            li: (props) => <li className="leading-relaxed" {...props} />,
            hr: () => <hr className="my-6 border-zinc-200" />,
            strong: (props) => (
              <strong className="font-semibold text-zinc-900" {...props} />
            ),
            em: (props) => (
              <em className="italic text-zinc-600" {...props} />
            ),
            code: (props) => (
              <code
                className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs text-zinc-800"
                {...props}
              />
            ),
            table: (props) => (
              <div className="my-4 overflow-x-auto">
                <table
                  className="w-full border-collapse overflow-hidden rounded border border-zinc-200 text-sm"
                  {...props}
                />
              </div>
            ),
            thead: (props) => <thead className="bg-zinc-100" {...props} />,
            th: (props) => (
              <th
                className="border-b border-zinc-200 px-3 py-2 text-left font-semibold text-zinc-900"
                {...props}
              />
            ),
            tr: (props) => (
              <tr className="even:bg-zinc-50" {...props} />
            ),
            td: (props) => (
              <td
                className="border-b border-zinc-100 px-3 py-2 text-zinc-700"
                {...props}
              />
            ),
            a: (props) => (
              <a
                className="text-indigo-600 underline hover:text-indigo-800"
                target="_blank"
                rel="noopener noreferrer"
                {...props}
              />
            ),
          }}
        >
          {markdown}
        </ReactMarkdown>
      </article>
    </>
  );
}
